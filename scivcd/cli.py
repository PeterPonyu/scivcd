"""Command-line interface for scivcd.

Subcommands
-----------
list-checks   List every registered check.
check         Run VCD checks on a PDF or figure script.
audit-export  Audit an already-exported PNG/JPEG/PDF artifact.
lint          Walk a directory for figure scripts and aggregate findings.
run           Execute a figure script under scivcd.install() and dump report.
version       Print the scivcd version.

Usage examples::

    scivcd list-checks --format table
    scivcd list-checks --category LAYOUT --stage TIER2 --format json
    scivcd check figures/fig01.pdf
    scivcd check src/visualization/fig07_alignment.py
    scivcd audit-export figures/fig01.png --json
    scivcd lint src/visualization/
    scivcd run src/visualization/fig07_alignment.py
    scivcd version

Exit codes
----------
0   No HIGH or higher severity findings.
1   At least one HIGH / BLOCKER finding present (or script error).
2   Tool/config/input error.
3   Export audit unavailable while explicitly required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy imports from the scivcd public API (provided by W1).  We do not want
# a hard import-time failure when the CLI is invoked for --help or version
# before the full package is assembled.
# ---------------------------------------------------------------------------

def _import_scivcd():
    """Return the scivcd module, raising ImportError with a helpful message."""
    try:
        import scivcd as _scivcd
        return _scivcd
    except ImportError as exc:
        print(
            "error: scivcd package not fully installed — "
            "run `pip install -e .` in the repo root.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _ensure_checks_registered():
    """Import scivcd.checks to trigger all detector registrations."""
    try:
        import scivcd.checks  # noqa: F401
    except ImportError:
        pass  # checks sub-package not yet built (W2/W3 work); graceful no-op


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_is_high_or_above(severity_name: str) -> bool:
    """Return True when severity is HIGH or BLOCKER."""
    return severity_name.upper() in ("HIGH", "BLOCKER")


def _report_has_high_findings(report) -> bool:
    """Check whether a Report contains any HIGH+ findings."""
    try:
        findings = report.findings
    except AttributeError:
        # Fallback: report might be a plain list
        findings = report if isinstance(report, list) else []
    return any(_severity_is_high_or_above(f.severity.name) for f in findings)


def _report_to_findings_list(report) -> list:
    """Extract a flat list of Finding objects from a Report."""
    try:
        return list(report.findings)
    except AttributeError:
        return list(report) if isinstance(report, (list, tuple)) else []


def _report_to_dict_with_metadata(report) -> dict:
    """Convert a Report to a dict while preserving Phase 1 metadata."""
    try:
        from scivcd.export_audit import report_to_dict

        return report_to_dict(report)
    except Exception:
        pass
    try:
        payload = report.to_dict()
    except AttributeError:
        payload = {"findings": []}
    metadata = getattr(report, "metadata", None)
    if metadata is not None and "metadata" not in payload:
        payload["metadata"] = metadata
    return payload


def _run_script(script_path: Path) -> Path:
    """Execute a figure script and return the path to the generated PDF.

    The script is run in a subprocess with the scivcd install hook active
    via the ``SCIVCD_ACTIVE`` environment variable.  The actual PDF path
    is inferred from the figures output directory.
    """
    import subprocess

    env = os.environ.copy()
    env["SCIVCD_ACTIVE"] = "1"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Script exited with code {result.returncode}:", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise SystemExit(1)
    # Return None — the caller will check for newly created PDFs separately.
    return None  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# list-checks
# ---------------------------------------------------------------------------

def _cmd_list_checks(args: argparse.Namespace) -> int:
    _ensure_checks_registered()
    sc = _import_scivcd()

    try:
        iter_checks = sc.iter_checks
    except AttributeError:
        # Fall back to core registry directly
        from scivcd.core.registry import iter_checks  # type: ignore[assignment]

    from scivcd.core.types import Category, Stage

    kwargs: dict = {"enabled_only": False}
    if args.category:
        try:
            kwargs["category"] = Category.coerce(args.category)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.stage:
        try:
            kwargs["stage"] = Stage.coerce(args.stage)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    checks = list(iter_checks(**kwargs))

    if args.format == "json":
        rows = [
            {
                "id": s.id,
                "severity": s.severity.name,
                "category": s.category.name,
                "stage": s.stage.name,
                "description": s.description,
                "default_enabled": s.default_enabled,
                "version": s.version,
            }
            for s in checks
        ]
        print(json.dumps(rows, indent=2))
    else:
        # table
        if not checks:
            print("(no checks registered)")
            return 0
        col_widths = {
            "id": max(len("ID"), max(len(s.id) for s in checks)),
            "sev": max(len("SEV"), max(len(s.severity.name) for s in checks)),
            "cat": max(len("CATEGORY"), max(len(s.category.name) for s in checks)),
            "stg": max(len("STAGE"), max(len(s.stage.name) for s in checks)),
            "desc": max(len("DESCRIPTION"), max(len(s.description) for s in checks)),
        }
        header = (
            f"{'ID':<{col_widths['id']}}  "
            f"{'SEV':<{col_widths['sev']}}  "
            f"{'CATEGORY':<{col_widths['cat']}}  "
            f"{'STAGE':<{col_widths['stg']}}  "
            f"{'DESCRIPTION':<{col_widths['desc']}}"
        )
        sep = "-" * len(header)
        print(header)
        print(sep)
        for s in checks:
            print(
                f"{s.id:<{col_widths['id']}}  "
                f"{s.severity.name:<{col_widths['sev']}}  "
                f"{s.category.name:<{col_widths['cat']}}  "
                f"{s.stage.name:<{col_widths['stg']}}  "
                f"{s.description:<{col_widths['desc']}}"
            )

    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def _cmd_check(args: argparse.Namespace) -> int:
    _ensure_checks_registered()
    sc = _import_scivcd()

    target = Path(args.target)
    if not target.exists():
        print(f"error: path does not exist: {target}", file=sys.stderr)
        return 1

    if target.suffix == ".py":
        reports = _exec_script_and_check(sc, target)
    else:
        # For non-Python targets (PDF, PNG) we cannot reconstruct the Figure
        # object that scivcd.check() requires.  Inform the caller clearly.
        print(
            f"error: scivcd.check() requires a matplotlib Figure; "
            f"pass the .py source script that generates '{target.name}' instead.",
            file=sys.stderr,
        )
        return 1

    if not reports:
        print("OK — no findings (no figures captured).")
        return 0

    any_high = False
    for report in reports:
        label = getattr(report, "figure_label", "") or str(target)
        if label:
            print(f"\n--- {label} ---")
        _print_report_summary(report)
        if _report_has_high_findings(report):
            any_high = True
    return 1 if any_high else 0


# ---------------------------------------------------------------------------
# audit-export
# ---------------------------------------------------------------------------

def _cmd_audit_export(args: argparse.Namespace) -> int:
    _ensure_checks_registered()
    sc = _import_scivcd()

    target = Path(args.target)
    if not target.exists():
        print(f"error: path does not exist: {target}", file=sys.stderr)
        return 2
    if not hasattr(sc, "audit_export"):
        print("error: scivcd.audit_export is unavailable", file=sys.stderr)
        return 2

    report = sc.audit_export(target, require_backend=args.require_backend)
    metadata = getattr(report, "metadata", {})

    if args.markdown:
        _print_audit_export_markdown(report)
    else:
        print(json.dumps(_report_to_dict_with_metadata(report), indent=2, default=str))

    if args.require_backend and metadata.get("audit_unavailable"):
        return 3
    return 1 if _report_has_high_findings(report) else 0


def _print_audit_export_markdown(report) -> None:
    """Print a Markdown audit report including export metadata."""
    metadata = getattr(report, "metadata", {}) or {}
    text = report.to_markdown() if hasattr(report, "to_markdown") else ""
    print(text.rstrip())
    if metadata:
        print("\n## Export metadata\n")
        for key in sorted(metadata):
            value = metadata[key]
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value) if value else "[]"
            print(f"- **{key}**: {value}")


def _exec_script_and_check(sc, script_path: Path) -> list:
    """Execute *script_path* under install(), collect per-figure reports.

    Hooks matplotlib so every figure that is shown or saved during the
    script's execution is captured and checked.  Returns a list of
    :class:`Report` objects, one per captured figure.
    """
    import matplotlib
    import matplotlib.pyplot as plt

    captured_figures: list = []

    # Patch plt.savefig and Figure.savefig to collect figures
    from matplotlib.figure import Figure as MplFigure
    _orig_fig_savefig = MplFigure.savefig

    def _capture_savefig(self, *a, **kw):
        captured_figures.append(self)
        return _orig_fig_savefig(self, *a, **kw)

    MplFigure.savefig = _capture_savefig  # type: ignore[method-assign]

    try:
        sc.install()
    except Exception as exc:
        print(f"warning: install() failed: {exc}", file=sys.stderr)

    script_globals = {"__file__": str(script_path), "__name__": "__main__"}
    try:
        exec(  # noqa: S102
            compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec"),
            script_globals,
        )
    except SystemExit:
        pass
    except Exception as exc:
        print(f"error executing script: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        MplFigure.savefig = _orig_fig_savefig  # type: ignore[method-assign]
        try:
            sc.uninstall()
        except Exception:
            pass

    # Also capture any figures still open (plt.show() path)
    for fig in plt.get_fignums():
        mpl_fig = plt.figure(fig)
        if mpl_fig not in captured_figures:
            captured_figures.append(mpl_fig)

    reports = []
    for fig in captured_figures:
        try:
            report = sc.check(fig)
            reports.append(report)
        except Exception as exc:
            print(f"warning: check failed for figure: {exc}", file=sys.stderr)
    return reports


def _print_report_summary(report) -> None:
    findings = _report_to_findings_list(report)
    total = len(findings)
    if total == 0:
        print("OK — no findings.")
        return

    from collections import Counter
    sev_counts = Counter(f.severity.name for f in findings)
    print(f"Found {total} finding(s):")
    for sev in ("BLOCKER", "HIGH", "MEDIUM", "LOW", "INFO"):
        count = sev_counts.get(sev, 0)
        if count:
            print(f"  {sev:8s}: {count}")

    high_plus = [
        f for f in findings if _severity_is_high_or_above(f.severity.name)
    ]
    if high_plus:
        print("\nHIGH+ findings:")
        for f in high_plus:
            loc = f" [{f.call_site}]" if f.call_site else ""
            print(f"  [{f.severity.name}] {f.check_id}: {f.message}{loc}")
            if f.fix_suggestion:
                print(f"         fix: {f.fix_suggestion}")


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

def _cmd_lint(args: argparse.Namespace) -> int:
    _ensure_checks_registered()
    sc = _import_scivcd()

    root = Path(args.directory)
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    # Find all figure scripts
    scripts = sorted(
        p
        for p in root.rglob("*.py")
        if _is_figure_script(p)
    )

    if not scripts:
        print(f"No figure scripts found under {root}")
        return 0

    print(f"Found {len(scripts)} figure script(s) under {root}\n")

    all_findings: list = []
    errors: list[str] = []

    for script in scripts:
        rel = script.relative_to(root) if root in script.parents else script
        print(f"  checking {rel} ...", end=" ", flush=True)
        try:
            reports = _exec_script_and_check(sc, script)
            findings = [f for r in reports for f in _report_to_findings_list(r)]
            all_findings.extend(findings)
            high_count = sum(1 for f in findings if _severity_is_high_or_above(f.severity.name))
            if high_count:
                print(f"FAIL ({high_count} HIGH+, {len(findings)} total)")
            elif findings:
                print(f"WARN ({len(findings)} finding(s))")
            else:
                print("OK")
        except SystemExit:
            errors.append(str(script))
            print("ERROR")

    print(f"\nAggregate: {len(all_findings)} finding(s) across {len(scripts)} script(s)")
    if errors:
        print(f"Errors in {len(errors)} script(s):")
        for e in errors:
            print(f"  {e}")

    high_plus = [f for f in all_findings if _severity_is_high_or_above(f.severity.name)]
    return 1 if (high_plus or errors) else 0


def _is_figure_script(path: Path) -> bool:
    """Return True for files matching the figure script naming convention."""
    name = path.stem.lower()
    return name.startswith("fig") or "figure" in name


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    _ensure_checks_registered()
    sc = _import_scivcd()

    script = Path(args.script)
    if not script.exists():
        print(f"error: script not found: {script}", file=sys.stderr)
        return 1
    if script.suffix != ".py":
        print(f"error: expected a .py script, got: {script}", file=sys.stderr)
        return 1

    # Execute the script under install() and capture per-figure reports.
    reports = _exec_script_and_check(sc, script)

    if not reports:
        print("(no figures captured)")
        return 0

    all_findings: list = []
    for report in reports:
        all_findings.extend(_report_to_findings_list(report))
        report_dict = report.to_dict() if hasattr(report, "to_dict") else {}
        print(json.dumps(report_dict, indent=2, default=str))

    _print_report_summary(
        type("_R", (), {"findings": all_findings})()
    )
    return 0



# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------
def _cmd_gate(args: argparse.Namespace) -> int:
    from scivcd.gating import GatePolicy, gate_report
    policy = GatePolicy.from_pyproject(args.config) if args.config else GatePolicy()
    current = Path(args.report)
    baseline = Path(args.baseline) if args.baseline else None
    result = gate_report(current, baseline, policy)
    print(json.dumps(result, indent=2, default=str))
    return int(result["exit_code"])


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

def _cmd_version(_args: argparse.Namespace) -> int:
    try:
        sc = _import_scivcd()
        version = getattr(sc, "__version__", None)
    except SystemExit:
        version = None

    if version is None:
        # Attempt importlib.metadata
        try:
            from importlib.metadata import version as pkg_version
            version = pkg_version("scivcd")
        except Exception:
            version = "unknown"

    print(f"scivcd {version}")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scivcd",
        description="SciVCD — visual conflict detection for scientific figures.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list-checks
    p_list = sub.add_parser("list-checks", help="List every registered check.")
    p_list.add_argument(
        "--category",
        metavar="C",
        help="Filter by category (LAYOUT, TYPOGRAPHY, CONTENT, POLICY, ACCESSIBILITY).",
    )
    p_list.add_argument(
        "--stage",
        metavar="S",
        help="Filter by lifecycle stage (TIER1, TIER2).",
    )
    p_list.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )

    # check
    p_check = sub.add_parser(
        "check",
        help="Run VCD checks on a PDF or figure script.",
    )
    p_check.add_argument(
        "target",
        help="Path to a .pdf figure or a .py figure script.",
    )

    # audit-export
    p_audit = sub.add_parser(
        "audit-export",
        help="Audit an already-exported PNG/JPEG/PDF artifact.",
    )
    p_audit.add_argument(
        "target",
        help="Path to a PNG, JPEG, TIFF, WebP, or PDF figure export.",
    )
    output = p_audit.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Emit JSON report.")
    output.add_argument("--markdown", action="store_true", help="Emit Markdown report.")
    p_audit.add_argument(
        "--require-backend",
        action="store_true",
        help="Exit 3 if an optional PDF/raster audit backend is unavailable.",
    )

    # lint
    p_lint = sub.add_parser(
        "lint",
        help="Walk a directory for figure scripts and aggregate findings.",
    )
    p_lint.add_argument(
        "directory",
        help="Directory to walk for figure scripts.",
    )

    # run
    p_run = sub.add_parser(
        "run",
        help="Execute a script under scivcd.install() and dump report to stdout.",
    )
    p_run.add_argument(
        "script",
        help="Path to the figure .py script to execute.",
    )


    # gate
    p_gate = sub.add_parser("gate", help="Apply SciVCD CI gating to a report.")
    p_gate.add_argument("report", help="Current SciVCD report JSON.")
    p_gate.add_argument("--baseline", help="Optional baseline report JSON.")
    p_gate.add_argument("--config", help="Optional pyproject.toml / config path.")

    # version
    sub.add_parser("version", help="Print the scivcd version.")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "list-checks": _cmd_list_checks,
        "check": _cmd_check,
        "audit-export": _cmd_audit_export,
        "lint": _cmd_lint,
        "run": _cmd_run,
        "gate": _cmd_gate,
        "version": _cmd_version,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
