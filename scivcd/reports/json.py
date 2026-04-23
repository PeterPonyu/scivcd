"""JSON report renderer for scivcd.

Serialises the full ``Report`` object to JSON using the report's own
``to_dict()`` method.  When ``to_dict`` is not available the renderer
falls back to extracting ``findings`` directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Report annotation only


def render(report, path: "Path | None" = None) -> str:
    """Render *report* as a JSON string.

    Parameters
    ----------
    report:
        A ``scivcd.Report`` instance or any object with ``to_dict()``
        or a ``findings`` iterable.
    path:
        Optional file path.  When given, the JSON is written to this
        path (UTF-8, overwrite).

    Returns
    -------
    str
        The JSON text (pretty-printed with 2-space indent).
    """
    payload = _to_dict(report)
    text = json.dumps(payload, indent=2, default=_json_default)
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


def _to_dict(report) -> dict:
    """Convert *report* to a JSON-serialisable dict."""
    # Preferred: report.to_dict()
    try:
        return report.to_dict()
    except AttributeError:
        pass
    # Fallback: construct a minimal dict from findings
    findings = _extract_findings(report)
    return {"findings": findings}


def _extract_findings(report) -> list[dict]:
    """Extract findings as a list of dicts."""
    try:
        raw = list(report.findings)
        return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in raw]
    except AttributeError:
        pass
    if isinstance(report, (list, tuple)):
        return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in report]
    return []


def _json_default(obj):
    """Fallback serialiser for non-JSON-native objects."""
    # Handle enums
    try:
        return obj.name  # Enum.name
    except AttributeError:
        pass
    return str(obj)
