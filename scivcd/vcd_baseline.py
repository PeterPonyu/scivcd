"""VCD baseline / diff module (US-203).

Pins a reference VCD snapshot and diffs subsequent runs against it. The goal
is to distinguish absolute count drift from genuine regressions — a new
``CRITICAL`` finding on a previously-clean figure is a blocker; a 2-warning
churn on a figure that was already flagged is noise.

The baseline stores one entry per article-manifest figure with:

- ``severity_counts`` for the four-level mapping
- ``finding_keys`` — a stable hash set of ``(type, detail)`` pairs that
  identifies individual findings across runs

Diffs are reported per-figure with added / removed finding keys and a
final exit code that is non-zero iff any figure gains a new CRITICAL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

def _finding_key(finding: dict) -> Tuple[str, str, str]:
    """Stable identity key for a finding across runs."""
    return (
        str(finding.get("type", "")),
        str(finding.get("severity_level", "")),
        str(finding.get("detail", ""))[:180],  # truncate for stability
    )


def _collect_figure_entry(data: dict) -> dict:
    """Extract the baseline-relevant subset of a VCD report entry."""
    sev_counts = dict(data.get("severity_counts") or {})
    findings = list(data.get("findings") or [])
    return {
        "severity_counts": {
            "CRITICAL": int(sev_counts.get("CRITICAL", 0)),
            "MAJOR": int(sev_counts.get("MAJOR", 0)),
            "MINOR": int(sev_counts.get("MINOR", 0)),
            "INFO": int(sev_counts.get("INFO", 0)),
        },
        "finding_keys": [list(_finding_key(f)) for f in findings],
    }


def snapshot_from_vcd_report(vcd: dict) -> dict:
    """Convert a run_regeneration.run_vcd_on_figures output into a baseline dict."""
    figures: Dict[str, dict] = {}
    for name, data in vcd.items():
        if name.startswith("__") or not isinstance(data, dict):
            continue
        figures[name] = _collect_figure_entry(data)
    return {"schema_version": 1, "figures": figures}


def load_baseline(path: Path | str) -> dict:
    """Load a baseline JSON file; return an empty scaffold if absent."""
    p = Path(path)
    if not p.exists():
        return {"schema_version": 1, "figures": {}}
    with open(p, "r") as f:
        return json.load(f)


def save_baseline(baseline: dict, path: Path | str) -> Path:
    """Serialize the baseline to disk; returns the output path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(baseline, f, indent=2, sort_keys=True)
    return p


# ---------------------------------------------------------------------------
# Diff model
# ---------------------------------------------------------------------------

@dataclass
class FigureDiff:
    name: str
    added: List[Tuple[str, str, str]] = field(default_factory=list)
    removed: List[Tuple[str, str, str]] = field(default_factory=list)
    sev_before: Dict[str, int] = field(default_factory=dict)
    sev_after: Dict[str, int] = field(default_factory=dict)

    @property
    def has_new_critical(self) -> bool:
        return any(level == "CRITICAL" for _, level, _ in self.added)


@dataclass
class DiffReport:
    figures: List[FigureDiff]

    @property
    def has_new_critical(self) -> bool:
        return any(f.has_new_critical for f in self.figures)

    @property
    def totals_added(self) -> Dict[str, int]:
        out = {"CRITICAL": 0, "MAJOR": 0, "MINOR": 0, "INFO": 0}
        for f in self.figures:
            for _, level, _ in f.added:
                out[level] = out.get(level, 0) + 1
        return out

    @property
    def totals_removed(self) -> Dict[str, int]:
        out = {"CRITICAL": 0, "MAJOR": 0, "MINOR": 0, "INFO": 0}
        for f in self.figures:
            for _, level, _ in f.removed:
                out[level] = out.get(level, 0) + 1
        return out

    @property
    def figures_with_changes(self) -> List[FigureDiff]:
        return [f for f in self.figures if f.added or f.removed]


def diff_against_baseline(current: dict, baseline: dict) -> DiffReport:
    """Compare the current snapshot against ``baseline`` and return a DiffReport."""
    cur_figs = current.get("figures", {}) or {}
    base_figs = baseline.get("figures", {}) or {}
    all_names = sorted(set(cur_figs) | set(base_figs))

    out: List[FigureDiff] = []
    for name in all_names:
        cur = cur_figs.get(name, {"severity_counts": {}, "finding_keys": []})
        base = base_figs.get(name, {"severity_counts": {}, "finding_keys": []})
        cur_keys = {tuple(k) for k in cur.get("finding_keys", [])}
        base_keys = {tuple(k) for k in base.get("finding_keys", [])}
        added = sorted(cur_keys - base_keys)
        removed = sorted(base_keys - cur_keys)
        diff = FigureDiff(
            name=name,
            added=added,
            removed=removed,
            sev_before=dict(base.get("severity_counts", {})),
            sev_after=dict(cur.get("severity_counts", {})),
        )
        out.append(diff)
    return DiffReport(figures=out)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_diff_markdown(report: DiffReport, *, baseline_path: Path | str, out_path: Path | str) -> Path:
    """Render the diff report to human-readable markdown."""
    lines: List[str] = [
        "# VCD Baseline Diff",
        "",
        f"**Baseline:** `{baseline_path}`",
        f"**Exit status:** {'NEW_CRITICAL' if report.has_new_critical else 'OK'}",
        "",
        "## Totals",
        "",
    ]
    added = report.totals_added
    removed = report.totals_removed
    for level in ("CRITICAL", "MAJOR", "MINOR", "INFO"):
        lines.append(f"- **{level}**: +{added.get(level, 0)} / −{removed.get(level, 0)}")
    lines.append("")

    changed = report.figures_with_changes
    if not changed:
        lines.append("_No per-figure diffs — the current run matches the baseline._")
    else:
        lines.extend(["## Per-figure changes", ""])
        for fig in changed:
            lines.append(f"### `{fig.name}`")
            sev_delta = [
                f"{lvl} {fig.sev_before.get(lvl, 0)}→{fig.sev_after.get(lvl, 0)}"
                for lvl in ("CRITICAL", "MAJOR", "MINOR", "INFO")
            ]
            lines.append(f"- severity: {', '.join(sev_delta)}")
            for typ, level, detail in fig.added:
                lines.append(f"- ADDED [{level}] {typ}: {detail[:200]}")
            for typ, level, detail in fig.removed:
                lines.append(f"- REMOVED [{level}] {typ}: {detail[:200]}")
            lines.append("")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    return out


__all__ = [
    "snapshot_from_vcd_report",
    "load_baseline",
    "save_baseline",
    "diff_against_baseline",
    "render_diff_markdown",
    "FigureDiff",
    "DiffReport",
]
