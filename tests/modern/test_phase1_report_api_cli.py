"""Phase 1 report schema, API, and CLI compatibility tests."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import scivcd
from scivcd.core import Category, Finding, Severity, Stage
from scivcd.reports import json as json_report
from scivcd.reports import markdown as markdown_report


def _finding(*, evidence=None) -> Finding:
    return Finding(
        check_id="phase1.schema",
        severity=Severity.INFO,
        category=Category.POLICY,
        stage=Stage.TIER2,
        message="schema probe",
        evidence=evidence,
    )


def test_finding_evidence_serializes_only_when_present():
    without = _finding().to_dict()
    with_evidence = _finding(evidence={"threshold": 7.0}).to_dict()

    assert "evidence" not in without
    assert with_evidence["evidence"] == {"threshold": 7.0}


def test_report_metadata_round_trips_through_json_and_markdown_helpers(tmp_path: Path):
    report = scivcd.Report(
        findings=[_finding(evidence={"source_stage": "post_export"})],
        figure_label="export.png",
        metadata={
            "source_stage": "post_export",
            "target_path": "export.png",
            "audit_limitations": [],
        },
    )

    payload = json.loads(json_report.render(report))
    assert payload["metadata"]["source_stage"] == "post_export"
    assert payload["findings"][0]["evidence"]["source_stage"] == "post_export"

    md = markdown_report.render(report)
    assert "source_stage" in md
    assert "post_export" in md

    out = tmp_path / "report.json"
    report.to_json(out)
    assert json.loads(out.read_text())["metadata"]["target_path"] == "export.png"


def test_check_api_remains_compatible_for_matplotlib_figures():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("x", fontsize=11)
    ax.set_ylabel("y", fontsize=11)
    ax.set_title("compatible", fontsize=12)
    fig.tight_layout()
    try:
        report = scivcd.check(fig)
    finally:
        plt.close(fig)

    assert isinstance(report, scivcd.Report)
    assert hasattr(report, "findings")
    assert isinstance(report.metadata, dict)
