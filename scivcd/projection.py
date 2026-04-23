"""Component-to-composed figure projection helpers.

The projection model maps normalized component coordinates into normalized
composed/export coordinates.  It is intentionally independent of any
project-specific sandbox: adapters may write these transforms as additive
sidecars, but
the generic package only knows about stems, rectangles, affine parameters, and
finding evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from scivcd.core import Finding

Rect = tuple[float, float, float, float]
Point = tuple[float, float]


@dataclass(frozen=True)
class ProjectionTransform:
    """Affine transform from one normalized rectangle to another.

    The required schema fields match the Phase 1 sidecar contract.  The
    transform is applied as ``target = source * scale + offset`` in normalized
    coordinate space.
    """

    component_stem: str
    composed_stem: str
    source_rect_norm: Rect
    target_rect_norm: Rect
    scale_x: float
    scale_y: float
    offset_x: float
    offset_y: float
    dpi: Optional[float] = None
    page_index: Optional[int] = None
    component_index: Optional[int] = None

    @classmethod
    def from_rects(
        cls,
        *,
        component_stem: str,
        composed_stem: str,
        source_rect_norm: Sequence[float] = (0.0, 0.0, 1.0, 1.0),
        target_rect_norm: Sequence[float],
        dpi: Optional[float] = None,
        page_index: Optional[int] = None,
        component_index: Optional[int] = None,
    ) -> "ProjectionTransform":
        """Create a transform from normalized source/target rectangles."""
        source = normalize_rect(source_rect_norm, name="source_rect_norm")
        target = normalize_rect(target_rect_norm, name="target_rect_norm")
        sw = source[2] - source[0]
        sh = source[3] - source[1]
        tw = target[2] - target[0]
        th = target[3] - target[1]
        scale_x = tw / sw
        scale_y = th / sh
        offset_x = target[0] - source[0] * scale_x
        offset_y = target[1] - source[1] * scale_y
        return cls(
            component_stem=str(component_stem),
            composed_stem=str(composed_stem),
            source_rect_norm=source,
            target_rect_norm=target,
            scale_x=scale_x,
            scale_y=scale_y,
            offset_x=offset_x,
            offset_y=offset_y,
            dpi=dpi,
            page_index=page_index,
            component_index=component_index,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectionTransform":
        """Load a transform from a JSON-like dict."""
        return cls.from_rects(
            component_stem=str(data["component_stem"]),
            composed_stem=str(data["composed_stem"]),
            source_rect_norm=data["source_rect_norm"],
            target_rect_norm=data["target_rect_norm"],
            dpi=data.get("dpi"),
            page_index=data.get("page_index"),
            component_index=data.get("component_index"),
        )

    def project_point(self, point: Sequence[float]) -> Point:
        """Project a normalized ``(x, y)`` point into composed coordinates."""
        x, y = _normalize_point(point)
        return (x * self.scale_x + self.offset_x, y * self.scale_y + self.offset_y)

    def project_rect(self, rect: Sequence[float]) -> Rect:
        """Project a normalized bbox/rect into composed coordinates."""
        x0, y0, x1, y1 = normalize_rect(rect, name="rect")
        px0, py0 = self.project_point((x0, y0))
        px1, py1 = self.project_point((x1, y1))
        return normalize_rect((px0, py0, px1, py1), name="projected_rect")

    # Alias used by tests/callers that describe findings as bboxes.
    project_bbox = project_rect

    def to_dict(self) -> dict[str, Any]:
        """Return the Phase 1 projection sidecar/evidence schema."""
        data: dict[str, Any] = {
            "component_stem": self.component_stem,
            "composed_stem": self.composed_stem,
            "source_rect_norm": list(self.source_rect_norm),
            "target_rect_norm": list(self.target_rect_norm),
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }
        if self.dpi is not None:
            data["dpi"] = self.dpi
        if self.page_index is not None:
            data["page_index"] = self.page_index
        if self.component_index is not None:
            data["component_index"] = self.component_index
        return data


def normalize_rect(rect: Sequence[float], *, name: str = "rect") -> Rect:
    """Validate and normalize a four-value rect in normalized coordinates."""
    if len(rect) != 4:
        raise ValueError(f"{name} must have four values [x0, y0, x1, y1]")
    x0, y0, x1, y1 = (float(v) for v in rect)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if x1 == x0 or y1 == y0:
        raise ValueError(f"{name} must have positive width and height")
    values = (x0, y0, x1, y1)
    if any(v < 0.0 or v > 1.0 for v in values):
        raise ValueError(f"{name} values must be within [0, 1]")
    return values


def vertical_stack_transforms(
    component_stems: Sequence[str],
    *,
    composed_stem: str,
    top_to_bottom: bool = True,
    source_rect_norm: Sequence[float] = (0.0, 0.0, 1.0, 1.0),
    dpi: Optional[float] = None,
    page_index: Optional[int] = None,
) -> list[ProjectionTransform]:
    """Build transforms for equal-height vertical raster stacks.

    With ``top_to_bottom=True`` the first component occupies the top band in
    conventional normalized figure coordinates (larger y values).
    """
    count = len(component_stems)
    if count <= 0:
        return []
    height = 1.0 / count
    transforms: list[ProjectionTransform] = []
    for idx, stem in enumerate(component_stems):
        if top_to_bottom:
            y1 = 1.0 - idx * height
            y0 = y1 - height
        else:
            y0 = idx * height
            y1 = y0 + height
        transforms.append(ProjectionTransform.from_rects(
            component_stem=stem,
            composed_stem=composed_stem,
            source_rect_norm=source_rect_norm,
            target_rect_norm=(0.0, y0, 1.0, y1),
            dpi=dpi,
            page_index=page_index,
            component_index=idx,
        ))
    return transforms


def attach_projection_evidence(
    finding: Finding,
    projection: ProjectionTransform,
    *,
    projected_bbox_norm: Optional[Sequence[float]] = None,
) -> Finding:
    """Attach projection-transform evidence to a finding in place.

    Returning the same object keeps this helper easy to compose with existing
    checks while preserving any prior evidence keys.
    """
    evidence = dict(finding.evidence or {})
    transform = projection.to_dict()
    if projected_bbox_norm is not None:
        transform["projected_bbox_norm"] = list(normalize_rect(
            projected_bbox_norm,
            name="projected_bbox_norm",
        ))
    evidence["projection_transform"] = transform
    finding.evidence = evidence
    return finding


def write_projection_sidecar(
    path: "str | Path",
    projections: Iterable[ProjectionTransform],
) -> Path:
    """Write projection transforms to an additive JSON sidecar.

    The helper refuses paths under ``_live_vcd`` so sandbox adapters cannot
    accidentally mutate the existing live VCD contract.
    """
    target = Path(path)
    if any(part == "_live_vcd" for part in target.parts):
        raise ValueError("projection sidecars must not be written under _live_vcd")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "scivcd.projection.v1",
        "projections": [projection.to_dict() for projection in projections],
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _normalize_point(point: Sequence[float]) -> Point:
    if len(point) != 2:
        raise ValueError("point must have two values [x, y]")
    x, y = (float(v) for v in point)
    if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
        raise ValueError("point values must be within [0, 1]")
    return x, y


__all__ = [
    "Point",
    "ProjectionTransform",
    "Rect",
    "attach_projection_evidence",
    "normalize_rect",
    "vertical_stack_transforms",
    "write_projection_sidecar",
]
