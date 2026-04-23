"""Baseline diff and CI gating helpers for SciVCD reports."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json

from scivcd.core import Severity


@dataclass
class GatePolicy:
    fail_on: list[str] = field(default_factory=lambda: ["BLOCKER", "HIGH"])
    warn_on: list[str] = field(default_factory=lambda: ["MEDIUM", "LOW"])
    info_report_only: bool = True
    baseline_path: str = ""
    require_export_audit: bool = False

    @classmethod
    def from_pyproject(cls, path: str | Path) -> "GatePolicy":
        try:
            import tomllib
        except ModuleNotFoundError:  # pragma: no cover
            import tomli as tomllib  # type: ignore
        p = Path(path)
        if not p.exists():
            return cls()
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        section = data.get("tool", {}).get("scivcd", {}).get("gate", {})
        return cls(
            fail_on=[str(v).upper() for v in section.get("fail_on", cls().fail_on)],
            warn_on=[str(v).upper() for v in section.get("warn_on", cls().warn_on)],
            info_report_only=bool(section.get("info_report_only", True)),
            baseline_path=str(section.get("baseline_path", "")),
            require_export_audit=bool(section.get("require_export_audit", False)),
        )


def _finding_dicts(report_or_payload: Any) -> list[dict[str, Any]]:
    if hasattr(report_or_payload, "to_dict"):
        report_or_payload = report_or_payload.to_dict()
    if isinstance(report_or_payload, (str, Path)):
        report_or_payload = json.loads(Path(report_or_payload).read_text(encoding="utf-8"))
    return list(report_or_payload.get("findings", [])) if isinstance(report_or_payload, dict) else []


def finding_fingerprint(finding: dict[str, Any]) -> str:
    evidence = finding.get("evidence") or {}
    source = evidence.get("source_artifact") or evidence.get("target_path") or finding.get("call_site") or ""
    semantic = evidence.get("semantic_id") or evidence.get("series_a") or ""
    message_key = " ".join(str(finding.get("message", "")).lower().split())
    # Strip digits to avoid float/coordinate noise in baseline keys.
    message_key = "".join("#" if ch.isdigit() else ch for ch in message_key)
    return "|".join([str(finding.get("check_id", "")), source, semantic, message_key[:120]])


def diff_reports(current: Any, baseline: Any) -> dict[str, list[dict[str, Any]]]:
    cur = _finding_dicts(current)
    base = _finding_dicts(baseline)
    base_map = {finding_fingerprint(f): f for f in base}
    cur_map = {finding_fingerprint(f): f for f in cur}
    return {
        "new": [cur_map[k] for k in sorted(cur_map.keys() - base_map.keys())],
        "resolved": [base_map[k] for k in sorted(base_map.keys() - cur_map.keys())],
        "persistent": [cur_map[k] for k in sorted(cur_map.keys() & base_map.keys())],
    }


def gate_report(current: Any, baseline: Any | None = None, policy: GatePolicy | None = None) -> dict[str, Any]:
    policy = policy or GatePolicy()
    diff = diff_reports(current, baseline or {"findings": []})
    fail = {s.upper() for s in policy.fail_on}
    new_failures = [f for f in diff["new"] if str(f.get("severity", "")).upper() in fail]
    exit_code = 1 if new_failures else 0
    return {"ok": exit_code == 0, "exit_code": exit_code, "diff": diff, "new_failures": new_failures, "policy": policy.__dict__}

__all__ = ["GatePolicy", "diff_reports", "finding_fingerprint", "gate_report"]
