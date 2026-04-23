"""Component-to-composed lifecycle sidecars for SciVCD.

This module closes the Phase 1 gap between component-level checks and a
composed/exported artifact.  It keeps the contract generic: callers provide
component mappings plus optional component/composed reports, and SciVCD emits a
versioned sidecar containing provenance, projected findings, composed-own audit
data, gate summary, and human-review hints.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from scivcd.core import Category, Finding, Severity, Stage
from scivcd.gating import GatePolicy
from scivcd.projection import ProjectionTransform, normalize_rect

SCHEMA_VERSION = "scivcd.composed_lifecycle.v1"

_BBOX_EVIDENCE_KEYS = (
    "bbox_norm",
    "rect_norm",
    "target_rect_norm",
    "extent_norm",
)

_HUMAN_HINT_RULES: dict[str, tuple[str, str]] = {
    "effective_font_too_small": (
        "small_font",
        "Review small text after component-to-composed downscaling.",
    ),
    "canvas_scale_font_too_small": (
        "small_font",
        "Review small text after component-to-composed downscaling.",
    ),
    "undersized_font_vs_canvas": (
        "small_font",
        "Review small text after component-to-composed downscaling.",
    ),
    "text_density_crowding": (
        "crowded_annotation",
        "Review crowded annotations and dense text regions in the composed artifact.",
    ),
    "annotation_data_overlap": (
        "crowded_annotation",
        "Review crowded annotations and dense text regions in the composed artifact.",
    ),
    "annotation_style_risk": (
        "crowded_annotation",
        "Review crowded annotations and dense text regions in the composed artifact.",
    ),
    "legend_tick_clearance": (
        "legend_proximity",
        "Review legend proximity to ticks, labels, or dense panel content.",
    ),
    "missing_legend": (
        "legend_proximity",
        "Review legend proximity to ticks, labels, or dense panel content.",
    ),
}


@dataclass(frozen=True)
class ComponentLink:
    """Provenance and affine mapping for one component in a composed artifact."""

    component_stem: str
    source_pdf: str = ""
    producer_file: str = ""
    source_sidecar: str = ""
    target_rect_norm: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    scale_x: float = 1.0
    scale_y: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    source_rect_norm: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    dpi: Optional[float] = None
    page_index: Optional[int] = None
    component_index: Optional[int] = None

    @classmethod
    def from_projection(
        cls,
        projection: ProjectionTransform,
        *,
        source_pdf: str | Path = "",
        producer_file: str | Path = "",
        source_sidecar: str | Path = "",
    ) -> "ComponentLink":
        """Build a lifecycle component mapping from a projection transform."""
        return cls(
            component_stem=projection.component_stem,
            source_pdf=str(source_pdf),
            producer_file=str(producer_file),
            source_sidecar=str(source_sidecar),
            target_rect_norm=projection.target_rect_norm,
            scale_x=projection.scale_x,
            scale_y=projection.scale_y,
            offset_x=projection.offset_x,
            offset_y=projection.offset_y,
            source_rect_norm=projection.source_rect_norm,
            dpi=projection.dpi,
            page_index=projection.page_index,
            component_index=projection.component_index,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ComponentLink":
        """Load a component mapping from a JSON-like object."""
        target = normalize_rect(
            data.get("target_rect_norm", (0.0, 0.0, 1.0, 1.0)),
            name="target_rect_norm",
        )
        source = normalize_rect(
            data.get("source_rect_norm", (0.0, 0.0, 1.0, 1.0)),
            name="source_rect_norm",
        )
        transform = ProjectionTransform.from_rects(
            component_stem=str(data["component_stem"]),
            composed_stem=str(data.get("composed_stem", "")),
            source_rect_norm=source,
            target_rect_norm=target,
            dpi=data.get("dpi"),
            page_index=data.get("page_index"),
            component_index=data.get("component_index"),
        )
        return cls(
            component_stem=transform.component_stem,
            source_pdf=str(data.get("source_pdf", "")),
            producer_file=str(data.get("producer_file", "")),
            source_sidecar=str(data.get("source_sidecar", "")),
            target_rect_norm=target,
            scale_x=float(data.get("scale_x", transform.scale_x)),
            scale_y=float(data.get("scale_y", transform.scale_y)),
            offset_x=float(data.get("offset_x", transform.offset_x)),
            offset_y=float(data.get("offset_y", transform.offset_y)),
            source_rect_norm=source,
            dpi=data.get("dpi"),
            page_index=data.get("page_index"),
            component_index=data.get("component_index"),
        )

    def to_projection(self, *, composed_stem: str = "") -> ProjectionTransform:
        """Return this link as a projection transform."""
        return ProjectionTransform.from_rects(
            component_stem=self.component_stem,
            composed_stem=composed_stem,
            source_rect_norm=self.source_rect_norm,
            target_rect_norm=self.target_rect_norm,
            dpi=self.dpi,
            page_index=self.page_index,
            component_index=self.component_index,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the public lifecycle sidecar component schema."""
        data: dict[str, Any] = {
            "component_stem": self.component_stem,
            "source_pdf": self.source_pdf,
            "producer_file": self.producer_file,
            "source_sidecar": self.source_sidecar,
            "target_rect_norm": list(self.target_rect_norm),
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }
        if self.source_rect_norm != (0.0, 0.0, 1.0, 1.0):
            data["source_rect_norm"] = list(self.source_rect_norm)
        if self.dpi is not None:
            data["dpi"] = self.dpi
        if self.page_index is not None:
            data["page_index"] = self.page_index
        if self.component_index is not None:
            data["component_index"] = self.component_index
        return data


def project_component_findings(
    component_reports: Mapping[str, Any] | None,
    components: Iterable[ComponentLink | ProjectionTransform | Mapping[str, Any]],
    *,
    composed_stem: str = "",
    severity_floor: Severity = Severity.INFO,
) -> list[Finding]:
    """Project component report findings into composed artifact coordinates.

    ``component_reports`` is keyed by ``component_stem`` and may contain
    ``Report`` objects, report dictionaries, lists of ``Finding`` objects, or
    lists of finding dictionaries.
    """
    if not component_reports:
        return []
    severity_floor = Severity.coerce(severity_floor)
    projected: list[Finding] = []
    for link in _coerce_component_links(components):
        raw_report = component_reports.get(link.component_stem)
        if raw_report is None:
            continue
        projection = link.to_projection(composed_stem=composed_stem)
        for source in _extract_findings(raw_report):
            if source.severity.value > severity_floor.value:
                continue
            evidence = dict(source.evidence or {})
            projection_evidence = projection.to_dict()
            bbox = _first_bbox(evidence)
            if bbox is not None:
                projection_evidence["projected_bbox_norm"] = list(projection.project_bbox(bbox))
            projected_evidence = {
                "projection_transform": projection_evidence,
                "component_stem": link.component_stem,
                "source_pdf": link.source_pdf,
                "source_sidecar": link.source_sidecar,
                "source_finding": source.to_dict(),
            }
            if bbox is not None:
                projected_evidence["source_bbox_norm"] = list(bbox)
            projected.append(Finding(
                check_id=f"projected.{source.check_id}",
                severity=source.severity,
                category=source.category,
                stage=Stage.TIER2,
                message=f"[projected from {link.component_stem}] {source.message}",
                call_site=source.call_site,
                fix_suggestion=source.fix_suggestion,
                evidence=projected_evidence,
            ))
    return projected


def build_gate_summary(
    findings: Iterable[Finding | Mapping[str, Any]],
    *,
    policy: GatePolicy | None = None,
) -> dict[str, Any]:
    """Summarise composed findings into blocker/warning/info gate buckets."""
    policy = policy or GatePolicy()
    finding_dicts = [_finding_to_dict(finding) for finding in findings]
    fail_on = {name.upper() for name in policy.fail_on}
    warn_on = {name.upper() for name in policy.warn_on}

    blocker = [f for f in finding_dicts if str(f.get("severity", "")).upper() in fail_on]
    warning = [f for f in finding_dicts if str(f.get("severity", "")).upper() in warn_on]
    info = [
        f for f in finding_dicts
        if f not in blocker and f not in warning
    ]
    counts_by_severity = {severity.name: 0 for severity in Severity}
    for finding in finding_dicts:
        severity = str(finding.get("severity", "")).upper()
        if severity in counts_by_severity:
            counts_by_severity[severity] += 1

    return {
        "ok": not blocker,
        "counts": {
            "blocker": len(blocker),
            "warning": len(warning),
            "info": len(info),
        },
        "counts_by_severity": counts_by_severity,
        "blocker_findings": [_finding_ref(f) for f in blocker],
        "warning_findings": [_finding_ref(f) for f in warning],
        "info_findings": [_finding_ref(f) for f in info],
        "policy": {
            "fail_on": list(policy.fail_on),
            "warn_on": list(policy.warn_on),
            "info_report_only": policy.info_report_only,
            "require_export_audit": policy.require_export_audit,
        },
    }


def build_human_review_hints(
    findings: Iterable[Finding | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return deduplicated human-review hints for known lifecycle risks."""
    hints: dict[str, dict[str, Any]] = {}
    for finding in (_finding_to_dict(f) for f in findings):
        check_id = str(finding.get("check_id", ""))
        base_check_id = check_id.removeprefix("projected.")
        rule = _HUMAN_HINT_RULES.get(base_check_id)
        if rule is None:
            continue
        hint_id, message = rule
        hint = hints.setdefault(hint_id, {
            "hint_id": hint_id,
            "message": message,
            "finding_refs": [],
        })
        hint["finding_refs"].append(_finding_ref(finding))
    return [hints[key] for key in sorted(hints)]


def build_composed_lifecycle_sidecar(
    *,
    composed_artifact: str | Path,
    components: Iterable[ComponentLink | ProjectionTransform | Mapping[str, Any]],
    component_reports: Mapping[str, Any] | None = None,
    composed_own_audit: Any | None = None,
    gate_policy: GatePolicy | None = None,
    created_at: str | None = None,
    tool_version: str | None = None,
) -> dict[str, Any]:
    """Build the full versioned composed lifecycle sidecar payload."""
    artifact = Path(composed_artifact)
    links = _coerce_component_links(components)
    composed_stem = artifact.stem
    projected_findings = project_component_findings(
        component_reports,
        links,
        composed_stem=composed_stem,
    )
    own_audit_payload = _report_to_payload(composed_own_audit)
    all_findings = projected_findings + _extract_findings(own_audit_payload)

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at or _utc_now(),
        "tool_version": tool_version or _tool_version(),
        "composed_artifact": str(composed_artifact),
        "components": [link.to_dict() for link in links],
        "projected_findings": [finding.to_dict() for finding in projected_findings],
        "composed_own_audit": own_audit_payload,
        "gate_summary": build_gate_summary(all_findings, policy=gate_policy),
        "human_review_hints": build_human_review_hints(all_findings),
    }


def make_composed_report(
    *,
    composed_artifact: str | Path,
    components: Iterable[ComponentLink | ProjectionTransform | Mapping[str, Any]],
    component_reports: Mapping[str, Any] | None = None,
    composed_own_audit: Any | None = None,
    gate_policy: GatePolicy | None = None,
) -> Any:
    """Return a ``Report`` whose findings include projected and own-audit data."""
    from scivcd.api import Report

    sidecar = build_composed_lifecycle_sidecar(
        composed_artifact=composed_artifact,
        components=components,
        component_reports=component_reports,
        composed_own_audit=composed_own_audit,
        gate_policy=gate_policy,
    )
    own_findings = _extract_findings(sidecar["composed_own_audit"])
    projected = _extract_findings({"findings": sidecar["projected_findings"]})
    return Report(
        findings=projected + own_findings,
        figure_label=Path(composed_artifact).name or str(composed_artifact),
        metadata={
            "source_stage": "composed_lifecycle",
            "composed_artifact": str(composed_artifact),
            "composed_lifecycle": sidecar,
            "schema_version": SCHEMA_VERSION,
            "gate_summary": sidecar["gate_summary"],
            "human_review_hints": sidecar["human_review_hints"],
        },
    )


def write_composed_lifecycle_sidecar(
    path: str | Path,
    sidecar: Mapping[str, Any] | None = None,
    **sidecar_kwargs: Any,
) -> Path:
    """Write a composed lifecycle sidecar JSON document.

    Passing an explicit ``sidecar`` writes it as-is.  Otherwise
    ``sidecar_kwargs`` are forwarded to :func:`build_composed_lifecycle_sidecar`.
    The helper refuses ``_live_vcd`` paths to keep composed lifecycle metadata
    additive rather than mutating the live VCD scratch contract.
    """
    target = Path(path)
    if any(part == "_live_vcd" for part in target.parts):
        raise ValueError("composed lifecycle sidecars must not be written under _live_vcd")
    payload = dict(sidecar) if sidecar is not None else build_composed_lifecycle_sidecar(**sidecar_kwargs)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _coerce_component_links(
    components: Iterable[ComponentLink | ProjectionTransform | Mapping[str, Any]],
) -> list[ComponentLink]:
    links: list[ComponentLink] = []
    for component in components:
        if isinstance(component, ComponentLink):
            links.append(component)
        elif isinstance(component, ProjectionTransform):
            links.append(ComponentLink.from_projection(component))
        else:
            links.append(ComponentLink.from_dict(component))
    return links


def _extract_findings(report_or_payload: Any) -> list[Finding]:
    if report_or_payload is None:
        return []
    if hasattr(report_or_payload, "findings"):
        return [_coerce_finding(f) for f in list(report_or_payload.findings)]
    if hasattr(report_or_payload, "to_dict"):
        report_or_payload = report_or_payload.to_dict()
    if isinstance(report_or_payload, Mapping):
        return [_coerce_finding(f) for f in report_or_payload.get("findings", [])]
    if isinstance(report_or_payload, (list, tuple)):
        return [_coerce_finding(f) for f in report_or_payload]
    return []


def _coerce_finding(value: Finding | Mapping[str, Any]) -> Finding:
    if isinstance(value, Finding):
        return value
    return Finding(
        check_id=str(value["check_id"]),
        severity=Severity.coerce(value["severity"]),
        category=Category.coerce(value["category"]),
        stage=Stage.coerce(value.get("stage", Stage.TIER2)),
        message=str(value["message"]),
        call_site=value.get("call_site"),
        fix_suggestion=value.get("fix_suggestion"),
        evidence=dict(value.get("evidence") or {}) or None,
    )


def _report_to_payload(report_or_payload: Any) -> dict[str, Any]:
    if report_or_payload is None:
        return {}
    if hasattr(report_or_payload, "to_dict"):
        payload = report_or_payload.to_dict()
        return dict(payload) if isinstance(payload, Mapping) else {}
    if isinstance(report_or_payload, Mapping):
        return dict(report_or_payload)
    if isinstance(report_or_payload, (list, tuple)):
        return {"findings": [_finding_to_dict(finding) for finding in report_or_payload]}
    return {}


def _finding_to_dict(finding: Finding | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(finding, Finding):
        return finding.to_dict()
    return dict(finding)


def _finding_ref(finding: Mapping[str, Any]) -> dict[str, Any]:
    evidence = finding.get("evidence") or {}
    return {
        "check_id": finding.get("check_id"),
        "severity": finding.get("severity"),
        "component_stem": evidence.get("component_stem"),
        "message": finding.get("message"),
    }


def _first_bbox(evidence: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    for key in _BBOX_EVIDENCE_KEYS:
        value = evidence.get(key)
        if value is None:
            continue
        try:
            return normalize_rect(value, name=key)
        except (TypeError, ValueError):
            continue
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tool_version() -> str:
    try:
        from scivcd import __version__

        return str(__version__)
    except Exception:  # pragma: no cover - defensive import fallback
        return "unknown"


__all__ = [
    "SCHEMA_VERSION",
    "ComponentLink",
    "build_composed_lifecycle_sidecar",
    "build_gate_summary",
    "build_human_review_hints",
    "make_composed_report",
    "project_component_findings",
    "write_composed_lifecycle_sidecar",
]
