"""Content-aware VCD checks (US-305, folded back from the multimodal audit).

Unlike the geometry-only checks, these rules look at the *string content*
of rendered text artists and the *value patterns* of plotted series. They
close the gap identified in `revision/vcd_multimodal_audit.md` where the
geometric VCD missed 27+ reviewer-visible defects across 11 paper figures
(all one family: pre-truncated ellipsis labels).

Four rules live here:

- ``check_label_string_ellipsis``  — text ends with ``…`` or ``...``
- ``check_overlapping_series_values`` — multiple lines collapsed on one y-value
- ``check_duplicate_tick_labels`` — axis ticks repeat a label string
- ``check_annotation_crowding`` — >=3 ad-hoc annotations in the same local region
"""

from __future__ import annotations

from typing import List

from matplotlib.text import Text
import numpy as np


_ELLIPSIS_SUFFIXES = ("…", "...")


def check_label_string_ellipsis(fig) -> List[dict]:
    """Flag text artists whose content was pre-truncated with ``…`` or ``...``.

    The matplotlib bbox fits the axis because the string was shortened
    before rendering; reviewers still see the cut-off name. Each hit is
    emitted as a single finding per axis to keep noise manageable on dense
    figures like figS01/figS02 which can have 15+ truncated labels.
    """
    issues: List[dict] = []
    for ax in fig.get_axes():
        hits: List[str] = []
        candidates = []
        try:
            candidates.extend(ax.get_xticklabels())
            candidates.extend(ax.get_yticklabels())
        except Exception:
            pass
        candidates.extend(list(ax.texts))
        if ax.get_legend() is not None:
            candidates.extend(ax.get_legend().get_texts())
        seen: set = set()
        for art in candidates:
            if not isinstance(art, Text) or id(art) in seen:
                continue
            seen.add(id(art))
            text = art.get_text().strip()
            if not text:
                continue
            if text.endswith(_ELLIPSIS_SUFFIXES):
                hits.append(text[:40])
        if hits:
            # Collapse to one finding per axis with a count + first 3 samples
            sample = ", ".join(hits[:3])
            title = ax.get_title() or ""
            issues.append({
                "type": "label_string_ellipsis",
                "severity": "warning",
                "severity_level": "MINOR",
                "detail": (
                    f"axes '{title[:40]}' has {len(hits)} pre-truncated labels "
                    f"(e.g. {sample})"
                ),
                "elements": hits[:5],
            })
    return issues


def check_overlapping_series_values(
    fig,
    *,
    min_series: int = 3,
    coincidence_threshold: float = 0.99,
    min_x_fraction: float = 0.80,
) -> List[dict]:
    """Flag axes where >= ``min_series`` plotted lines collapse onto the same y.

    For each pair of lines on an axes, compute the fraction of their common
    x-range on which their normalized y-values agree. Build a coincidence
    graph and report any connected component of size >= ``min_series``.
    """
    issues: List[dict] = []
    for ax in fig.get_axes():
        lines = [ln for ln in ax.lines if ln.get_visible()]
        if len(lines) < min_series:
            continue
        ys = []
        labels = []
        for ln in lines:
            y = np.asarray(ln.get_ydata(), dtype=float)
            if y.size < 3:
                continue
            ys.append(y)
            labels.append(ln.get_label() or "?")
        if len(ys) < min_series:
            continue
        # Normalize each series by the overall (cross-series) y-range so we
        # compare relative shape on a consistent scale. This lets us treat
        # "three series all sitting at the ceiling" as coincident even when a
        # fourth reference series diverges.
        all_vals = np.concatenate(ys)
        span = np.nanmax(all_vals) - np.nanmin(all_vals)
        if span <= 0:
            continue
        floor = np.nanmin(all_vals)
        normed = [(y - floor) / span for y in ys]

        # Pairwise coincidence fraction (per-x agreement within tolerance).
        tol = 1.0 - coincidence_threshold
        n = len(normed)
        adj: dict[int, set] = {i: set() for i in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                m = min(normed[i].size, normed[j].size)
                diff = np.abs(normed[i][:m] - normed[j][:m])
                frac = float((diff <= tol).mean())
                if frac >= min_x_fraction:
                    adj[i].add(j)
                    adj[j].add(i)

        # Find the largest connected component of coincident series.
        visited: set = set()
        def _component(start: int) -> set:
            stack = [start]
            comp: set = set()
            while stack:
                u = stack.pop()
                if u in comp:
                    continue
                comp.add(u)
                stack.extend(adj[u] - comp)
            return comp

        for start in range(n):
            if start in visited:
                continue
            comp = _component(start)
            visited |= comp
            if len(comp) >= min_series:
                comp_labels = [labels[i] for i in sorted(comp)]
                issues.append({
                    "type": "overlapping_series_values",
                    "severity": "info",
                    "detail": (
                        f"{len(comp)} lines are coincident (>= "
                        f"{int(min_x_fraction * 100)}% of x-range): "
                        f"{', '.join(str(l)[:20] for l in comp_labels[:4])}"
                    ),
                    "elements": [str(l) for l in comp_labels],
                })
    return issues


def check_duplicate_tick_labels(fig) -> List[dict]:
    """Flag axes whose tick-label list contains duplicated non-empty strings.

    Legitimate in grouped-axis designs (e.g. bootstrap CIs with per-method
    rows), but worth verifying. Emitted as INFO.
    """
    issues: List[dict] = []
    for ax in fig.get_axes():
        for axis_name, ticklabels in (
            ("x", ax.get_xticklabels()),
            ("y", ax.get_yticklabels()),
        ):
            strings = [t.get_text().strip() for t in ticklabels]
            nonempty = [s for s in strings if s]
            if len(nonempty) < 3:
                continue
            seen: dict = {}
            dups: list = []
            for s in nonempty:
                seen[s] = seen.get(s, 0) + 1
            for s, c in seen.items():
                if c > 1:
                    dups.append((s, c))
            if dups:
                sample = ", ".join(f"{s!r}×{c}" for s, c in dups[:3])
                issues.append({
                    "type": "duplicate_tick_labels",
                    "severity": "info",
                    "detail": (
                        f"{axis_name}-axis has duplicate ticklabels: {sample}"
                    ),
                    "elements": [s for s, _ in dups[:5]],
                })
    return issues


def check_annotation_crowding(
    fig,
    *,
    min_annotations: int = 3,
    bin_fraction: float = 0.15,
    exclude_titles: bool = True,
) -> List[dict]:
    """Flag axes where >=``min_annotations`` ad-hoc text artists fall inside
    the same local axes-fraction bin of size ``bin_fraction`` x ``bin_fraction``.

    Distilled from the scivcd 2026-04-17 layout review: offset-heuristic
    self-organising labels (``annotate`` with automatic offset) stop being
    readable once three or more land in the same local region — the labels
    collide and the leader lines cross. The geometric overlap checks miss
    this because any two labels may be individually non-overlapping even
    while the cluster as a whole is illegible.

    The rule only looks at ``ax.texts`` (annotations the author added
    explicitly). It ignores titles, axis labels, tick labels, and panel
    labels so legitimate single-letter panel tags (a, b, c, ...) do not
    trigger the rule.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    min_annotations : int
        Cluster size that triggers a finding. Default 3 matches the
        layout-review recommendation.
    bin_fraction : float
        Side length of the axes-fraction bin used to detect local density.
        Default 0.15 treats any 15% x 15% patch as a single "local region".
    exclude_titles : bool
        If True, drop single-character texts (panel labels) and any text
        whose axes-fraction position is above the axes top (titles).

    Returns
    -------
    list[dict]
        One finding per over-crowded axes/bin, with ``axes_id``, ``bin``
        (x_frac, y_frac integer-indexed), ``n_annotations``, and
        ``effective_density`` (annotations per unit axes-fraction area).
    """
    issues: List[dict] = []
    if bin_fraction <= 0.0 or bin_fraction > 1.0:
        return issues

    for axes_idx, ax in enumerate(fig.get_axes()):
        if not getattr(ax, "axison", True):
            continue
        text_artists = [t for t in ax.texts if isinstance(t, Text)]
        if len(text_artists) < min_annotations:
            continue

        # Convert each text artist's position to axes fraction coords. A text
        # created with ``ax.annotate(..., xy=data)`` carries data-coordinate
        # positions; normalise to axes-fraction space so figures with
        # different data ranges share a uniform crowding threshold.
        points: list[tuple[float, float, Text]] = []
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        dx = xlim[1] - xlim[0]
        dy = ylim[1] - ylim[0]
        if dx == 0 or dy == 0:
            continue
        for t in text_artists:
            raw = t.get_text().strip()
            if not raw:
                continue
            if exclude_titles and len(raw) == 1:
                continue
            try:
                x, y = t.get_position()
            except Exception:
                continue
            coords = t.get_transform()
            # Only honour annotations anchored in data or axes-fraction space.
            # Figure-fraction texts are not per-axes crowding candidates.
            transform_name = str(getattr(coords, "__class__", "")).lower()
            if "axes" in transform_name:
                x_frac, y_frac = float(x), float(y)
            else:
                x_frac = (float(x) - xlim[0]) / dx
                y_frac = (float(y) - ylim[0]) / dy
            if exclude_titles and y_frac > 1.02:
                continue
            if not (-0.02 <= x_frac <= 1.02 and -0.02 <= y_frac <= 1.02):
                continue
            points.append((x_frac, y_frac, t))

        if len(points) < min_annotations:
            continue

        # Bin by axes-fraction quantized to the requested bin size.
        bins: dict[tuple[int, int], list] = {}
        n_bins = max(1, int(round(1.0 / bin_fraction)))
        for x_frac, y_frac, t in points:
            bx = min(n_bins - 1, max(0, int(x_frac * n_bins)))
            by = min(n_bins - 1, max(0, int(y_frac * n_bins)))
            bins.setdefault((bx, by), []).append((x_frac, y_frac, t))

        for (bx, by), cluster in bins.items():
            if len(cluster) < min_annotations:
                continue
            samples = [str(t.get_text())[:30] for _, _, t in cluster[:3]]
            effective_density = len(cluster) / (bin_fraction * bin_fraction)
            title = ax.get_title() or ""
            issues.append({
                "type": "annotation_crowding",
                "severity": "warning",
                "severity_level": "MAJOR",
                "detail": (
                    f"axes '{title[:40]}' has {len(cluster)} annotations "
                    f"clustered in a {int(bin_fraction*100)}%x{int(bin_fraction*100)}% "
                    f"bin at (x_frac≈{bx/n_bins:.2f}, y_frac≈{by/n_bins:.2f}); "
                    f"samples: {', '.join(samples)}"
                ),
                "elements": [str(t.get_text()) for _, _, t in cluster[:5]],
                "axes_id": axes_idx,
                "bin": (bx, by),
                "n_annotations": len(cluster),
                "effective_density": effective_density,
            })

    return issues


__all__ = [
    "check_label_string_ellipsis",
    "check_overlapping_series_values",
    "check_duplicate_tick_labels",
    "check_annotation_crowding",
]
