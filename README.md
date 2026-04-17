# scivcd

**Scientific figure Visual Conflict Detector** — a publication-grade matplotlib figure linter with
severity grading, complexity-routed checks, font auto-fix, layout tightening, and content-aware
audits.

Originally developed as an internal tool for the CLOP-DiT paper revision; extracted here as a
standalone package so any Python visualization project can run the same 36-pass, 4-severity
audit against its figures.

## What it does

- **36 checks across 6 layers** (geometry, layout, legend/colorbar, perceptual, semantic,
  publication-quality) — finds text truncation, cross-axes overlap, colorblind-confusable palettes,
  effective-DPI problems, pre-truncated label strings, overlapping series, duplicate ticks, etc.
- **4-level severity grading** — `CRITICAL` (publication-blocker) / `MAJOR` (reviewer-visible
  defect) / `MINOR` (cosmetic) / `INFO` (signal, not a defect). Drives triage, not just a flat count.
- **Complexity-routed profiles** — classifies each figure as `SIMPLE` / `COMPOUND` / `COMPOSED`
  and runs only the relevant checks. Simple figures audit ~8× faster than the full 36-pass suite.
- **Font auto-fix** — `maximize_font_size(fig)` grows every text artist uniformly until the next
  step would introduce overlap, returning the largest legible scale.
- **Layout tightening** — `tighten_layout(fig)` greedily shrinks `hspace` / `wspace` / margins
  to their smallest values that preserve the overlap-finding baseline.
- **Baseline diff** — pin a VCD snapshot, then fail later runs on any new CRITICAL.
- **Content-aware rules** — catches issues geometric linters miss, like producer-side ellipsis
  label truncation that hides biological identifiers from reviewers.

## Install

```bash
# From source (editable)
pip install -e .

# or from a local clone
cd scivcd
pip install .
```

## Development

```bash
# Run the test suite
pytest -q

# Build sdist + wheel
python -m pip install build
python -m build
```

## Quick start

```python
import matplotlib.pyplot as plt
from scivcd import detect_all_conflicts, count_by_severity_level

fig, ax = plt.subplots()
ax.plot([0, 1], [0, 1])
ax.set_title("Example", fontsize=8)  # small font will trip check_minimum_font_size

issues = detect_all_conflicts(fig, verbose=False, profile="auto")
print(count_by_severity_level(issues))
# → {'CRITICAL': 0, 'MAJOR': 1, 'MINOR': 0, 'INFO': 0}

for i in issues:
    print(f"[{i['severity_level']}] {i['type']}: {i['detail']}")
```

## Adaptive profile routing

```python
from scivcd.vcd_complexity import classify_figure, PROFILES

print(classify_figure(fig))
# Complexity.SIMPLE  — 4 cheap checks

# Or let detect_all_conflicts pick for you:
issues = detect_all_conflicts(fig, profile="auto")
```

| Profile   | #checks | When |
|-----------|--------:|------|
| SIMPLE    | 4       | single axes, ≤50 artists, no suptitle |
| COMPOUND  | 10      | ≤4 axes, single row or column gridspec |
| COMPOSED  | 36      | grid gridspec, figure-level legend, or ≥5 axes |
| full      | 36      | explicit override |

## Font auto-fix

```python
from scivcd.vcd_autofix import maximize_font_size

result = maximize_font_size(fig, step=1.05, max_iter=12)
print(f"grew fonts by {(result.scale_factor - 1) * 100:.0f}% "
      f"to {result.max_legible_avg_pt:.1f}pt")
```

## Baseline diff

```python
from scivcd.vcd_baseline import (
    snapshot_from_vcd_report, save_baseline, load_baseline,
    diff_against_baseline, render_diff_markdown,
)

# Pin a baseline after a clean run
save_baseline(snapshot_from_vcd_report(current_vcd), "vcd_baseline.json")

# Later, diff a new run
report = diff_against_baseline(new_vcd, load_baseline("vcd_baseline.json"))
if report.has_new_critical:
    raise SystemExit(2)
```

## Severity mapping

```python
from scivcd import severity_level_for

severity_level_for({"type": "text_truncation"})          # → "CRITICAL"
severity_level_for({"type": "cross_axes_text_overlap"})  # → "CRITICAL"
severity_level_for({"type": "legend_artist_masking"})    # → "MINOR"
severity_level_for({"type": "bold_usage"})               # → "INFO"
```

Override via `FigurePolicy.severity_overrides`.

## Origin

Extracted from the CLOP-DiT paper's `revision/major` branch, commit
`cf5de41 vcd: adaptive routing, autofix, tightening, content-aware checks`. The original VCD
package is referenced in the CLOP-DiT submission's `revision/vcd_coverage_audit.md` and
`revision/vcd_multimodal_audit.md`.

## License

MIT — see LICENSE.
