"""Trusted recording provenance shared by reads, training totals and write guards.

DEMO_FIXTURE is the persisted legacy marker. A fixture *silhouette* on an
otherwise real recording is not a sample; presentation labels are not evidence.
"""

from app.models.entities import RecordedSet

SAMPLE_READ_ONLY = "Illustrative samples are read-only. They do not change workout targets or count as performed training."


def is_sample_set(rec: RecordedSet) -> bool:
    return rec.entry_source == "demo" or rec.original_filename == "DEMO_FIXTURE"


def is_performed_set(rec: RecordedSet) -> bool:
    if is_sample_set(rec) or (rec.completed_reps or 0) <= 0:
        return False
    if rec.entry_source == "manual":
        return rec.processing_status in {"LOGGED", "COMPLETED", "SAVED"}
    return rec.entry_source == "video" and rec.processing_status in {"COMPLETED", "SAVED"}
