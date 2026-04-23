"""Check registry for scivcd.

Every check in the scivcd pipeline is described by a frozen
``CheckSpec``. The registry is a module-level dict keyed by
``spec.id``; ``register`` refuses duplicates so a misnamed check fails
loud at import time.

``iter_checks`` is the primary read API used by the executor to walk
registered checks for a given stage / category / enabled state. It is
also the contract Worker 2 onwards codes against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterator, Optional

from .state import Finding
from .types import Category, Severity, Stage

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from .config import ScivcdConfig


@dataclass(frozen=True)
class CheckSpec:
    """Declarative description of a scivcd check.

    Attributes
    ----------
    id:
        Stable, unique identifier. Used for config, reports, and
        finding.check_id back-reference.
    severity, category, stage:
        Classification axes mirrored onto every finding the check
        produces.
    fire:
        Callable ``(fig, config) -> list[Finding]`` that actually runs
        the check. Must not mutate ``fig``.
    autofix:
        Optional callable ``(fig, findings, config) -> list`` that
        attempts to remediate findings in-place and returns a list of
        applied fix records.
    default_enabled:
        Whether the check runs when it is not explicitly enabled or
        disabled in config.
    config_keys:
        Tuple of ``ScivcdConfig`` attribute names the check reads.
        Purely documentary (for tooling), not enforced.
    version:
        Integer bumped when the check's semantics change incompatibly.
    description:
        One-line human-readable description.
    """

    id: str
    severity: Severity
    category: Category
    stage: Stage
    fire: Callable
    autofix: Optional[Callable] = None
    default_enabled: bool = True
    config_keys: tuple[str, ...] = ()
    version: int = 1
    description: str = ""


# Module-level registry. Access from outside goes through the public
# helpers below so we can later swap this for a richer container
# without breaking callers.
_REGISTRY: dict[str, CheckSpec] = {}


def register(spec: CheckSpec) -> CheckSpec:
    """Register ``spec``; raise ``ValueError`` if its id is taken.

    Returns ``spec`` so ``register`` can be used as a decorator-style
    pass-through::

        MY_CHECK = register(CheckSpec(id="my.check", ...))
    """
    if not isinstance(spec, CheckSpec):
        raise TypeError(
            f"register expects CheckSpec, got {type(spec).__name__}"
        )
    if spec.id in _REGISTRY:
        raise ValueError(f"Duplicate check id: {spec.id}")
    _REGISTRY[spec.id] = spec
    return spec


def unregister(check_id: str) -> None:
    """Remove ``check_id`` from the registry.

    No-ops silently if the id is not registered, so repeated teardown
    in tests is safe.
    """
    _REGISTRY.pop(check_id, None)


def get(check_id: str) -> CheckSpec:
    """Return the spec for ``check_id`` or raise ``KeyError``."""
    try:
        return _REGISTRY[check_id]
    except KeyError as exc:
        raise KeyError(f"No check registered with id: {check_id}") from exc


def iter_checks(
    *,
    stage: Optional[Stage] = None,
    category: Optional[Category] = None,
    enabled_only: bool = True,
    config: Optional["ScivcdConfig"] = None,
) -> Iterator[CheckSpec]:
    """Yield registered checks filtered by stage/category/enabled state.

    Parameters
    ----------
    stage:
        If given, only checks for this lifecycle stage are yielded.
    category:
        If given, only checks in this category are yielded.
    enabled_only:
        When True (default), a check is skipped if it is either
        disabled in ``config.disabled_checks`` or has
        ``default_enabled=False`` and is not explicitly enabled in
        config. When False, all matching checks are yielded regardless
        of config.
    config:
        Optional ``ScivcdConfig`` consulted for disabled/severity-floor
        information. When None, ``enabled_only`` uses only the check's
        ``default_enabled``.
    """
    if stage is not None:
        stage = Stage.coerce(stage)
    if category is not None:
        category = Category.coerce(category)

    disabled = frozenset()
    severity_floor: Optional[Severity] = None
    if config is not None:
        disabled = frozenset(config.disabled_checks or ())
        severity_floor = getattr(config, "severity_floor", None)

    # Iterate a snapshot so callers may (un)register mid-iteration.
    for spec in list(_REGISTRY.values()):
        if stage is not None and spec.stage is not stage:
            continue
        if category is not None and spec.category is not category:
            continue
        if enabled_only:
            if spec.id in disabled:
                continue
            if not spec.default_enabled:
                continue
            if (
                severity_floor is not None
                and spec.severity.value > severity_floor.value
            ):
                # Less serious than the floor -> skip.
                continue
        yield spec


def _clear_registry_for_tests() -> None:
    """Test-only hook to wipe the registry. Not part of the public API."""
    _REGISTRY.clear()


__all__ = [
    "CheckSpec",
    "register",
    "unregister",
    "get",
    "iter_checks",
]
