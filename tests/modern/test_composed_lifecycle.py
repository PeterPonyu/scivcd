"""Tests for composed lifecycle sidecars and composed-report projection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scivcd
from scivcd.composed_lifecycle import (
    SCHEMA_VERSION,
    ComponentLink,
    build_composed_lifecycle_sidecar,
    make_composed_report,
    project_component_findings,
    write_composed_lifecycle_sidecar,
)
from scivcd.core import Category, Finding, Severity, Stage
from scivcd.gating import GatePolicy
from scivcd.projection import ProjectionTransform
from scivcd.reports import json as json_report


def _finding(
    check_id: str,
    severity: Severity,
    *,
    message: str | None = None,
    evidence: dict | None = None,
) -> Finding:
    return Finding(
        check_id=check_id,
        severity=severity,
        category=Category.LAYOUT,
        stage=Stage.TIER2,
        message=message or check_id.replace("_", " "),
        evidence=evidence,
    )


def test_component_link_preserves_phase1_sidecar_fields():
    transform = ProjectionTransform.from_rects(
        component_stem="fig_a",
        composed_stem="main",
        target_rect_norm=(0.0, 0.5, 1.0, 1.0),
        dpi=300,
        component_index=0,
    )

    link = ComponentLink.from_projection(
        transform,
        source_pdf="fig_a.pdf",
        producer_file="make_fig_a.py",
        source_sidecar="fig_a.scivcd.json",
    )

    assert link.to_dict() == {
        "component_stem": "fig_a",
        "source_pdf": "fig_a.pdf",
        "producer_file": "make_fig_a.py",
        "source_sidecar": "fig_a.scivcd.json",
        "target_rect_norm": [0.0, 0.5, 1.0, 1.0],
        "scale_x": 1.0,
        "scale_y": 0.5,
        "offset_x": 0.0,
        "offset_y": 0.5,
        "dpi": 300,
        "component_index": 0,
    }


def test_project_component_findings_maps_bbox_and_keeps_source_finding():
    link = {
        "component_stem": "fig_a",
        "source_pdf": "fig_a.pdf",
        "source_sidecar": "fig_a.scivcd.json",
        "target_rect_norm": [0.25, 0.0, 0.75, 0.5],
    }
    component_report = scivcd.Report(findings=[
        _finding(
            "effective_font_too_small",
            Severity.INFO,
            evidence={"bbox_norm": [0.0, 0.0, 0.5, 0.5]},
        )
    ])

    projected = project_component_findings({"fig_a": component_report}, [link], composed_stem="main")

    assert len(projected) == 1
    payload = projected[0].to_dict()
    assert payload["check_id"] == "projected.effective_font_too_small"
    assert payload["evidence"]["component_stem"] == "fig_a"
    assert payload["evidence"]["source_finding"]["check_id"] == "effective_font_too_small"
    assert payload["evidence"]["projection_transform"]["projected_bbox_norm"] == [
        0.25,
        0.0,
        0.5,
        0.25,
    ]


def test_build_composed_lifecycle_sidecar_contains_full_contract():
    components = [
        {
            "component_stem": "panel_a",
            "source_pdf": "panel_a.pdf",
            "producer_file": "make_panel_a.py",
            "source_sidecar": "panel_a.scivcd.json",
            "target_rect_norm": [0.0, 0.5, 1.0, 1.0],
        },
        {
            "component_stem": "panel_b",
            "source_pdf": "panel_b.pdf",
            "producer_file": "make_panel_b.py",
            "source_sidecar": "panel_b.scivcd.json",
            "target_rect_norm": [0.0, 0.0, 1.0, 0.5],
        },
    ]
    component_reports = {
        "panel_a": scivcd.Report(findings=[
            _finding("effective_font_too_small", Severity.INFO),
            _finding("text_density_crowding", Severity.LOW),
        ]),
        "panel_b": scivcd.Report(findings=[
            _finding("legend_tick_clearance", Severity.MEDIUM),
        ]),
    }
    own_audit = scivcd.Report(findings=[
        _finding("composed.panel_overlap", Severity.HIGH, message="composed panel overlap"),
    ])

    sidecar = build_composed_lifecycle_sidecar(
        composed_artifact="figures/composed.pdf",
        components=components,
        component_reports=component_reports,
        composed_own_audit=own_audit,
        gate_policy=GatePolicy(fail_on=["HIGH"], warn_on=["MEDIUM", "LOW"]),
        created_at="2026-04-23T00:00:00Z",
        tool_version="test",
    )

    assert sidecar["schema_version"] == SCHEMA_VERSION
    assert sidecar["created_at"] == "2026-04-23T00:00:00Z"
    assert sidecar["tool_version"] == "test"
    assert sidecar["composed_artifact"] == "figures/composed.pdf"
    assert sidecar["components"][0]["source_pdf"] == "panel_a.pdf"
    assert len(sidecar["projected_findings"]) == 3
    assert sidecar["composed_own_audit"]["findings"][0]["check_id"] == "composed.panel_overlap"
    assert sidecar["gate_summary"]["ok"] is False
    assert sidecar["gate_summary"]["counts"] == {"blocker": 1, "warning": 2, "info": 1}

    hint_ids = {hint["hint_id"] for hint in sidecar["human_review_hints"]}
    assert {"small_font", "crowded_annotation", "legend_proximity"} <= hint_ids


def test_make_composed_report_exposes_projected_and_own_audit_findings():
    component_report = scivcd.Report(findings=[
        _finding("legend_tick_clearance", Severity.MEDIUM),
    ])
    own_audit = scivcd.Report(findings=[
        _finding("composed.export_bounds", Severity.LOW),
    ])

    report = make_composed_report(
        composed_artifact="composed.pdf",
        components=[{"component_stem": "panel", "target_rect_norm": [0.0, 0.0, 1.0, 1.0]}],
        component_reports={"panel": component_report},
        composed_own_audit=own_audit,
    )

    payload = json.loads(json_report.render(report))
    check_ids = {finding["check_id"] for finding in payload["findings"]}
    assert {"projected.legend_tick_clearance", "composed.export_bounds"} <= check_ids
    assert payload["metadata"]["schema_version"] == SCHEMA_VERSION
    assert payload["metadata"]["composed_lifecycle"]["projected_findings"][0]["check_id"] == (
        "projected.legend_tick_clearance"
    )
    assert payload["metadata"]["composed_lifecycle"]["composed_own_audit"]["findings"][0][
        "check_id"
    ] == "composed.export_bounds"


def test_write_composed_lifecycle_sidecar_is_additive(tmp_path: Path):
    sidecar = build_composed_lifecycle_sidecar(
        composed_artifact="composed.pdf",
        components=[{"component_stem": "panel", "target_rect_norm": [0.0, 0.0, 1.0, 1.0]}],
        created_at="2026-04-23T00:00:00Z",
        tool_version="test",
    )
    target = tmp_path / "figures" / "_scivcd_composed" / "composed.json"

    written = write_composed_lifecycle_sidecar(target, sidecar)

    assert written == target
    assert json.loads(written.read_text())["schema_version"] == SCHEMA_VERSION
    with pytest.raises(ValueError, match="_live_vcd"):
        write_composed_lifecycle_sidecar(tmp_path / "_live_vcd" / "bad.json", sidecar)
