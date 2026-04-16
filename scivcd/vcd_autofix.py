"""Auto-fix: maximize font size under overlap constraint (US-302).

Given a matplotlib figure, iteratively scale every text artist's font size
upwards until the next scale-up would introduce a text-overlap or truncation
finding. Returns a ``FontScalingResult`` describing the chosen scale factor
and the resulting effective point sizes.

Design notes:
  - The scale is uniform across every Text artist in the figure (titles,
    tick labels, annotations, legend text). A heterogeneous-scale variant is
    possible but significantly harder to search; uniform scaling is enough
    to answer the user's question "how big can the fonts be?".
  - Re-measurement happens via ``fig.canvas.draw()`` so the artist bboxes
    reflect the new font sizes before the VCD probe runs.
  - We probe only two *fast* checks inside the search loop (text_overlap +
    text_truncation). A full VCD sweep per iteration would be too slow and
    would punish unrelated findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from matplotlib.text import Text


@dataclass
class FontScalingResult:
    scale_factor: float
    current_avg_pt: float
    max_legible_avg_pt: float
    iterations: int
    accepted_scales: List[float] = field(default_factory=list)
    rejected_scales: List[Tuple[float, str]] = field(default_factory=list)


def _collect_texts(fig) -> list:
    texts: list = []
    for ax in fig.get_axes():
        if getattr(ax, "title", None) is not None:
            texts.append(ax.title)
        for t in (ax.xaxis.label, ax.yaxis.label):
            if t is not None:
                texts.append(t)
        texts.extend(ax.get_xticklabels())
        texts.extend(ax.get_yticklabels())
        texts.extend(list(ax.texts))
        leg = ax.get_legend()
        if leg is not None:
            texts.extend(leg.get_texts())
    texts.extend(list(getattr(fig, "texts", [])))
    # Deduplicate while preserving order
    seen: set = set()
    uniq: list = []
    for t in texts:
        if isinstance(t, Text) and id(t) not in seen and t.get_text():
            uniq.append(t)
            seen.add(id(t))
    return uniq


def _snapshot_sizes(texts: list) -> list[float]:
    return [float(t.get_fontsize()) for t in texts]


def _apply_scale(texts: list, sizes: list[float], scale: float, max_pt: float) -> None:
    for t, s in zip(texts, sizes):
        t.set_fontsize(min(max_pt, s * scale))


def _probe_overlap(fig) -> int:
    """Return count of overlap + truncation findings at the current font scale."""
    try:
        fig.canvas.draw()
    except Exception:
        return 0
    try:
        import sys
        from pathlib import Path
        pass
        pass

        from . import detect_all_conflicts
        issues = detect_all_conflicts(fig, verbose=False)
    except Exception:
        return 0
    blockers = [
        i for i in issues
        if str(i.get("type")) in {"text_overlap", "text_truncation",
                                    "cross_axes_text_overlap", "text_artist_overlap"}
    ]
    return len(blockers)


def maximize_font_size(
    fig,
    *,
    step: float = 1.05,
    max_iter: int = 12,
    min_pt: float = 6.0,
    max_pt: float = 24.0,
) -> FontScalingResult:
    """Grow font sizes geometrically until the next step would break overlap invariants."""
    texts = _collect_texts(fig)
    if not texts:
        return FontScalingResult(1.0, 0.0, 0.0, 0)

    original_sizes = _snapshot_sizes(texts)
    original_avg = sum(original_sizes) / len(original_sizes)

    baseline_overlaps = _probe_overlap(fig)

    accepted: List[float] = [1.0]
    rejected: List[Tuple[float, str]] = []

    lo, hi = 1.0, max(step, 1.0) ** max_iter
    best = 1.0
    iterations = 0
    # Expand upward until we hit a scale that breaks overlap invariants.
    scale = step
    while iterations < max_iter and scale <= hi:
        iterations += 1
        effective_min = min(original_sizes) * scale
        effective_max = max(original_sizes) * scale
        if effective_min < min_pt or effective_max > max_pt:
            rejected.append((scale, "outside [min_pt, max_pt]"))
            break
        _apply_scale(texts, original_sizes, scale, max_pt)
        overlaps = _probe_overlap(fig)
        if overlaps <= baseline_overlaps:
            accepted.append(scale)
            best = scale
            scale *= step
        else:
            rejected.append((scale, f"overlaps {baseline_overlaps} -> {overlaps}"))
            break

    # Restore the figure to the chosen best scale (so caller sees the autofixed state).
    _apply_scale(texts, original_sizes, best, max_pt)
    try:
        fig.canvas.draw()
    except Exception:
        pass

    return FontScalingResult(
        scale_factor=best,
        current_avg_pt=original_avg,
        max_legible_avg_pt=original_avg * best,
        iterations=iterations,
        accepted_scales=accepted,
        rejected_scales=rejected,
    )


__all__ = ["maximize_font_size", "FontScalingResult"]
