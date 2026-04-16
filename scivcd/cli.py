"""scivcd command-line entry point.

Usage:
    scivcd lint <fig.py> [--profile auto|full|SIMPLE|COMPOUND|COMPOSED]
    scivcd baseline write <dir>
    scivcd baseline diff  <dir>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def _load_module_from_path(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _cmd_lint(args: argparse.Namespace) -> int:
    from . import detect_all_conflicts, count_by_severity_level
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    script = Path(args.figure).resolve()
    if not script.exists():
        print(f"not found: {script}", file=sys.stderr)
        return 2

    _load_module_from_path(script)
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        issues = detect_all_conflicts(fig, verbose=False, profile=args.profile)
        counts = count_by_severity_level(issues)
        print(f"figure {fig_num}: {counts}")
        for i in issues[:10]:
            print(f"  [{i.get('severity_level')}] {i.get('type')}: {i.get('detail', '')[:120]}")
    return 0 if all(count_by_severity_level(detect_all_conflicts(plt.figure(n), verbose=False, profile=args.profile))["CRITICAL"] == 0 for n in plt.get_fignums()) else 1


def _cmd_baseline(args: argparse.Namespace) -> int:
    from .vcd_baseline import load_baseline, save_baseline, diff_against_baseline, render_diff_markdown
    dir_ = Path(args.dir).resolve()
    baseline_path = dir_ / "vcd_baseline.json"
    current_path = dir_ / "vcd_report.json"
    if not current_path.exists():
        print(f"expected {current_path}; run lint first", file=sys.stderr)
        return 2
    if args.action == "write":
        current = json.load(open(current_path))
        save_baseline({"schema_version": 1, "figures": current.get("figures", {})}, baseline_path)
        print(f"wrote {baseline_path}")
        return 0
    if args.action == "diff":
        baseline = load_baseline(baseline_path)
        current = json.load(open(current_path))
        report = diff_against_baseline(current, baseline)
        out = render_diff_markdown(report, baseline_path=baseline_path, out_path=dir_ / "vcd_diff.md")
        print(f"wrote {out}")
        return 2 if report.has_new_critical else 0
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="scivcd", description="Visual conflict detector for scientific matplotlib figures.")
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="Lint every figure produced by a Python script")
    lint.add_argument("figure", help="Path to a .py file that creates matplotlib figures")
    lint.add_argument("--profile", default="auto", choices=["auto", "full", "SIMPLE", "COMPOUND", "COMPOSED"])

    base = sub.add_parser("baseline", help="Write or diff a VCD baseline")
    base.add_argument("action", choices=["write", "diff"])
    base.add_argument("dir", help="Directory containing vcd_report.json (from an earlier run)")

    args = parser.parse_args()
    if args.command == "lint":
        return _cmd_lint(args)
    if args.command == "baseline":
        return _cmd_baseline(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
