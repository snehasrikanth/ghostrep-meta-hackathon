"""Attach saved or fixture segmentation to an analysis row. Never calls Meta."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import AnalysisResult, RecordedSet
from app.services.meta.silhouettes import (
    GeometryMissing,
    assign_athlete,
    attach_silhouettes,
    fixture_from_overlay,
    require_drawable_geometry,
    segmentation_document,
    silhouette_source,
)


def persist_to_analysis(
    db: Session,
    rec: RecordedSet,
    segmentation: dict,
    *,
    media: dict | None = None,
) -> dict:
    analysis = rec.analysis
    if analysis is None:
        raise RuntimeError("This recording has no pose analysis to attach silhouettes to.")
    overlay = json.loads(analysis.overlay_json or "{}")
    previous_source = overlay.get("silhouette_source")
    assign_athlete(segmentation, overlay.get("frames") or [])
    incoming = silhouette_source(segmentation)
    if incoming == "sam":
        try:
            require_drawable_geometry(segmentation)
        except GeometryMissing:
            if previous_source == "fixture":
                return overlay
            raise
    attached = attach_silhouettes(overlay, segmentation, analysis.reference_rep)
    source = attached.get("silhouette_source") or incoming
    if incoming == "sam" and source != "sam":
        if previous_source == "fixture":
            overlay["silhouette_source"] = "fixture"
            overlay["silhouette_label"] = "Offline fixture"
            return overlay
        raise GeometryMissing("Live SAM masks did not attach to pose timestamps.")
    document = segmentation_document(
        {**segmentation, "source": source, "available": source in {"sam", "fixture"}},
        set_id=rec.id,
        analysis_id=analysis.id,
        session_id=rec.session_id,
        media=media,
    )
    analysis.overlay_json = json.dumps(attached)
    analysis.segmentation_json = json.dumps(document)
    analysis.sam_available = source in {"sam", "fixture"}
    analysis.sam_status = "live" if source == "sam" else source if source != "unavailable" else str(
        segmentation.get("status") or "unavailable"
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return attached


def reapply_saved(analysis: AnalysisResult, overlay: dict) -> tuple[dict, dict | None]:
    """Reuse stored tracks when a new Meta call is not allowed."""
    if not analysis.segmentation_json:
        return overlay, None
    saved = json.loads(analysis.segmentation_json)
    if not saved.get("tracks"):
        return overlay, None
    assign_athlete(saved, overlay.get("frames") or [])
    if silhouette_source(saved) == "sam":
        try:
            require_drawable_geometry(saved)
        except GeometryMissing:
            return overlay, saved
    attached = attach_silhouettes(overlay, saved, analysis.reference_rep)
    return attached, saved


def install_overlay_fixture(db: Session, rec: RecordedSet, *, fps: float | None = None) -> dict:
    analysis = rec.analysis
    if analysis is None:
        raise RuntimeError("This recording has no pose analysis.")
    overlay = json.loads(analysis.overlay_json or "{}")
    rate = fps or (len(overlay.get("frames") or []) / max(float(rec.duration_seconds or 1), 0.001))
    segmentation = fixture_from_overlay(overlay, fps=rate)
    return persist_to_analysis(db, rec, segmentation)


def load_tracks_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("tracks"):
        raise RuntimeError(f"{path} has no decoded tracks.")
    return data
