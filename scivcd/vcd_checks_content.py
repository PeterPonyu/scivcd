"""Content-aware VCD checks (US-305, folded back from the multimodal audit).

Unlike the geometry-only checks, these rules look at the *string content*
of rendered text artists and the *value patterns* of plotted series. They
close the gap identified in `revision/vcd_multimodal_audit.md` where the
geometric VCD missed 27+ reviewer-visible defects across 11 paper figures
(all one family: pre-truncated ellipsis labels).

Three rules live here:

- ``check_label_string_ellipsis``  — text ends with ``…`` or ``...``
- ``check_overlapping_series_values`` — multiple lines collapsed on one y-value
- ``check_duplicate_tick_labels`` — axis ticks repeat a label string
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


__all__ = [
    "check_label_string_ellipsis",
    "check_overlapping_series_values",
    "check_duplicate_tick_labels",
]
