"""Per-figure finding and lifecycle state for scivcd.

``Finding`` is the canonical record emitted by every check. It replaces
the older ``FindingRecord`` used under ``scripts/vcd/lifecycle/`` but
keeps a superset of the fields so the new pipeline can consume legacy
data by round-tripping through ``to_dict``.

``FigureLifecycleState`` collects findings + fixes + timings for a
single figure across the TIER1 and TIER2 stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .types import Category, Severity, Stage


@dataclass
class Finding:
    """A single scivcd finding.

    Attributes
    ----------
    check_id:
        Stable identifier of the check that produced the finding
        (matches ``CheckSpec.id``).
    severity, category, stage:
        Three-axis classification; see ``scivcd.core.types``.
    message:
        Human-readable summary of what is wrong.
    call_site:
        Optional ``"file.py:lineno"`` string pointing at the code that
        created the problematic artist.
    fix_suggestion:
        Optional actionable suggestion for the caller. Autofix
        routines may key off this.
    evidence:
        Optional JSON-serialisable structured details that explain how
        the finding was derived (thresholds, transforms, export metadata).
        Omitted from ``to_dict()`` when absent to preserve the historical
        report schema for callers that do not use it.
    artist:
        Optional matplotlib artist associated with the finding. Kept
        out of equality / repr so findings remain comparable and
        JSON-ish serialisable without pulling matplotlib into pickles.
    """

    check_id: str
    severity: Severity
    category: Category
    stage: Stage
    message: str
    call_site: Optional[str] = None
    fix_suggestion: Optional[str] = None
    evidence: Optional[dict[str, Any]] = None
    artist: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        # Accept legacy strings / raw values for the enum fields so
        # call sites migrated from scripts/vcd/* keep working.
        self.severity = Severity.coerce(self.severity)
        self.category = Category.coerce(self.category)
        self.stage = Stage.coerce(self.stage)

    def to_dict(self) -> dict:
        """JSON-serialisable representation (drops the live artist)."""
        data = {
            "check_id": self.check_id,
            "severity": self.severity.name,
            "category": self.category.name,
            "stage": self.stage.name,
            "message": self.message,
            "call_site": self.call_site,
            "fix_suggestion": self.fix_suggestion,
        }
        if self.evidence is not None:
            data["evidence"] = dict(self.evidence)
        return data


@dataclass
class FigureLifecycleState:
    """Mutable state accumulated while processing one figure.

    Equivalent to the existing ``scripts/vcd/lifecycle/state.py`` state,
    but using the new ``Finding`` dataclass instead of the legacy
    ``FindingRecord``. ``events``, ``fixes``, and ``timings`` are kept
    as plain containers because their shape is pipeline-specific and
    the core package does not want to constrain it.
    """

    figure_label: str = ""
    events: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    fixes: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)

    def add_finding(self, finding: Finding) -> None:
        """Append a finding, validating its type."""
        if not isinstance(finding, Finding):
            raise TypeError(
                f"add_finding expects Finding, got {type(finding).__name__}"
            )
        self.findings.append(finding)

    def findings_by_severity(self, sev: Severity) -> list[Finding]:
        """Return every finding at exactly ``sev``."""
        sev = Severity.coerce(sev)
        return [f for f in self.findings if f.severity is sev]

    def findings_by_category(self, cat: Category) -> list[Finding]:
        """Return every finding in category ``cat``."""
        cat = Category.coerce(cat)
        return [f for f in self.findings if f.category is cat]

    def to_dict(self) -> dict:
        """JSON-serialisable representation of the full lifecycle."""
        return {
            "figure_label": self.figure_label,
            "events": list(self.events),
            "findings": [f.to_dict() for f in self.findings],
            "fixes": list(self.fixes),
            "timings": dict(self.timings),
        }


__all__ = ["Finding", "FigureLifecycleState"]
