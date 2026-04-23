"""Tests for Phase 1 component-to-composed projection helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scivcd.core import Category, Finding, Severity, Stage
from scivcd.projection import (
    ProjectionTransform,
    attach_projection_evidence,
    normalize_rect,
    vertical_stack_transforms,
    write_projection_sidecar,
)


def test_projection_transform_from_rects_maps_point_and_bbox():
    transform = ProjectionTransform.from_rects(
        component_stem="component_a",
        composed_stem="composed",
        source_rect_norm=(0.0, 0.0, 1.0, 1.0),
        target_rect_norm=(0.25, 0.5, 0.75, 1.0),
        dpi=300,
        page_index=0,
        component_index=1,
    )

    assert transform.scale_x == pytest.approx(0.5)
    assert transform.scale_y == pytest.approx(0.5)
    assert transform.offset_x == pytest.approx(0.25)
    assert transform.offset_y == pytest.approx(0.5)
    assert transform.project_point((0.5, 0.5)) == pytest.approx((0.5, 0.75))
    assert transform.project_bbox((0.0, 0.0, 0.5, 0.5)) == pytest.approx(
        (0.25, 0.5, 0.5, 0.75)
    )

    payload = transform.to_dict()
    assert payload["component_stem"] == "component_a"
    assert payload["composed_stem"] == "composed"
    assert payload["source_rect_norm"] == [0.0, 0.0, 1.0, 1.0]
    assert payload["target_rect_norm"] == [0.25, 0.5, 0.75, 1.0]
    assert payload["dpi"] == 300
    assert payload["page_index"] == 0
    assert payload["component_index"] == 1


def test_projection_from_dict_recomputes_affine_parameters():
    transform = ProjectionTransform.from_dict({
        "component_stem": "a",
        "composed_stem": "stack",
        "source_rect_norm": [0.0, 0.0, 1.0, 1.0],
        "target_rect_norm": [0.0, 0.0, 1.0, 0.25],
    })

    assert transform.scale_y == pytest.approx(0.25)
    assert transform.project_point((1.0, 1.0)) == pytest.approx((1.0, 0.25))


def test_vertical_stack_top_to_bottom_maps_expected_bands():
    top, bottom = vertical_stack_transforms(
        ["top", "bottom"], composed_stem="composed", top_to_bottom=True
    )

    assert top.target_rect_norm == pytest.approx((0.0, 0.5, 1.0, 1.0))
    assert bottom.target_rect_norm == pytest.approx((0.0, 0.0, 1.0, 0.5))
    assert top.project_point((0.5, 0.0)) == pytest.approx((0.5, 0.5))
    assert bottom.project_point((0.5, 1.0)) == pytest.approx((0.5, 0.5))


def test_attach_projection_evidence_preserves_existing_evidence():
    finding = Finding(
        check_id="semantic_loss",
        severity=Severity.MEDIUM,
        category=Category.CONTENT,
        stage=Stage.TIER2,
        message="component semantic signal lost in composition",
        evidence={"semantic_id": "series:a"},
    )
    transform = ProjectionTransform.from_rects(
        component_stem="component",
        composed_stem="composed",
        target_rect_norm=(0.0, 0.0, 1.0, 0.5),
    )

    out = attach_projection_evidence(
        finding,
        transform,
        projected_bbox_norm=transform.project_bbox((0.2, 0.2, 0.4, 0.4)),
    )

    assert out is finding
    assert finding.evidence["semantic_id"] == "series:a"
    projection = finding.to_dict()["evidence"]["projection_transform"]
    assert projection["component_stem"] == "component"
    assert projection["projected_bbox_norm"] == [0.2, 0.1, 0.4, 0.2]


def test_write_projection_sidecar_is_additive_and_refuses_live_vcd(tmp_path: Path):
    transform = ProjectionTransform.from_rects(
        component_stem="component",
        composed_stem="composed",
        target_rect_norm=(0.0, 0.0, 1.0, 1.0),
    )
    sidecar = tmp_path / "results" / "figures_composed" / "_scivcd_projection" / "composed.json"

    written = write_projection_sidecar(sidecar, [transform])
    payload = json.loads(written.read_text())

    assert written == sidecar
    assert payload["schema_version"] == "scivcd.projection.v1"
    assert payload["projections"][0]["component_stem"] == "component"

    with pytest.raises(ValueError, match="_live_vcd"):
        write_projection_sidecar(tmp_path / "results" / "_live_vcd" / "bad.json", [transform])


def test_normalize_rect_reorders_reversed_corners_and_rejects_bad_values():
    assert normalize_rect((0.8, 0.7, 0.2, 0.1)) == pytest.approx(
        (0.2, 0.1, 0.8, 0.7)
    )
    with pytest.raises(ValueError, match="positive width"):
        normalize_rect((0.1, 0.1, 0.1, 0.2))
    with pytest.raises(ValueError, match="within"):
        normalize_rect((-0.1, 0.0, 1.0, 1.0))
