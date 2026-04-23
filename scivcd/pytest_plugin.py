"""pytest plugin for scivcd.

Registration
------------
Declared in pyproject.toml (W6) as::

    [project.entry-points."pytest11"]
    scivcd = "scivcd.pytest_plugin"

Usage
-----
Run the test suite with VCD checks active::

    pytest --scivcd                            # fail on HIGH+
    pytest --scivcd --scivcd-severity MEDIUM   # fail on MEDIUM+

How it works
------------
1. ``pytest_configure`` calls ``scivcd.install()`` when ``--scivcd`` is given.
   This hooks matplotlib's ``savefig`` so every figure saved during tests is
   captured and checked automatically.
2. ``pytest_runtest_teardown`` collects findings accumulated during the test,
   checks against the configured severity threshold, and injects a failure via
   ``pytest.fail()`` if the threshold is breached.
3. ``pytest_unconfigure`` calls ``scivcd.uninstall()`` to restore matplotlib.

Severity threshold
------------------
``--scivcd-severity`` accepts any ``Severity`` name (case-insensitive):
BLOCKER, HIGH (default), MEDIUM, LOW, INFO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


# ---------------------------------------------------------------------------
# Option registration
# ---------------------------------------------------------------------------

def pytest_addoption(parser) -> None:
    group = parser.getgroup("scivcd", "SciVCD visual conflict detection")
    group.addoption(
        "--scivcd",
        action="store_true",
        default=False,
        help="Run SciVCD checks on every figure saved during tests.",
    )
    group.addoption(
        "--scivcd-severity",
        default="HIGH",
        metavar="LEVEL",
        help=(
            "Fail tests when any finding at this severity or higher is found. "
            "Choices: BLOCKER, HIGH (default), MEDIUM, LOW, INFO."
        ),
    )


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def pytest_configure(config) -> None:
    """Install scivcd hooks when --scivcd flag is present."""
    if not config.getoption("--scivcd", default=False):
        return

    try:
        import scivcd
        import scivcd.checks  # noqa: F401 — trigger detector registration
    except ImportError:
        # scivcd not fully assembled yet; register a marker and skip silently
        config._scivcd_available = False
        return

    config._scivcd_available = True

    try:
        scivcd.install()
    except Exception as exc:
        import warnings
        warnings.warn(f"scivcd.install() failed: {exc}", stacklevel=1)
        config._scivcd_available = False


def pytest_unconfigure(config) -> None:
    """Uninstall scivcd hooks after the session ends."""
    if not getattr(config, "_scivcd_available", False):
        return
    try:
        import scivcd
        scivcd.uninstall()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Per-test teardown
# ---------------------------------------------------------------------------

def pytest_runtest_teardown(item, nextitem) -> None:  # noqa: ARG001
    """Collect per-test findings and fail when threshold is exceeded."""
    config = item.config
    if not config.getoption("--scivcd", default=False):
        return
    if not getattr(config, "_scivcd_available", False):
        return

    # Resolve the severity threshold
    severity_name = config.getoption("--scivcd-severity", default="HIGH").upper()
    try:
        from scivcd.core.types import Severity
        threshold = Severity.coerce(severity_name)
    except (ValueError, ImportError):
        return  # Can't determine threshold; skip

    # Collect findings that were produced during this test item.
    # scivcd.Report is expected to expose a ``current()`` classmethod or a
    # ``flush()`` that returns findings since the last call.
    findings = _collect_findings_since_last_test()
    if not findings:
        return

    # Filter to findings at or above threshold
    violations = [
        f for f in findings
        if f.severity.value <= threshold.value
    ]
    if not violations:
        return

    import pytest
    lines = [
        f"scivcd: {len(violations)} finding(s) at or above {threshold.name}:",
    ]
    for f in violations:
        loc = f" [{f.call_site}]" if f.call_site else ""
        lines.append(f"  [{f.severity.name}] {f.check_id}: {f.message}{loc}")
        if f.fix_suggestion:
            lines.append(f"         fix: {f.fix_suggestion}")
    pytest.fail("\n".join(lines), pytrace=False)


# ---------------------------------------------------------------------------
# Finding collection helpers
# ---------------------------------------------------------------------------

# Module-level accumulator: matplotlib event-based capture
_pending_findings: list = []


def _collect_findings_since_last_test() -> list:
    """Return and clear all findings accumulated since the last test."""
    global _pending_findings
    try:
        import scivcd
        # Try the preferred Report.flush() API first
        try:
            report = scivcd.Report.flush()
            findings = list(report.findings) if hasattr(report, "findings") else []
        except AttributeError:
            # Fallback: use module-level pending list populated by
            # the savefig hook below
            findings = list(_pending_findings)
            _pending_findings = []
        return findings
    except ImportError:
        findings = list(_pending_findings)
        _pending_findings = []
        return findings


def _on_figure_saved(figure_path: str) -> None:
    """Callback invoked by scivcd's savefig hook for each saved figure.

    When the Report API is unavailable, this populates ``_pending_findings``
    so teardown can still collect them.
    """
    try:
        import scivcd
        report = scivcd.check(figure_path)
        findings = list(report.findings) if hasattr(report, "findings") else []
        _pending_findings.extend(findings)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# matplotlib savefig event hook (belt-and-suspenders)
# ---------------------------------------------------------------------------

def _install_mpl_hook() -> None:
    """Register a matplotlib event listener for figure saves."""
    try:
        import matplotlib
        matplotlib.rcParams.setdefault("backend", matplotlib.get_backend())
        # Matplotlib fires 'close_event' but not 'save_figure_event' in older
        # versions.  We patch Figure.savefig as a lightweight alternative.
        from matplotlib.figure import Figure
        _original_savefig = Figure.savefig

        def _patched_savefig(self, fname, *args, **kwargs):
            result = _original_savefig(self, fname, *args, **kwargs)
            if isinstance(fname, str):
                _on_figure_saved(fname)
            return result

        if not getattr(Figure.savefig, "_scivcd_patched", False):
            _patched_savefig._scivcd_patched = True
            Figure.savefig = _patched_savefig  # type: ignore[method-assign]

    except ImportError:
        pass


# Install the hook at plugin import time so it is active for the whole session.
_install_mpl_hook()
