"""VCD threshold constants and configuration.

All tunable detection thresholds are centralised here so they can be
adjusted in one place instead of being scattered across detection passes.
"""

from __future__ import annotations

# ── Text overlap (Pass 1) ──────────────────────────────────────────────────
TEXT_OVERLAP_TOL_PX: float = 2.5

# ── Truncation (Pass 2-3) ──────────────────────────────────────────────────
BORDER_TOL_PX: float = 3.0
BORDER_INFO_WINDOW_PX: float = 30.0   # overshoot < tol + this → info
EXTREME_OVERSHOOT_PX: float = 10000   # skip polar geometry artefacts

# ── Artist-vs-artist overlap (Pass 4) ──────────────────────────────────────
ARTIST_OVERLAP_MIN_PX2: float = 200.0

# ── Text-vs-artist overlap (Pass 5) ───────────────────────────────────────
TEXT_ARTIST_TOL_PX: float = 2.0
TEXT_ARTIST_OVERLAP_MIN_PX2: float = 150.0

# ── Axes overflow (Pass 6) ─────────────────────────────────────────────────
AXES_OVERFLOW_TOL_PX: float = 3.0

# ── Cross-panel spillover (Pass 8) ─────────────────────────────────────────
SPILLOVER_AREA_THRESHOLD: float = 50.0

# ── Panel label overlap (Pass 9) ──────────────────────────────────────────
PANEL_LABEL_TOL_PX: float = 2.0
PANEL_LABEL_CONTENT_AREA: float = 20.0

# ── Legend spillover (Pass 10) ─────────────────────────────────────────────
LEGEND_SPILLOVER_TOL_PX: float = 5.0
LEGEND_SPILLOVER_NEIGHBOR_AREA: float = 100.0

# ── Legend-vs-other-panel (Pass 11) ────────────────────────────────────────
LEGEND_PANEL_OVERLAP_MIN_PX2: float = 20.0

# ── Legend-vs-own-content (Pass 12) ────────────────────────────────────────
LEGEND_OWN_CONTENT_MIN_PX2: float = 140.0
LEGEND_OWN_CONTENT_FRAC: float = 0.03   # 3% of artist area

# ── Fig-legend-vs-subplot (Pass 13) ───────────────────────────────────────
FIG_LEGEND_SUBPLOT_MIN_PX2: float = 20.0
FIG_LEGEND_SUBPLOT_FRAC: float = 0.02   # 2%

# ── Colorbar internal (Pass 14) ───────────────────────────────────────────
CBAR_INTERNAL_TOL_PX: float = 1.0

# ── Legend internal (Pass 15) ──────────────────────────────────────────────
LEGEND_INTERNAL_TOL_PX: float = 1.0

# ── Significance brackets (Pass 16) ───────────────────────────────────────
BRACKET_BORDER_TOL_PX: float = 5.0
BRACKET_TEXT_OVERLAP_AREA: float = 10.0

# ── Colorbar-data overlap (Pass 17) ───────────────────────────────────────
CBAR_DATA_FRAC: float = 0.03   # 3%

# ── Legend crowding auto-fix (Pass 18) ─────────────────────────────────────
LEGEND_CROWDING_ENTRY_COUNT: int = 6
LEGEND_CROWDING_MIN_FONTSIZE: float = 8.0

# ── Font-size adequacy (Pass 19) ──────────────────────────────────────────
MIN_PT: float = 5.5
COMPOSED_SCALE: float = 0.95   # standalone full-width figures in LaTeX
DENSE_LABEL_MIN_PT: float = 5.5

# ── Label density (Pass 22) ──────────────────────────────────────────────
LABEL_DENSITY_THRESHOLD: float = 0.92

# ── Per-axes summary ──────────────────────────────────────────────────────
PER_AXES_SUMMARY_AREA: float = 30.0
PER_AXES_SUMMARY_FRAC: float = 0.03

# ── Skip tags for legend-data checks ─────────────────────────────────────
SKIP_TAGS = ("Spine", "Wedge", "FancyBbox")

# ── Font policy (new) ────────────────────────────────────────────────────
ALLOWED_FONT_FAMILIES = {"Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "sans-serif"}
MAX_TITLE_LABEL_SIZE_DIFF: float = 2.0   # max pt difference title vs label
BOLD_WHITELIST = set()  # elements allowed to use bold (empty = none)

# ── Contrast (Pass 23) ─────────────────────────────────────────────────
MIN_TEXT_CONTRAST: float = 3.0           # WCAG 2.0 relaxed for sci-figs
MIN_LINE_CONTRAST: float = 1.8           # lines/markers vs axes bg

# ── Colorblind safety (Pass 24) ────────────────────────────────────────
MIN_CVD_DISTANCE: float = 10.0           # CIE76 ΔE under simulated CVD
CVD_MAX_CATEGORIES: int = 20             # skip O(n²) on continuous palettes

# ── Error-bar visibility (Pass 25) ─────────────────────────────────────
ERRORBAR_TARGET_DPI: int = 300
ERRORBAR_MIN_CAP_PX: float = 1.5        # cap size at target DPI

# ── Precision excess (Pass 26) ─────────────────────────────────────────
MAX_DECIMAL_PLACES: int = 4              # flag labels with > this many

# ── Overplotting (Pass 27) ─────────────────────────────────────────────
OVERPLOT_ALPHA_THRESHOLD: int = 5000     # any alpha: this many pts → warn
OVERPLOT_OPAQUE_THRESHOLD: int = 2000    # α≥0.5: this many pts → warn
                                         # Tuned: gene scatter ~1800 pts is readable

# ── Log-scale sanity (Pass 28) ─────────────────────────────────────────
# (threshold-free; checks label text and data range)

# ── Scale consistency (Pass 29) ────────────────────────────────────────
SCALE_RANGE_SPREAD_FACTOR: float = 3.0   # flag if max_range/min_range > this

# ── Floating significance (Pass 30) ───────────────────────────────────
SIGNIFICANCE_PROXIMITY_PX: float = 50.0  # max px from nearest data artist

# ── Panel complexity (Pass 31) ─────────────────────────────────────────
MAX_LEGEND_SERIES: int = 10              # legend entries before complexity flag
MAX_NUMERIC_BAR_LABELS: int = 30         # per-bar value labels before flag
MAX_ANNOTATIONS_COMPLEXITY: int = 20     # text elements per axes before flag
COMPLEXITY_SCORE_THRESHOLD: float = 15.0 # weighted sum that triggers the issue

# ── Whitespace / height compaction (post-refinement) ──────────────────
HSPACE_EXCESS_THRESHOLD: float = 0.70    # hspace above this can be compacted
HSPACE_COMPACT_TARGET: float = 0.35      # hspace target after compaction
TARGET_HEIGHT_WIDTH_RATIO: float = 0.50  # h/w target for full-width panels
HEIGHT_COMPACT_MIN: float = 4.0          # never shrink below this many inches

# ── Semantic integrity (label preservation) ────────────────────────────
MIN_LABEL_DISPLAY_CHARS: int = 12        # never shorten a label below this

# ── Cross-axes text overlap (Pass 32) ────────────────────────────
CROSS_AXES_TEXT_OVERLAP_TOL_PX: float = 2.0   # shrink before overlap test
CROSS_AXES_TEXT_OVERLAP_MIN_PX2: float = 10.0 # minimum area to report

# ── Panel label placement (Pass 33) ─────────────────────────────
PANEL_LABEL_PLACEMENT_MARGIN_PX: float = 5.0  # margin for "inside" detection
