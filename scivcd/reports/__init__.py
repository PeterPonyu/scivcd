"""scivcd.reports — pluggable report renderers.

Available renderers
-------------------
markdown    Human-readable Markdown table, grouped by severity and category.
json        JSON serialisation of the full report dict.
sarif       Minimal SARIF 2.1.0 for GitHub code-scanning integration.

All renderers expose the same interface::

    render(report: Report, path: Path | None = None) -> str

When ``path`` is given, the rendered string is also written to that file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Report type only needed for annotations


def render_markdown(report, path: "Path | None" = None) -> str:
    """Render *report* as a Markdown table grouped by severity/category."""
    from scivcd.reports.markdown import render
    return render(report, path)


def render_json(report, path: "Path | None" = None) -> str:
    """Render *report* as JSON."""
    from scivcd.reports.json import render
    return render(report, path)


def render_sarif(report, path: "Path | None" = None) -> str:
    """Render *report* as SARIF 2.1.0."""
    from scivcd.reports.sarif import render
    return render(report, path)


__all__ = ["render_markdown", "render_json", "render_sarif"]
