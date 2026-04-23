"""SARIF 2.1.0 report renderer for scivcd.

Produces a minimal Static Analysis Results Interchange Format (SARIF) 2.1.0
document so findings surface in GitHub's code-scanning UI when uploaded as
a SARIF artifact.

SARIF specification: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html

The output contains:
- One ``run`` with ``tool.driver`` populated from scivcd metadata.
- One ``rule`` per registered check (uses ``iter_checks`` from the registry).
- One ``result`` per finding.

Severity mapping
----------------
BLOCKER  -> error
HIGH     -> error
MEDIUM   -> warning
LOW      -> note
INFO     -> none
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


_SARIF_VERSION = "2.1.0"
_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master"
    "/Schemata/sarif-schema-2.1.0.json"
)
_TOOL_NAME = "scivcd"
_TOOL_URI = "https://github.com/PeterPonyu/CLOP-DiT"

_SEV_TO_SARIF = {
    "BLOCKER": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
    "INFO": "none",
}


def render(report, path: "Path | None" = None) -> str:
    """Render *report* as a SARIF 2.1.0 JSON string.

    Parameters
    ----------
    report:
        A ``scivcd.Report`` instance or any object with ``to_dict()`` /
        a ``findings`` attribute.
    path:
        Optional file path.  When given, the SARIF JSON is written there.

    Returns
    -------
    str
        SARIF 2.1.0 JSON text.
    """
    findings = _extract_findings(report)
    rules = _build_rules()
    results = [_finding_to_result(f) for f in findings]

    sarif_doc = {
        "version": _SARIF_VERSION,
        "$schema": _SARIF_SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": _TOOL_NAME,
                        "version": _get_version(),
                        "informationUri": _TOOL_URI,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }

    text = json.dumps(sarif_doc, indent=2, default=str)
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_findings(report) -> list[dict]:
    """Return findings as a list of plain dicts."""
    try:
        raw = list(report.findings)
        return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in raw]
    except AttributeError:
        pass
    try:
        d = report.to_dict()
        return d.get("findings", [])
    except AttributeError:
        pass
    if isinstance(report, (list, tuple)):
        return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in report]
    return []


def _build_rules() -> list[dict]:
    """Build SARIF ``rules`` array from the check registry."""
    rules: list[dict] = []
    try:
        from scivcd.core.registry import iter_checks
        for spec in iter_checks(enabled_only=False):
            rules.append(
                {
                    "id": spec.id,
                    "name": _check_id_to_name(spec.id),
                    "shortDescription": {"text": spec.description or spec.id},
                    "defaultConfiguration": {
                        "level": _SEV_TO_SARIF.get(spec.severity.name, "warning")
                    },
                    "properties": {
                        "category": spec.category.name,
                        "stage": spec.stage.name,
                    },
                }
            )
    except ImportError:
        pass
    return rules


def _finding_to_result(finding: dict) -> dict:
    """Convert a finding dict to a SARIF ``result`` object."""
    severity = finding.get("severity", "MEDIUM")
    sarif_level = _SEV_TO_SARIF.get(severity.upper(), "warning")

    result: dict = {
        "ruleId": finding.get("check_id", "unknown"),
        "level": sarif_level,
        "message": {"text": finding.get("message", "")},
    }

    # Location: best-effort from call_site "file.py:lineno"
    call_site = finding.get("call_site")
    if call_site:
        location = _parse_call_site(call_site)
        if location:
            result["locations"] = [location]

    # Fix suggestion as a related location / suggestion
    fix = finding.get("fix_suggestion")
    if fix:
        result["fixes"] = [
            {
                "description": {"text": fix},
                "artifactChanges": [],
            }
        ]

    return result


def _parse_call_site(call_site: str) -> "dict | None":
    """Parse ``'path/to/file.py:42'`` into a SARIF physicalLocation."""
    if ":" not in call_site:
        return {
            "physicalLocation": {
                "artifactLocation": {"uri": call_site, "uriBaseId": "%SRCROOT%"}
            }
        }
    # Split on the *last* colon to handle Windows paths
    parts = call_site.rsplit(":", 1)
    file_part = parts[0]
    try:
        line = int(parts[1])
    except (ValueError, IndexError):
        line = 1
    return {
        "physicalLocation": {
            "artifactLocation": {
                "uri": file_part.replace("\\", "/"),
                "uriBaseId": "%SRCROOT%",
            },
            "region": {"startLine": line},
        }
    }


def _check_id_to_name(check_id: str) -> str:
    """Convert ``'layout.overlap'`` to ``'LayoutOverlap'`` (PascalCase)."""
    return "".join(
        part.capitalize()
        for segment in check_id.split(".")
        for part in segment.split("_")
    )


def _get_version() -> str:
    """Return the scivcd version string."""
    try:
        import scivcd
        v = getattr(scivcd, "__version__", None)
        if v:
            return str(v)
    except ImportError:
        pass
    try:
        from importlib.metadata import version
        return version("scivcd")
    except Exception:
        return "0.0.0"
