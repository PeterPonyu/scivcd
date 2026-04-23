"""Core enums for scivcd: severity, category, and lifecycle stage.

These enums define the three-dimensional classification of every finding
produced by the new scivcd pipeline. They also provide a ``coerce``
classmethod that accepts legacy string names from the scripts/vcd/*
codebase so the rewrite can be rolled out incrementally.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Severity(Enum):
    """Finding severity, ordered from most to least serious.

    The integer values encode severity order: ``BLOCKER`` (0) is the
    most serious, ``INFO`` (4) the least. Callers may compare
    ``severity.value <= other.value`` to ask "at least as serious as".
    """

    BLOCKER = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    INFO = 4

    @classmethod
    def coerce(cls, value: Any) -> "Severity":
        """Accept legacy strings, the new names, or raw enum values.

        Legacy mapping:
            ``CRITICAL`` -> ``BLOCKER``
            ``MAJOR``    -> ``HIGH``
            ``MINOR``    -> ``MEDIUM``

        Also accepts any member name (case-insensitive) and integer
        values (``0..4``). Raises ``ValueError`` on unknown input.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            try:
                return cls(value)
            except ValueError as exc:
                raise ValueError(f"Unknown Severity value: {value!r}") from exc
        if isinstance(value, str):
            key = value.strip().upper()
            legacy = {
                "CRITICAL": cls.BLOCKER,
                "MAJOR": cls.HIGH,
                "MINOR": cls.MEDIUM,
            }
            if key in legacy:
                return legacy[key]
            try:
                return cls[key]
            except KeyError as exc:
                raise ValueError(f"Unknown Severity name: {value!r}") from exc
        raise ValueError(
            f"Cannot coerce {type(value).__name__} to Severity: {value!r}"
        )


class Category(Enum):
    """Top-level classification of what a finding is about."""

    LAYOUT = "LAYOUT"
    TYPOGRAPHY = "TYPOGRAPHY"
    CONTENT = "CONTENT"
    POLICY = "POLICY"
    ACCESSIBILITY = "ACCESSIBILITY"

    @classmethod
    def coerce(cls, value: Any) -> "Category":
        """Accept a Category, its member name, or its string value."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            key = value.strip().upper()
            # Try the member name first, then fall back to .value
            if key in cls.__members__:
                return cls[key]
            for member in cls:
                if member.value.upper() == key:
                    return member
            raise ValueError(f"Unknown Category: {value!r}")
        raise ValueError(
            f"Cannot coerce {type(value).__name__} to Category: {value!r}"
        )


class Stage(Enum):
    """Lifecycle stage at which a check fires.

    TIER1 runs during artist construction (pre-layout), so checks see
    only the objects they are told about. TIER2 runs after the figure
    has been laid out for saving, so checks see the full rendered
    geometry.
    """

    TIER1 = 1  # artist-local, pre-layout
    TIER2 = 2  # post-layout, savefig-time

    @classmethod
    def coerce(cls, value: Any) -> "Stage":
        """Accept a Stage, its member name, or its integer value."""
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            try:
                return cls(value)
            except ValueError as exc:
                raise ValueError(f"Unknown Stage value: {value!r}") from exc
        if isinstance(value, str):
            key = value.strip().upper()
            if key in cls.__members__:
                return cls[key]
            raise ValueError(f"Unknown Stage name: {value!r}")
        raise ValueError(
            f"Cannot coerce {type(value).__name__} to Stage: {value!r}"
        )


__all__ = ["Severity", "Category", "Stage"]
