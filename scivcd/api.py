"""Public programmatic API for scivcd.

Two entry points:

* :func:`check` — run registered checks against an already-built figure and
  return a :class:`Report` *without* installing any global hooks. The
  figure is consumed read-only.
* :func:`install` / :func:`uninstall` — activate the lifecycle hooks from
  ``scripts/vcd/lifecycle`` (provenance + tier1 + tier2 etc.) for
  automatic checking during normal plotting. Both mechanisms can coexist
  with the legacy lifecycle environment gate.

Plus :class:`Report` — the aggregate result dataclass returned by
``check()``. It supports filtering, summarisation, truthiness (any
findings?), and JSON / Markdown export.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from scivcd.core import (
    Category,
    Finding,
    ScivcdConfig,
    Severity,
    Stage,
    iter_checks,
)

if TYPE_CHECKING:  # pragma: no cover
    import matplotlib.figure  # noqa: F401


__all__ = ["Report", "check", "audit_export", "install", "uninstall"]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class Report:
    """Aggregate result returned by :func:`check`.

    Attributes
    ----------
    findings:
        List of :class:`Finding` records emitted by checks, in the order
        they were produced.
    figure_label:
        Optional label for the figure being reported on (usually the
        target filename or the ``suptitle``).
    timings:
        Dict of ``{check_id: seconds}`` so callers can see which checks
        dominate runtime.
    metadata:
        Optional report-level structured context such as source stage,
        export target path, audit limitations, or adapter provenance.
    """

    findings: list[Finding] = field(default_factory=list)
    figure_label: str = ""
    timings: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- predicates ---------------------------------------------------------

    def has(self, check_id: str) -> bool:
        """Return True if any finding matches ``check_id``."""
        return any(f.check_id == check_id for f in self.findings)

    def has_severity(self, sev: Severity) -> bool:
        """Return True if any finding is at exactly ``sev``."""
        sev = Severity.coerce(sev)
        return any(f.severity is sev for f in self.findings)

    def __bool__(self) -> bool:
        """True iff there is at least one finding.

        Lets callers write ``if report: ...`` after a CI gate check.
        """
        return bool(self.findings)

    def __len__(self) -> int:
        return len(self.findings)

    def __iter__(self):  # pragma: no cover - trivial
        return iter(self.findings)

    # -- grouping -----------------------------------------------------------

    def by_category(self) -> dict[Category, list[Finding]]:
        """Group findings by :class:`Category`."""
        out: dict[Category, list[Finding]] = defaultdict(list)
        for f in self.findings:
            out[f.category].append(f)
        return dict(out)

    def by_severity(self) -> dict[Severity, list[Finding]]:
        """Group findings by :class:`Severity`."""
        out: dict[Severity, list[Finding]] = defaultdict(list)
        for f in self.findings:
            out[f.severity].append(f)
        return dict(out)

    # -- summary / serialisation -------------------------------------------

    def summary(self) -> str:
        """One-line human-readable summary of the report."""
        if not self.findings:
            label = f" for {self.figure_label}" if self.figure_label else ""
            return f"scivcd: no findings{label}."
        counts = defaultdict(int)
        for f in self.findings:
            counts[f.severity] += 1
        # Iterate severity order (BLOCKER -> INFO) for a stable presentation.
        parts = []
        for sev in sorted(Severity, key=lambda s: s.value):
            n = counts.get(sev, 0)
            if n:
                parts.append(f"{n} {sev.name.lower()}")
        label = f" ({self.figure_label})" if self.figure_label else ""
        return f"scivcd{label}: {len(self.findings)} finding(s) — " + ", ".join(parts)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "figure_label": self.figure_label,
            "metadata": dict(self.metadata),
            "findings": [f.to_dict() for f in self.findings],
            "timings": dict(self.timings),
        }

    def to_json(self, path: Optional[Path] = None) -> str:
        """Return JSON string; optionally write to ``path``."""
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def to_markdown(self, path: Optional[Path] = None) -> str:
        """Return a Markdown report; optionally write to ``path``."""
        lines: list[str] = []
        label = self.figure_label or "figure"
        lines.append(f"# scivcd report — {label}")
        lines.append("")
        lines.append(self.summary())
        lines.append("")
        if self.metadata:
            lines.append("## Metadata")
            lines.append("")
            for key in sorted(self.metadata):
                lines.append(f"- **{key}**: {self.metadata[key]}")
            lines.append("")
        if not self.findings:
            text = "\n".join(lines) + "\n"
        else:
            grouped = self.by_severity()
            for sev in sorted(Severity, key=lambda s: s.value):
                items = grouped.get(sev, [])
                if not items:
                    continue
                lines.append(f"## {sev.name} ({len(items)})")
                lines.append("")
                for f in items:
                    cs = f" _(at {f.call_site})_" if f.call_site else ""
                    lines.append(f"- **{f.check_id}** [{f.category.name}]: {f.message}{cs}")
                    if f.fix_suggestion:
                        lines.append(f"  - Fix: {f.fix_suggestion}")
                lines.append("")
            text = "\n".join(lines).rstrip() + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text


# ---------------------------------------------------------------------------
# check() — one-shot, no hooks
# ---------------------------------------------------------------------------


def check(
    fig: "matplotlib.figure.Figure",
    *,
    config: Optional[ScivcdConfig] = None,
    stage: Optional[Stage] = None,
    severity_floor: Severity = Severity.INFO,
) -> Report:
    """Run registered checks against ``fig`` and return a :class:`Report`.

    This does *not* install lifecycle hooks; it simply walks the registry
    and calls each check's ``fire(fig, config)`` callable directly. The
    figure is treated as read-only: checks that mutate it will surface as
    bugs in the check itself rather than as silent side effects here.

    Parameters
    ----------
    fig:
        The matplotlib figure to inspect.
    config:
        Optional :class:`ScivcdConfig` controlling which checks run and
        their thresholds. If ``None``, a default-constructed config is
        used.
    stage:
        If given, only checks for this :class:`Stage` fire. Otherwise
        every stage is run.
    severity_floor:
        Findings with ``severity.value > severity_floor.value`` are
        dropped (i.e. less-serious ones are filtered out). The default
        of ``INFO`` keeps everything.
    """
    severity_floor = Severity.coerce(severity_floor)
    cfg = config if config is not None else _make_default_config()
    label = _figure_label(fig)

    findings: list[Finding] = []
    timings: dict[str, float] = {}

    stages_to_run = [stage] if stage is not None else list(Stage)
    for s in stages_to_run:
        for spec in iter_checks(stage=s, config=cfg, enabled_only=True):
            t0 = time.perf_counter()
            try:
                produced = spec.fire(fig, cfg) or []
            except Exception as exc:  # pragma: no cover - defensive
                # A broken check must not blow up the whole report. Emit a
                # synthetic INFO finding so the caller knows something
                # went wrong without losing the other results.
                produced = [
                    Finding(
                        check_id=spec.id,
                        severity=Severity.INFO,
                        category=spec.category,
                        stage=spec.stage,
                        message=f"check {spec.id!r} raised {type(exc).__name__}: {exc}",
                    )
                ]
            finally:
                timings[spec.id] = time.perf_counter() - t0
            for finding in produced:
                if not isinstance(finding, Finding):
                    # Tolerate checks that return dict-ish records by
                    # skipping them — W2 will write well-formed checks.
                    continue
                if finding.severity.value > severity_floor.value:
                    continue
                findings.append(finding)

    return Report(findings=findings, figure_label=label, timings=timings)


# ---------------------------------------------------------------------------
# audit_export() — package-native post-export audit entry point
# ---------------------------------------------------------------------------


def audit_export(
    path: str | Path,
    *,
    config: Optional[ScivcdConfig] = None,
    **kwargs: Any,
) -> Report:
    """Audit an exported figure artifact and return a :class:`Report`.

    This thin public wrapper keeps ``scivcd.audit_export`` available from the
    main API module while avoiding an import cycle with
    :mod:`scivcd.export_audit`.
    """
    from scivcd.export_audit import audit_export as _audit_export

    return _audit_export(path, config=config, **kwargs)


# ---------------------------------------------------------------------------
# install() / uninstall() — delegate to legacy lifecycle when available
# ---------------------------------------------------------------------------


# Process-wide state recording the last install() call so uninstall() can
# mirror it and so repeat install() calls are idempotent.
_install_state: dict[str, Any] = {"installed": False, "config": None}


def install(
    *,
    config: Optional[ScivcdConfig] = None,
    categories: Optional[list[Category]] = None,
    severity_floor: Severity = Severity.INFO,
    autofix: bool = False,
) -> None:
    """Install the lifecycle hooks for automatic checking.

    Delegates to ``scripts.vcd.lifecycle.install()`` when that legacy
    package is importable (W2 will move it under ``scripts/vcd`` so the
    import path stays stable). If the legacy package is not available,
    this function stashes the filter config on the module and returns —
    callers that rely solely on :func:`check` are unaffected.

    Parameters
    ----------
    config:
        Optional :class:`ScivcdConfig`. When ``None`` a default-
        constructed config is used.
    categories:
        If given, only checks whose :class:`Category` is in this list
        will fire. Stored on the config so the hook registry respects it.
    severity_floor:
        Findings below this floor are suppressed.
    autofix:
        When True, autofix callables attached to :class:`CheckSpec` are
        allowed to run after detection.
    """
    cfg = config if config is not None else _make_default_config()
    # Attach the extra filters onto the config so the hook layer can read
    # them from the same object. Using setattr keeps this compatible with
    # whatever fields ScivcdConfig ends up exposing.
    try:
        if categories is not None:
            setattr(cfg, "categories", list(categories))
        setattr(cfg, "severity_floor", Severity.coerce(severity_floor))
        setattr(cfg, "autofix", bool(autofix))
    except Exception:  # pragma: no cover - frozen config subclasses
        pass

    _install_state["config"] = cfg

    lifecycle = _try_import_lifecycle()
    if lifecycle is not None:
        # The legacy install() takes no arguments; it reads env vars and
        # the process-global config. We stash cfg on the module so checks
        # can retrieve it via ``scivcd.api._install_state['config']``.
        try:
            lifecycle.install()
        except Exception as exc:  # pragma: no cover - defensive
            _install_state["installed"] = False
            raise RuntimeError(
                f"scivcd.install: lifecycle.install() failed: {exc}"
            ) from exc
    _install_state["installed"] = True


def uninstall() -> None:
    """Reverse a prior :func:`install`. Idempotent."""
    if not _install_state.get("installed"):
        return
    lifecycle = _try_import_lifecycle()
    if lifecycle is not None:
        try:
            lifecycle.uninstall()
        except Exception:  # pragma: no cover - defensive
            pass
    _install_state["installed"] = False
    _install_state["config"] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_default_config() -> ScivcdConfig:
    """Construct a default :class:`ScivcdConfig` without tripping on
    ``__init__`` signatures that evolve during the rewrite."""
    try:
        return ScivcdConfig()  # type: ignore[call-arg]
    except TypeError:  # pragma: no cover - defensive
        # Some ScivcdConfig dataclasses may require explicit fields.
        return ScivcdConfig.__new__(ScivcdConfig)  # type: ignore[return-value]


def _figure_label(fig: Any) -> str:
    """Best-effort human-readable label for a figure.

    Preference order: caller-set ``fig._scivcd_label`` -> ``suptitle`` ->
    ``fig.get_label()`` -> empty string.
    """
    label = getattr(fig, "_scivcd_label", None)
    if isinstance(label, str) and label:
        return label
    sup = getattr(fig, "_suptitle", None)
    if sup is not None:
        try:
            text = sup.get_text()
        except Exception:
            text = ""
        if text:
            return text
    getter = getattr(fig, "get_label", None)
    if callable(getter):
        try:
            text = getter()
        except Exception:
            text = ""
        if text:
            return str(text)
    return ""


def _try_import_lifecycle() -> Any:
    """Return ``scripts.vcd.lifecycle`` module if importable, else None.

    The lifecycle package is owned by Worker 2; import failures here are
    expected during the rewrite and must not break the public API.
    """
    try:  # pragma: no cover - import path varies during rewrite
        from scripts.vcd import lifecycle as _lc  # type: ignore

        return _lc
    except Exception:
        return None
