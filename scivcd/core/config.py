"""Configuration dataclass for scivcd.

``ScivcdConfig`` holds every numeric threshold and behavior toggle the
check pipeline reads. It is deliberately flat so it stays ergonomic in
both Python and TOML.

Three loaders are provided:

* ``ScivcdConfig.from_toml`` - load from an arbitrary TOML file.
* ``ScivcdConfig.from_pyproject`` - load ``[tool.scivcd]`` from a
  pyproject.toml (walks upward from CWD if the path is None).
* ``ScivcdConfig.discover`` - walk upward from CWD to find a
  pyproject.toml; fall back to hard-coded defaults.

All loaders silently fall back to defaults if the file or section is
missing, so callers may always ask for a config without error
handling boilerplate.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from .types import Severity

# Python 3.11+ has tomllib in stdlib. On older interpreters fall back
# to the pip-installable ``tomli`` package.
try:  # pragma: no cover - trivial import guard
    import tomllib as _tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as _tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        _tomllib = None  # type: ignore[assignment]


@dataclass
class ScivcdConfig:
    """All thresholds and behavior toggles for the scivcd pipeline."""

    # --- layout thresholds ---
    gutter_hspace_max: float = 0.60
    gutter_wspace_max: float = 0.55
    whitespace_content_min: float = 0.45
    border_left_max: float = 0.18
    border_right_min: float = 0.88
    border_top_min: float = 0.88
    border_bottom_max: float = 0.16
    title_axes_gap_max: float = 0.08
    row_alignment_tol: float = 0.025
    legend_tick_clearance_px: float = 8.0

    # --- typography thresholds ---
    floor_pt: float = 9.0
    large_canvas_floor_pt: float = 10.0
    large_canvas_threshold_in: float = 20.0
    title_min_pt: float = 11.0
    label_min_pt: float = 10.0
    max_distinct_sizes: int = 6

    # --- policy thresholds ---
    panel_label_radius: float = 0.08
    panel_label_companion_horiz: float = 0.12
    panel_label_companion_vert: float = 0.025

    # --- content thresholds ---
    text_density_max_per_sqin: float = 2.2
    min_overlap_px2: float = 150.0
    annotation_min_pt: float = 10.0
    colorblind_delta_e_min: float = 12.0
    composed_scale: float = 1.0
    final_print_scale: float = 1.0
    effective_font_floors: dict[str, float] = field(default_factory=lambda: {"title": 11.0, "axis_label": 10.0, "tick": 7.0, "legend": 8.0, "annotation": 8.0, "panel_label": 10.0})

    # --- behavior toggles ---
    disabled_checks: frozenset[str] = field(default_factory=frozenset)
    severity_floor: Severity = Severity.INFO
    autofix_enabled: bool = False

    # ----- loaders -----------------------------------------------------

    @classmethod
    def from_toml(cls, path: Path) -> "ScivcdConfig":
        """Load a config from ``path``.

        The file is searched for a top-level ``[scivcd]`` table or a
        nested ``[tool.scivcd]`` table (pyproject convention). If
        neither exists, the defaults are returned.
        """
        path = Path(path)
        if _tomllib is None:
            raise RuntimeError(
                "TOML support requires Python 3.11+ (tomllib) or the "
                "'tomli' package."
            )
        if not path.is_file():
            return cls()
        with path.open("rb") as fh:
            data = _tomllib.load(fh)
        section = _extract_section(data)
        return cls._from_mapping(section) if section else cls()

    @classmethod
    def from_pyproject(cls, path: Optional[Path] = None) -> "ScivcdConfig":
        """Load ``[tool.scivcd]`` from a pyproject.toml.

        If ``path`` is None, walk upward from CWD to find the nearest
        ``pyproject.toml``. If none is found the defaults are returned.
        """
        if path is None:
            found = _walk_up_for("pyproject.toml")
            if found is None:
                return cls()
            path = found
        return cls.from_toml(path)

    @classmethod
    def discover(cls) -> "ScivcdConfig":
        """Walk from CWD upward looking for a scivcd config.

        Checks (in order) for a ``scivcd.toml`` or ``pyproject.toml``
        in each ancestor directory. Returns the first config that
        successfully parses; falls back to defaults if nothing is
        found.
        """
        for name in ("scivcd.toml", "pyproject.toml"):
            found = _walk_up_for(name)
            if found is not None:
                return cls.from_toml(found)
        return cls()

    # ----- internal ----------------------------------------------------

    @classmethod
    def _from_mapping(cls, data: Mapping[str, Any]) -> "ScivcdConfig":
        """Build a config from a dict, ignoring unknown keys."""
        fields = {f.name: f for f in dataclasses.fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if key not in fields:
                continue
            kwargs[key] = _coerce_field(key, value)
        return cls(**kwargs)


def _coerce_field(name: str, value: Any) -> Any:
    """Coerce a raw TOML value to the type expected by ``ScivcdConfig``."""
    if name == "severity_floor":
        return Severity.coerce(value)
    if name == "disabled_checks":
        if isinstance(value, (list, tuple, set, frozenset)):
            return frozenset(str(v) for v in value)
        raise ValueError(
            f"disabled_checks must be a list of strings, got {type(value).__name__}"
        )
    return value


def _extract_section(data: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """Pull the scivcd table out of parsed TOML data.

    Supports both ``[scivcd]`` (standalone config) and
    ``[tool.scivcd]`` (pyproject-style).
    """
    tool = data.get("tool")
    if isinstance(tool, Mapping):
        scivcd = tool.get("scivcd")
        if isinstance(scivcd, Mapping):
            return scivcd
    scivcd = data.get("scivcd")
    if isinstance(scivcd, Mapping):
        return scivcd
    return None


def _walk_up_for(filename: str) -> Optional[Path]:
    """Search from CWD upward for a file named ``filename``."""
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / filename
        if candidate.is_file():
            return candidate
    return None


__all__ = ["ScivcdConfig"]
