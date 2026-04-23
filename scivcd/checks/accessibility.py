"""ACCESSIBILITY-category detectors for SciVCD."""
from __future__ import annotations

from typing import Any

from matplotlib.colors import to_rgb

from scivcd.core import Category, CheckSpec, Finding, ScivcdConfig, Severity, Stage, register


def _data_axes(fig: Any) -> list:
    return [ax for ax in fig.get_axes() if not getattr(ax, "_colorbar", None)]


def _rgb255(color: Any) -> tuple[float, float, float] | None:
    try:
        r, g, b = to_rgb(color)
    except Exception:
        return None
    return (r * 255.0, g * 255.0, b * 255.0)


def _srgb_to_xyz(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    vals = []
    for c in (v / 255.0 for v in rgb):
        vals.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = vals
    return (
        r * 0.4124564 + g * 0.3575761 + b * 0.1804375,
        r * 0.2126729 + g * 0.7151522 + b * 0.0721750,
        r * 0.0193339 + g * 0.1191920 + b * 0.9503041,
    )


def _xyz_to_lab(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    xr, yr, zr = xyz[0] / 0.95047, xyz[1] / 1.00000, xyz[2] / 1.08883
    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)
    fx, fy, fz = f(xr), f(yr), f(zr)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(rgb_a: tuple[float, float, float], rgb_b: tuple[float, float, float]) -> float:
    lab_a = _xyz_to_lab(_srgb_to_xyz(rgb_a))
    lab_b = _xyz_to_lab(_srgb_to_xyz(rgb_b))
    return sum((a - b) ** 2 for a, b in zip(lab_a, lab_b)) ** 0.5


def _simulate_cvd(rgb: tuple[float, float, float], mode: str) -> tuple[float, float, float]:
    # Simple linear Machado-style approximations sufficient for MVP fixtures.
    matrices = {
        "deuteranopia": ((0.367, 0.861, -0.228), (0.280, 0.673, 0.047), (-0.012, 0.043, 0.969)),
        "protanopia": ((0.152, 1.053, -0.205), (0.115, 0.786, 0.099), (-0.004, -0.048, 1.052)),
    }
    m = matrices[mode]
    r, g, b = rgb
    out = []
    for row in m:
        out.append(max(0.0, min(255.0, row[0] * r + row[1] * g + row[2] * b)))
    return tuple(out)  # type: ignore[return-value]


def _artist_label(artist: Any, fallback: str) -> str:
    try:
        label = artist.get_label()
        if label and not str(label).startswith("_"):
            return str(label)
    except Exception:
        pass
    try:
        gid = artist.get_gid()
        if gid:
            return str(gid)
    except Exception:
        pass
    return fallback


def _series_colors(ax: Any) -> list[tuple[str, Any, tuple[float, float, float]]]:
    out = []
    for idx, line in enumerate(getattr(ax, "lines", [])):
        try:
            if not line.get_visible():
                continue
            rgb = _rgb255(line.get_color())
        except Exception:
            rgb = None
        if rgb is not None:
            out.append((_artist_label(line, f"line:{idx}"), line, rgb))
    for idx, patch in enumerate(getattr(ax, "patches", [])):
        if patch is getattr(ax, "patch", None):
            continue
        try:
            if not patch.get_visible():
                continue
            fc = patch.get_facecolor()
            if len(fc) >= 4 and fc[3] <= 0.05:
                continue
            rgb = tuple(v * 255.0 for v in fc[:3])
        except Exception:
            continue
        out.append((_artist_label(patch, f"patch:{idx}"), patch, rgb))
    return out


def _fire_colorblind_confusable(fig: Any, config: ScivcdConfig) -> list[Finding]:
    threshold = float(getattr(config, "colorblind_delta_e_min", 12.0))
    out: list[Finding] = []
    for ax in _data_axes(fig):
        colors = _series_colors(ax)
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                name_a, artist_a, rgb_a = colors[i]
                name_b, _artist_b, rgb_b = colors[j]
                for mode in ("deuteranopia", "protanopia"):
                    dist = _delta_e(_simulate_cvd(rgb_a, mode), _simulate_cvd(rgb_b, mode))
                    if dist < threshold:
                        out.append(Finding(
                            check_id="colorblind_confusable",
                            severity=Severity.HIGH,
                            category=Category.ACCESSIBILITY,
                            stage=Stage.TIER2,
                            message=(f"series '{name_a}' and '{name_b}' are confusable under {mode} "
                                     f"(ΔE={dist:.1f} < {threshold:.1f})"),
                            fix_suggestion="choose a more colorblind-robust palette, or add line style/marker/label redundancy",
                            evidence={"series_a": name_a, "series_b": name_b, "cvd_mode": mode, "delta_e": round(dist, 3), "threshold": threshold},
                            artist=artist_a,
                        ))
                        break
    return out


register(CheckSpec(
    id="colorblind_confusable",
    severity=Severity.HIGH,
    category=Category.ACCESSIBILITY,
    stage=Stage.TIER2,
    fire=_fire_colorblind_confusable,
    description="Series colors collapse under common color-vision-deficiency simulations",
    config_keys=("colorblind_delta_e_min",),
))

__all__ = ["_fire_colorblind_confusable"]
