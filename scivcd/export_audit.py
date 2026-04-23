"""Post-export artifact audit entry point for SciVCD.

The Phase 1 MVP keeps export auditing deliberately lightweight and
backend-optional. Raster/PDF metadata is recorded when a local backend is
available; otherwise the returned report documents the limitation instead
of crashing. Findings produced here use ``Stage.TIER2`` and report-level
``metadata["source_stage"] == "post_export"`` to avoid introducing a new
public stage enum.
"""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any, Optional

from scivcd.api import Report
from scivcd.core import Category, Finding, ScivcdConfig, Severity, Stage

_RASTER_FORMATS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
_PDF_FORMATS = {".pdf"}
_SUPPORTED_FORMATS = _RASTER_FORMATS | _PDF_FORMATS


def audit_export(
    path: str | Path,
    *,
    config: Optional[ScivcdConfig] = None,
    require_backend: bool = False,
) -> Report:
    """Audit an exported figure artifact and return a SciVCD ``Report``.

    Parameters
    ----------
    path:
        Path to a PDF/PNG/JPG-like exported figure artifact.
    config:
        Reserved for future thresholded export checks. Accepted now so the
        public signature mirrors ``check(fig, config=...)``.
    require_backend:
        When true, unavailable optional PDF backends are represented as a HIGH
        finding in addition to report metadata. This lets gate/CI callers
        convert required-but-unavailable audits into exit code 3.
    """
    del config  # Phase 1 schema/API slice: no thresholds consumed yet.

    started = time.perf_counter()
    target = Path(path)
    suffix = target.suffix.lower()
    fmt = suffix.lstrip(".") or "unknown"
    limitations: list[str] = []
    metadata: dict[str, Any] = {
        "source_stage": "post_export",
        "target_path": str(target),
        "format": fmt,
        "audit_limitations": limitations,
    }
    findings: list[Finding] = []

    if not target.exists():
        findings.append(_finding(
            "export.path_missing",
            Severity.HIGH,
            f"export artifact does not exist: {target}",
            evidence={"target_path": str(target)},
        ))
        metadata["audit_unavailable"] = True
        return _make_report(target, metadata, findings, started)

    if suffix not in _SUPPORTED_FORMATS:
        limitations.append("unsupported_export_format")
        findings.append(_finding(
            "export.unsupported_format",
            Severity.INFO,
            f"export format '{suffix or '<none>'}' is not audited by the Phase 1 MVP",
            evidence={"format": fmt, "supported_formats": sorted(_SUPPORTED_FORMATS)},
        ))
        metadata["audit_unavailable"] = False
        return _make_report(target, metadata, findings, started)

    if suffix in _RASTER_FORMATS:
        _audit_raster_metadata(target, metadata, limitations, findings)
    elif suffix in _PDF_FORMATS:
        _audit_pdf_metadata(target, metadata, limitations, findings, require_backend)

    metadata["audit_unavailable"] = _has_backend_limitation(limitations)
    return _make_report(target, metadata, findings, started)


def _audit_raster_metadata(
    target: Path,
    metadata: dict[str, Any],
    limitations: list[str],
    findings: list[Finding],
) -> None:
    try:
        from matplotlib import image as mpimg

        image = mpimg.imread(target)
    except Exception as exc:
        limitations.append("raster_metadata_read_failed")
        findings.append(_finding(
            "export.metadata_read_failed",
            Severity.INFO,
            f"could not read raster export metadata: {type(exc).__name__}: {exc}",
            evidence={"target_path": str(target), "backend": "matplotlib.image"},
        ))
        return

    shape = getattr(image, "shape", ())
    if len(shape) >= 2:
        metadata["height_px"] = int(shape[0])
        metadata["width_px"] = int(shape[1])
    if len(shape) >= 3:
        metadata["channels"] = int(shape[2])

    if metadata.get("width_px", 0) <= 0 or metadata.get("height_px", 0) <= 0:
        findings.append(_finding(
            "export.invalid_dimensions",
            Severity.HIGH,
            "export artifact reports non-positive pixel dimensions",
            evidence={
                "width_px": metadata.get("width_px"),
                "height_px": metadata.get("height_px"),
            },
        ))


def _audit_pdf_metadata(
    target: Path,
    metadata: dict[str, Any],
    limitations: list[str],
    findings: list[Finding],
    require_backend: bool,
) -> None:
    fitz = _load_pymupdf()
    if fitz is None:
        limitations.append("pdf_backend_unavailable:pymupdf")
        if require_backend:
            findings.append(_finding(
                "export.backend_unavailable",
                Severity.HIGH,
                "PDF export audit requires PyMuPDF, but PyMuPDF is unavailable",
                evidence={"backend": "PyMuPDF", "target_path": str(target)},
            ))
        return

    try:
        with fitz.open(str(target)) as doc:
            page_count = int(doc.page_count)
            metadata["page_count"] = page_count
            if page_count:
                rect = doc[0].rect
                metadata["page0_width_pt"] = float(rect.width)
                metadata["page0_height_pt"] = float(rect.height)
    except Exception as exc:
        limitations.append("pdf_metadata_read_failed")
        findings.append(_finding(
            "export.metadata_read_failed",
            Severity.INFO,
            f"could not read PDF export metadata: {type(exc).__name__}: {exc}",
            evidence={"target_path": str(target), "backend": "PyMuPDF"},
        ))
        return

    if metadata.get("page_count", 0) <= 0:
        findings.append(_finding(
            "export.empty_pdf",
            Severity.HIGH,
            "PDF export contains no pages",
            evidence={"page_count": metadata.get("page_count")},
        ))


def _finding(
    check_id: str,
    severity: Severity,
    message: str,
    *,
    evidence: Optional[dict[str, Any]] = None,
) -> Finding:
    return Finding(
        check_id=check_id,
        severity=severity,
        category=Category.POLICY,
        stage=Stage.TIER2,
        message=message,
        evidence=evidence,
    )


def _make_report(
    target: Path,
    metadata: dict[str, Any],
    findings: list[Finding],
    started: float,
) -> Report:
    return Report(
        findings=findings,
        figure_label=target.name or str(target),
        timings={"audit_export": time.perf_counter() - started},
        metadata=metadata,
    )


def _load_pymupdf():
    """Return the optional PyMuPDF module when available."""
    for module_name in ("fitz", "pymupdf"):
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    return None


def _has_backend_limitation(limitations: list[str]) -> bool:
    return any("backend_unavailable" in limitation for limitation in limitations)


def report_to_dict(report: Report) -> dict[str, Any]:
    """Return a report dictionary preserving Phase 1 metadata."""
    return report.to_dict()


__all__ = ["audit_export", "report_to_dict"]
