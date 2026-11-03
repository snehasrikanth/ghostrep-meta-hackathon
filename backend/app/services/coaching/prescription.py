"""Resolve next-set targets from the workout prescription, not from completed reps.

A recorded set stores the snapshot used at upload time (`target_reps`, `load_kg`).
The open workout exercise stores the live prescription (`target_reps`, `rest_seconds`,
`suggested_load_kg`). KEEP_PLAN must preserve the workout prescription. Completed
repetitions are evidence, not a new target.
"""

from __future__ import annotations

from app.models.entities import RecordedSet, WorkoutExercise, WorkoutSession

KEEP_TARGET_ACTIONS = {
    "KEEP_PLAN",
    "NO_RECOMMENDATION",
    "REQUEST_NEW_RECORDING",
    "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
}


def matching_exercise(rec: RecordedSet, session: WorkoutSession | None = None) -> WorkoutExercise | None:
    session = session or getattr(rec, "session", None)
    plan = getattr(session, "plan", None) if session is not None else None
    if plan is None:
        return None
    return next((ex for ex in plan.exercises if ex.exercise_id == rec.exercise_id), None)


def prescription_for_set(rec: RecordedSet, session: WorkoutSession | None = None) -> dict:
    exercise = matching_exercise(rec, session)
    planned_set_reps = rec.target_reps
    planned_set_load_kg = rec.load_kg
    if exercise is not None:
        workout_reps = exercise.target_reps
        workout_rest = exercise.rest_seconds
        workout_load = exercise.suggested_load_kg
    else:
        workout_reps = planned_set_reps
        workout_rest = None
        workout_load = planned_set_load_kg
    return {
        "planned_set_reps": planned_set_reps,
        "planned_set_load_kg": planned_set_load_kg,
        "completed_reps": rec.completed_reps,
        "workout_reps": workout_reps,
        "workout_rest_seconds": workout_rest,
        "workout_load_kg": workout_load,
        "current_reps": workout_reps,
        "current_rest": workout_rest,
        "current_load": workout_load,
    }


def coach_input_targets(rec: RecordedSet, session: WorkoutSession | None = None) -> dict:
    rx = prescription_for_set(rec, session)
    return {
        "current_reps": rx["current_reps"],
        "current_rest": rx["current_rest"],
        "current_load": rx["current_load"],
        "planned_set_reps": rx["planned_set_reps"],
        "planned_set_load_kg": rx["planned_set_load_kg"],
        "completed_reps": rx["completed_reps"],
        "workout_reps": rx["workout_reps"],
        "workout_rest_seconds": rx["workout_rest_seconds"],
        "workout_load_kg": rx["workout_load_kg"],
    }


def attach_prescription(payload: dict, rx: dict) -> dict:
    """Label planned / completed / workout targets. KEEP_PLAN suggested values match the workout."""
    payload["planned_set_reps"] = rx["planned_set_reps"]
    payload["planned_set_load_kg"] = rx["planned_set_load_kg"]
    payload["completed_reps"] = rx["completed_reps"]
    payload["workout_reps"] = rx["workout_reps"]
    payload["workout_rest_seconds"] = rx["workout_rest_seconds"]
    payload["workout_load_kg"] = rx["workout_load_kg"]
    payload["current_reps"] = rx["current_reps"]
    payload["current_rest_seconds"] = rx["current_rest"]
    payload["current_load_kg"] = rx["current_load"]
    if payload.get("suggested_action") in KEEP_TARGET_ACTIONS:
        payload["suggested_reps"] = rx["current_reps"]
        payload["suggested_rest_seconds"] = rx["current_rest"]
        payload["suggested_load_kg"] = rx["current_load"]
    return payload
