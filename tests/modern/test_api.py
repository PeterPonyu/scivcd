"""Tests for the top-level scivcd.check() entrypoint and Report object.

Skips gracefully if the API is not yet implemented.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import pytest

scivcd = pytest.importorskip(
    "scivcd",
    reason="scivcd top-level API not yet implemented",
)
for _sym in ("check", "Report"):
    if not hasattr(scivcd, _sym):
        pytest.skip(
            f"scivcd.{_sym} not yet implemented",
            allow_module_level=True,
        )

check = scivcd.check
Report = scivcd.Report
iter_checks = scivcd.iter_checks if hasattr(scivcd, "iter_checks") else None


def _any_checks_registered() -> bool:
    """Return True if at least one check is registered in the global registry."""
    if iter_checks is None:
        return False
    return any(True for _ in iter_checks(enabled_only=False))


# ---------------------------------------------------------------------------
# Fixtures (local so this module is self-contained even without conftest)
# ---------------------------------------------------------------------------

@pytest.fixture()
def _clean_fig():
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.linspace(0, 2 * np.pi, 100)
    ax.plot(x, np.sin(x), lw=1.5)
    ax.set_xlabel("x", fontsize=11)
    ax.set_ylabel("sin(x)", fontsize=11)
    ax.set_title("Clean", fontsize=12)
    fig.tight_layout()
    yield fig
    plt.close(fig)


@pytest.fixture()
def _overlap_fig():
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.plot([0, 1], [0, 1], color="black", lw=2)
    ax.text(
        0.5, 0.5, "Dense annotation label",
        transform=ax.transAxes, ha="center", va="center", fontsize=14,
    )
    # Stack many text objects to trigger text-density or overlap checks
    for i in range(8):
        ax.text(
            0.05 + i * 0.12, 0.5,
            f"lbl{i}",
            transform=ax.transAxes, fontsize=8,
        )
    fig.canvas.draw()
    yield fig
    plt.close(fig)


# ---------------------------------------------------------------------------
# scivcd.check() return type
# ---------------------------------------------------------------------------

class TestCheckReturnsReport:
    def test_returns_report_instance(self, _clean_fig):
        report = check(_clean_fig)
        assert isinstance(report, Report)

    def test_report_has_findings_attribute(self, _clean_fig):
        report = check(_clean_fig)
        assert hasattr(report, "findings")

    def test_findings_is_iterable(self, _clean_fig):
        report = check(_clean_fig)
        _ = list(report.findings)


# ---------------------------------------------------------------------------
# Report on a clean figure
# ---------------------------------------------------------------------------

class TestCleanFigReport:
    def test_clean_fig_no_findings(self, _clean_fig):
        report = check(_clean_fig)
        assert len(list(report.findings)) == 0

    def test_report_bool_false_when_no_findings(self, _clean_fig):
        report = check(_clean_fig)
        assert not bool(report)


# ---------------------------------------------------------------------------
# Report on a figure with overlap
# ---------------------------------------------------------------------------

class TestOverlapFigReport:
    def test_overlap_fig_has_at_least_one_finding(self, _overlap_fig):
        if not _any_checks_registered():
            pytest.skip("No checks registered yet — overlap detection unavailable")
        report = check(_overlap_fig)
        assert len(list(report.findings)) >= 1

    def test_report_bool_true_when_findings(self, _overlap_fig):
        if not _any_checks_registered():
            pytest.skip("No checks registered yet — overlap detection unavailable")
        report = check(_overlap_fig)
        assert bool(report)


# ---------------------------------------------------------------------------
# Report.has()
# ---------------------------------------------------------------------------

class TestReportHas:
    def test_has_returns_false_for_absent_id(self, _clean_fig):
        report = check(_clean_fig)
        assert not report.has("nonexistent_check_id_xyz")

    def test_has_returns_true_for_present_id(self, _overlap_fig):
        report = check(_overlap_fig)
        # Grab the first finding's check_id and verify .has() recognises it.
        findings = list(report.findings)
        if not findings:
            pytest.skip("No findings on overlap figure — cannot test has()")
        first_id = findings[0].check_id
        assert report.has(first_id)


# ---------------------------------------------------------------------------
# Report.to_markdown()
# ---------------------------------------------------------------------------

class TestReportToMarkdown:
    def test_to_markdown_returns_string(self, _clean_fig):
        report = check(_clean_fig)
        md = report.to_markdown()
        assert isinstance(md, str)

    def test_to_markdown_non_empty_when_findings(self, _overlap_fig):
        report = check(_overlap_fig)
        md = report.to_markdown()
        if bool(report):
            assert len(md) > 0

    def test_to_markdown_contains_check_id(self, _overlap_fig):
        report = check(_overlap_fig)
        findings = list(report.findings)
        if not findings:
            pytest.skip("No findings — cannot verify check_id in markdown")
        md = report.to_markdown()
        assert findings[0].check_id in md
