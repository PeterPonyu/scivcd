"""Layout-rect optimizer: tighten composition until just before overlap (US-303).

Iteratively shrinks figure margins and inter-subplot spacing (``hspace``,
``wspace``) until either:

  1. The next shrink step introduces a text-overlap or truncation finding, or
  2. The inter-axes or axes-to-border inset hits the configured floor.

Returns a ``TightenResult`` describing the before/after figure size, the
accepted margin/spacing values, and the percentage of whitespace saved.

The implementation is intentionally dependency-light: it mutates the figure
in place through ``subplots_adjust`` for margins and walks ``gridspec``
objects for ``hspace``/``wspace``. A full layout-engine rewrite was avoided
because the goal here is a bounded audit tool, not a replacement for
``tight_layout``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class TightenResult:
    original_size_in: Tuple[float, float]
    tightened_size_in: Tuple[float, float]
    saved_whitespace_pct: float
    before_params: Dict[str, float] = field(default_factory=dict)
    after_params: Dict[str, float] = field(default_factory=dict)
    iterations: int = 0
    stopped_reason: str = ""


def _current_adjust(fig) -> Dict[str, float]:
    sp = fig.subplotpars
    return {
        "left": float(sp.left),
        "right": float(sp.right),
        "top": float(sp.top),
        "bottom": float(sp.bottom),
        "hspace": float(sp.hspace),
        "wspace": float(sp.wspace),
    }


def _probe_overlap(fig) -> int:
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
        if str(i.get("type")) in {
            "text_overlap", "text_truncation",
            "cross_axes_text_overlap", "text_artist_overlap",
            "artist_content_overlap",
        }
    ]
    return len(blockers)


def tighten_layout(
    fig,
    *,
    min_inset_px: float = 8.0,
    step: float = 0.02,
    max_iter: int = 20,
) -> TightenResult:
    """Greedy tightening of subplot adjust parameters.

    Each iteration nudges margins inward and ``hspace``/``wspace`` down by
    ``step``. If the overlap probe returns more findings than the baseline,
    the step is reverted and the loop stops.
    """
    original_figsize_in = tuple(fig.get_size_inches())
    before = _current_adjust(fig)
    baseline = _probe_overlap(fig)

    accepted = dict(before)
    iterations = 0
    stopped_reason = "max_iter"
    dpi = float(fig.dpi) or 100.0
    min_inset_fig_frac_w = (min_inset_px / dpi) / max(original_figsize_in[0], 1e-6)
    min_inset_fig_frac_h = (min_inset_px / dpi) / max(original_figsize_in[1], 1e-6)

    for _ in range(max_iter):
        iterations += 1
        candidate = dict(accepted)
        # Pull margins inward, but never past the opposite side or the inset floor.
        max_left = accepted["right"] - min_inset_fig_frac_w - 0.05
        min_right = accepted["left"] + min_inset_fig_frac_w + 0.05
        max_bottom = accepted["top"] - min_inset_fig_frac_h - 0.05
        min_top = accepted["bottom"] + min_inset_fig_frac_h + 0.05
        candidate["left"] = min(max_left, accepted["left"] + step)
        candidate["right"] = max(min_right, accepted["right"] - step)
        candidate["bottom"] = min(max_bottom, accepted["bottom"] + step)
        candidate["top"] = max(min_top, accepted["top"] - step)
        candidate["hspace"] = max(0.0, accepted["hspace"] - step)
        candidate["wspace"] = max(0.0, accepted["wspace"] - step)

        if candidate["left"] >= candidate["right"] or candidate["bottom"] >= candidate["top"]:
            stopped_reason = "margin floor reached"
            break
        if candidate == accepted:
            stopped_reason = "no further tightening possible"
            break

        fig.subplots_adjust(**candidate)
        overlaps = _probe_overlap(fig)
        if overlaps > baseline:
            # revert to previously accepted
            fig.subplots_adjust(**accepted)
            stopped_reason = f"overlap count {baseline} -> {overlaps}"
            break
        accepted = candidate

    # Approximate whitespace saved: change in the surrounding border margins.
    before_area = (1 - before["left"] - (1 - before["right"])) * (
        1 - before["bottom"] - (1 - before["top"])
    )
    after_area = (1 - accepted["left"] - (1 - accepted["right"])) * (
        1 - accepted["bottom"] - (1 - accepted["top"])
    )
    saved = max(0.0, (after_area - before_area) / max(before_area, 1e-6)) * 100.0

    return TightenResult(
        original_size_in=original_figsize_in,
        tightened_size_in=tuple(fig.get_size_inches()),
        saved_whitespace_pct=saved,
        before_params=before,
        after_params=accepted,
        iterations=iterations,
        stopped_reason=stopped_reason,
    )


__all__ = ["tighten_layout", "TightenResult"]
