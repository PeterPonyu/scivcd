"""Exemption mechanisms for scivcd.

Three orthogonal ways to silence a check on a specific artist (or set of
artists), all routed through one fast ``is_exempt(artist, check_id)``
function that detectors call:

1. **Context manager** — ``with scivcd.exempt("annotation_data_overlap"):
   ...`` pushes ``check_id``s onto a thread-local stack. Every matplotlib
   ``Artist`` whose ``__init__`` runs inside the block is tagged via a
   lightweight hook so later check passes know to skip it.
2. **Direct helper** — ``scivcd.ignore("check_a", "check_b")`` returns a
   ``{"gid": "scivcd-ignore:check_a,check_b"}`` dict that can be spread
   into an Artist factory call::

       ax.text(..., **scivcd.ignore("non_panel_bold_text"))

   The detector framework recognises the sentinel ``gid`` prefix and
   treats it as an exemption for the listed ids.
3. **Artist attribute** — set ``artist._scivcd_exempt = {"check_id"}``
   directly on any Artist (or ``fig._scivcd_exempt = {...}`` for a whole
   figure).

``is_exempt(artist, check_id)`` consults all three in O(1):

    * direct ``_scivcd_exempt`` set on the artist,
    * ancestor figure's ``_scivcd_exempt`` set,
    * sentinel ``gid`` prefix ``scivcd-ignore:``,
    * thread-local stack tag left by the ``exempt()`` context manager.

Also provides ``"*"`` / ``"all"`` as wildcard ids in any of the three
mechanisms to exempt an artist from every check.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Set

__all__ = ["exempt", "ignore", "is_exempt"]


# The sentinel prefix that ``ignore()`` stamps into the ``gid`` kwarg of an
# Artist. Detectors strip the prefix and split on commas to recover the
# exempted check ids.
_GID_SENTINEL = "scivcd-ignore:"

# Attribute name used on Artists / Figures to carry an exemption set.
_ATTR = "_scivcd_exempt"

# Wildcards — if any exemption set contains one of these, every check is
# exempt on that artist.
_WILDCARDS = frozenset({"*", "all", "ALL"})


# Thread-local stack of active exemption sets. Each entry is a frozenset
# of check ids. ``_install_ctx_hook`` patches ``Artist.__init__`` to copy
# the union of the current stack onto every Artist created inside an
# ``exempt()`` block.
class _ExemptState(threading.local):
    def __init__(self) -> None:  # pragma: no cover - trivial
        self.stack: list[frozenset[str]] = []


_state = _ExemptState()


# ---------------------------------------------------------------------------
# Artist.__init__ hook — lazy so importing this module does not monkey-patch
# matplotlib unless someone actually uses ``exempt()``.
# ---------------------------------------------------------------------------


_hook_installed = False


def _install_ctx_hook() -> None:
    """Monkey-patch ``Artist.__init__`` once so new Artists inside an
    active ``exempt()`` block inherit the current stack's union.

    Safe to call repeatedly; idempotent.
    """
    global _hook_installed
    if _hook_installed:
        return
    try:
        from matplotlib.artist import Artist
    except Exception:  # pragma: no cover - matplotlib missing
        return

    _orig_init = Artist.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        _orig_init(self, *args, **kwargs)
        stack = _state.stack
        if stack:
            # Union of every active frame; new frames only add, never subtract.
            ids: Set[str] = set()
            for frame in stack:
                ids.update(frame)
            existing = getattr(self, _ATTR, None)
            if isinstance(existing, set):
                existing.update(ids)
            else:
                try:
                    setattr(self, _ATTR, set(ids))
                except Exception:  # pragma: no cover - exotic subclasses
                    pass

    # Preserve metadata so introspection still looks sensible.
    try:
        _patched_init.__wrapped__ = _orig_init  # type: ignore[attr-defined]
        _patched_init.__doc__ = _orig_init.__doc__
    except Exception:  # pragma: no cover
        pass

    Artist.__init__ = _patched_init  # type: ignore[assignment]
    _hook_installed = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@contextmanager
def exempt(*check_ids: str) -> Iterator[None]:
    """Context manager: exempt every Artist created inside ``with`` from
    the given ``check_ids``.

    Passing no ids is a no-op. Use ``"*"`` to exempt from every check::

        with scivcd.exempt("*"):
            ax.annotate(...)   # free from all checks
    """
    ids = frozenset(str(x) for x in check_ids if x)
    if not ids:
        yield
        return
    _install_ctx_hook()
    _state.stack.append(ids)
    try:
        yield
    finally:
        # Pop the matching frame; guard against misuse where the user
        # fiddled with the stack manually.
        try:
            _state.stack.pop()
        except IndexError:  # pragma: no cover - defensive
            pass


def ignore(*check_ids: str) -> dict:
    """Return kwargs that tag an Artist as exempt from ``check_ids``.

    The result is meant to be splatted into any matplotlib factory that
    accepts ``gid``::

        ax.text(0.5, 0.5, "note", **scivcd.ignore("non_panel_bold_text"))

    The sentinel ``gid`` survives through matplotlib without affecting
    rendering, and ``is_exempt`` recognises it at detection time.
    """
    clean = [str(x) for x in check_ids if x]
    if not clean:
        return {}
    return {"gid": _GID_SENTINEL + ",".join(clean)}


def is_exempt(artist: Any, check_id: str) -> bool:
    """Fast O(1) check: is ``artist`` exempt from ``check_id``?

    Consults, in order:
        1. The artist's own ``_scivcd_exempt`` set.
        2. Its parent figure's ``_scivcd_exempt`` set (if resolvable).
        3. The sentinel ``gid`` prefix written by ``ignore()``.
        4. The thread-local stack of active ``exempt()`` blocks.

    Returns ``True`` at the first hit; never raises. Wildcards ``"*"`` and
    ``"all"`` match every check id.
    """
    if artist is None:
        return _stack_exempts(check_id)

    # (1) Artist-level set — the O(1) hot path.
    direct = getattr(artist, _ATTR, None)
    if _set_matches(direct, check_id):
        return True

    # (2) Figure-level set. ``get_figure`` may return None on un-parented
    # artists; guard both attribute and call failures.
    fig = _safe_get_figure(artist)
    if fig is not None:
        fig_set = getattr(fig, _ATTR, None)
        if _set_matches(fig_set, check_id):
            return True

    # (3) ``gid`` sentinel — cheap string check.
    try:
        gid = artist.get_gid() if hasattr(artist, "get_gid") else None
    except Exception:
        gid = None
    if isinstance(gid, str) and gid.startswith(_GID_SENTINEL):
        body = gid[len(_GID_SENTINEL):]
        if body:
            parts = {p.strip() for p in body.split(",") if p.strip()}
            if _WILDCARDS & parts or check_id in parts:
                return True

    # (4) Thread-local stack — covers artists created inside an active
    # ``exempt()`` block before the hook had a chance to tag them (for
    # example when the artist existed before the block entered).
    return _stack_exempts(check_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _set_matches(exempt_set: Any, check_id: str) -> bool:
    """Return True if ``exempt_set`` is a non-empty iterable containing
    ``check_id`` or a wildcard.

    Accepts ``set``, ``frozenset``, ``tuple``, or ``list`` for
    convenience; anything else is ignored.
    """
    if not exempt_set:
        return False
    if isinstance(exempt_set, (set, frozenset)):
        if exempt_set & _WILDCARDS:
            return True
        return check_id in exempt_set
    if isinstance(exempt_set, (list, tuple)):
        for item in exempt_set:
            if item in _WILDCARDS or item == check_id:
                return True
    return False


def _stack_exempts(check_id: str) -> bool:
    stack = _state.stack
    if not stack:
        return False
    for frame in stack:
        if frame & _WILDCARDS or check_id in frame:
            return True
    return False


def _safe_get_figure(artist: Any) -> Any:
    """Best-effort ``artist.get_figure()`` that never raises."""
    getter = getattr(artist, "get_figure", None)
    if getter is None:
        return getattr(artist, "figure", None)
    try:
        return getter()
    except Exception:  # pragma: no cover - exotic artists
        return getattr(artist, "figure", None)


def _iter_exempt_ids(artist: Any) -> Iterable[str]:
    """Yield every exempt id currently attached to ``artist``.

    Kept as a small internal helper for tests / diagnostics.
    """
    direct = getattr(artist, _ATTR, None)
    if isinstance(direct, (set, frozenset, list, tuple)):
        for item in direct:
            yield str(item)
    fig = _safe_get_figure(artist)
    if fig is not None:
        fig_set = getattr(fig, _ATTR, None)
        if isinstance(fig_set, (set, frozenset, list, tuple)):
            for item in fig_set:
                yield str(item)
