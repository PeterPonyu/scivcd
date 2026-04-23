"""Markdown report renderer for scivcd.

Produces a human-readable Markdown document with:
- A summary line (total findings, count per severity).
- Findings grouped first by severity (BLOCKER → INFO), then by category.

The output is valid GitHub-Flavoured Markdown.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Report annotation only


_SEVERITY_ORDER = ("BLOCKER", "HIGH", "MEDIUM", "LOW", "INFO")


def render(report, path: "Path | None" = None) -> str:
    """Render *report* as Markdown.

    Parameters
    ----------
    report:
        A ``scivcd.Report`` instance (or any object with a ``findings``
        attribute returning an iterable of ``Finding`` objects, or a
        ``to_dict()`` method).
    path:
        Optional file path.  When given, the rendered string is written
        to this path (UTF-8, overwrite).

    Returns
    -------
    str
        The Markdown text.
    """
    findings = _extract_findings(report)
    metadata = _extract_metadata(report)
    lines: list[str] = []

    # --- Title & summary ---
    lines.append("# SciVCD Report\n")
    if metadata:
        lines.append("## Metadata\n")
        for key in sorted(metadata):
            lines.append(f"- **{_md_escape(key)}**: {_md_escape(metadata[key])}")
        lines.append("")
    if not findings:
        lines.append("**No findings.** All checks passed.\n")
        result = "\n".join(lines)
        if path is not None:
            Path(path).write_text(result, encoding="utf-8")
        return result

    from collections import Counter
    sev_counts = Counter(f["severity"] for f in findings)
    summary_parts = [f"{sev_counts[s]} {s}" for s in _SEVERITY_ORDER if s in sev_counts]
    lines.append(f"**{len(findings)} finding(s):** {', '.join(summary_parts)}\n")

    # --- Group by severity then category ---
    by_sev_cat: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for f in findings:
        by_sev_cat[f["severity"]][f["category"]].append(f)

    for sev in _SEVERITY_ORDER:
        if sev not in by_sev_cat:
            continue
        lines.append(f"## {sev}\n")
        for cat in sorted(by_sev_cat[sev].keys()):
            lines.append(f"### {cat}\n")
            lines.append("| Check ID | Stage | Message | Call Site | Fix Suggestion |")
            lines.append("|----------|-------|---------|-----------|----------------|")
            for f in by_sev_cat[sev][cat]:
                check_id = _md_escape(f.get("check_id", ""))
                stage = _md_escape(f.get("stage", ""))
                message = _md_escape(f.get("message", ""))
                call_site = _md_escape(f.get("call_site") or "")
                fix = _md_escape(f.get("fix_suggestion") or "")
                lines.append(
                    f"| {check_id} | {stage} | {message} | {call_site} | {fix} |"
                )
            lines.append("")

    result = "\n".join(lines)
    if path is not None:
        Path(path).write_text(result, encoding="utf-8")
    return result


def _extract_metadata(report) -> dict:
    """Extract report-level metadata when present."""
    try:
        metadata = getattr(report, "metadata")
        if isinstance(metadata, dict):
            return dict(metadata)
    except AttributeError:
        pass
    try:
        d = report.to_dict()
        metadata = d.get("metadata", {})
        return dict(metadata) if isinstance(metadata, dict) else {}
    except AttributeError:
        return {}


def _extract_findings(report) -> list[dict]:
    """Normalise *report* to a list of plain dicts."""
    # Preferred: report.findings (iterable of Finding objects)
    try:
        raw = list(report.findings)
        return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in raw]
    except AttributeError:
        pass
    # Fallback: report.to_dict()
    try:
        d = report.to_dict()
        return d.get("findings", [])
    except AttributeError:
        pass
    # Last resort: treat report as a list
    if isinstance(report, (list, tuple)):
        return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in report]
    return []


def _md_escape(text: str) -> str:
    """Escape pipe characters so they don't break Markdown tables."""
    return str(text).replace("|", "\\|").replace("\n", " ")
