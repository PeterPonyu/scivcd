"""Public API of ``scivcd.core``.

This subpackage is the foundation of the scivcd rewrite: enums,
dataclasses, the check registry, and the config loader. Every other
scivcd subpackage depends on these symbols and nothing else inside
scivcd.
"""

from .config import ScivcdConfig
from .registry import CheckSpec, get, iter_checks, register, unregister
from .state import Finding, FigureLifecycleState
from .types import Category, Severity, Stage

__all__ = [
    # enums
    "Severity",
    "Category",
    "Stage",
    # dataclasses
    "Finding",
    "FigureLifecycleState",
    "CheckSpec",
    # registry API
    "register",
    "unregister",
    "get",
    "iter_checks",
    # config
    "ScivcdConfig",
]
