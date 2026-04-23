"""Tests for post-export SciVCD audit API and CLI."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import scivcd
from scivcd.cli import main as scivcd_cli


def _write_png(path):
    fig, ax = plt.subplots(figsize=(2, 1))
    ax.plot([0, 1], [0, 1])
    fig.savefig(path)
    plt.close(fig)


def test_audit_export_png_returns_post_export_report(tmp_path):
    target = tmp_path / "fixture.png"
    _write_png(target)

    report = scivcd.audit_export(target)

    assert report.metadata["source_stage"] == "post_export"
    assert report.metadata["target_path"] == str(target)
    assert report.metadata["format"] == "png"
    assert report.metadata["audit_limitations"] == []
    assert report.metadata["width_px"] > 0
    assert report.metadata["height_px"] > 0


def test_audit_export_cli_json_emits_metadata(tmp_path, capsys):
    target = tmp_path / "fixture.png"
    _write_png(target)

    exit_code = scivcd_cli(["audit-export", str(target), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["metadata"]["source_stage"] == "post_export"
    assert payload["metadata"]["format"] == "png"
    assert payload["findings"] == []


def test_audit_export_pdf_backend_missing_is_graceful(monkeypatch, tmp_path):
    target = tmp_path / "fixture.pdf"
    target.write_bytes(b"%PDF-1.4\n%%EOF\n")

    import scivcd.export_audit as export_audit

    monkeypatch.setattr(export_audit, "_load_pymupdf", lambda: None)

    report = scivcd.audit_export(target)

    assert report.metadata["source_stage"] == "post_export"
    assert report.metadata["audit_unavailable"] is True
    assert "pdf_backend_unavailable:pymupdf" in report.metadata["audit_limitations"]
    assert list(report.findings) == []
