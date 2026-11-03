"""Normalize the training assessment and project it onto planner inputs.

The stored document is the source of truth when present. Older rows that only
have the flat columns are still readable.
"""

from __future__ import annotations

from typing import Any

LB_TO_KG = 0.45359237

GOAL_TO_LEGACY = {
    "build_muscle": "build_muscle",
    "increase_strength": "build_strength",
    "lose_body_fat": "improve_conditioning",
    "improve_endurance": "improve_conditioning",
    "athletic_performance": "build_strength",
    "maintain_fitness": "learn_technique",
    "build_strength": "build_strength",
    "improve_conditioning": "improve_conditioning",
    "learn_technique": "learn_technique",
}

LEGACY_TO_GOAL = {
    "build_strength": "increase_strength",
    "build_muscle": "build_muscle",
    "improve_conditioning": "improve_endurance",
    "learn_technique": "maintain_fitness",
}

EQUIPMENT_ALIASES = {
    "barbell": "barbell",
    "dumbbells": "dumbbells",
    "dumbbell": "dumbbells",
    "kettlebells": "kettlebell",
    "kettlebell": "kettlebell",
    "weight_plates": "barbell",
    "leg_press": "machines",
    "cable_machine": "machines",
    "smith_machine": "machines",
    "leg_extension": "machines",
    "leg_curl": "machines",
    "chest_press": "machines",
    "lat_pulldown": "machines",
    "machines": "machines",
    "squat_rack": "rack",
    "rack": "rack",
    "adjustable_bench": "bench",
    "resistance_bands": "bands",
    "pull_up_bar": "pullup",
    "bodyweight": "bodyweight",
    "bodyweight_only": "bodyweight",
}

PRESETS = {
    "full_gym": [
        "barbell",
        "dumbbells",
        "kettlebells",
        "weight_plates",
        "squat_rack",
        "leg_press",
        "cable_machine",
        "leg_extension",
        "leg_curl",
        "lat_pulldown",
        "chest_press",
        "adjustable_bench",
        "pull_up_bar",
        "bodyweight",
    ],
    "basic_home": ["dumbbells", "adjustable_bench", "resistance_bands", "bodyweight"],
    "minimal": ["dumbbells", "bodyweight"],
    "bodyweight": ["bodyweight"],
}


def to_kg(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    if unit == "lb":
        return round(float(value) * LB_TO_KG, 2)
    return round(float(value), 2)


def legacy_equipment(available: list[str]) -> list[str]:
    mapped = []
    for item in available:
        alias = EQUIPMENT_ALIASES.get(item, item)
        if alias not in mapped:
            mapped.append(alias)
    if not mapped:
        mapped = ["bodyweight"]
    if "bodyweight" not in mapped:
        mapped.append("bodyweight")
    return mapped


def assessment_from_legacy(profile: dict) -> dict:
    goal = LEGACY_TO_GOAL.get(profile.get("goal") or "", profile.get("goal") or "maintain_fitness")
    return {
        "identity": {
            "display_name": profile.get("display_name"),
            "preferred_weight_unit": "kg",
            "training_environment": None,
            "age_range": None,
            "height_cm": profile.get("optional_height_cm"),
            "weight_kg": profile.get("optional_weight_kg"),
        },
        "goals": {
            "primary": goal,
            "secondary": None,
            "priority_muscles": [],
            "ambitions": [],
            "personal_objective": None,
            "planning_horizon_weeks": None,
        },
        "experience": {
            "level": profile.get("experience") or "beginner",
            "training_history": None,
            "consistency": None,
            "current_split": None,
            "exercise_familiarity": {},
            "working_sets": _legacy_squat(profile),
        },
        "schedule": {
            "days_per_week": profile.get("days_per_week") or 3,
            "preferred_days": [],
            "session_minutes": profile.get("session_duration_minutes") or 45,
            "duration_band": None,
        },
        "preferences": {
            "training_style": None,
            "preferred_split": None,
            "intensity": None,
            "other_activities": [],
            "enjoyed_exercises": [],
            "disliked_exercises": [],
            "sport": None,
        },
        "equipment": {
            "preset": None,
            "available": list(profile.get("equipment") or ["bodyweight"]),
        },
        "considerations": {
            "avoided_exercises": [],
            "movement_restrictions": list(profile.get("limitations") or []),
            "limitation_note": None,
        },
    }


def _legacy_squat(profile: dict) -> dict:
    load = profile.get("current_squat_load_kg")
    if load is None:
        return {}
    return {"barbell_squat": {"weight_kg": load, "reps": 8, "sets": None}}


def project_assessment(assessment: dict) -> dict:
    """Flat columns the rest of the app already reads."""
    identity = assessment.get("identity") or {}
    goals = assessment.get("goals") or {}
    experience = assessment.get("experience") or {}
    schedule = assessment.get("schedule") or {}
    equipment = assessment.get("equipment") or {}
    considerations = assessment.get("considerations") or {}
    unit = identity.get("preferred_weight_unit") or "kg"
    working = (experience.get("working_sets") or {}).get("barbell_squat") or {}
    raw_load = working.get("weight_kg")
    if raw_load is None and working.get("weight") is not None:
        raw_load = to_kg(working.get("weight"), unit)
    available = list(equipment.get("available") or [])
    if equipment.get("preset") in PRESETS and not available:
        available = list(PRESETS[equipment["preset"]])
    limitations = list(considerations.get("movement_restrictions") or [])
    note = considerations.get("limitation_note")
    if note:
        limitations.append(str(note))
    return {
        "display_name": identity.get("display_name"),
        "goal": GOAL_TO_LEGACY.get(goals.get("primary") or "", "build_strength"),
        "experience": experience.get("level") or "beginner",
        "days_per_week": int(schedule.get("days_per_week") or 3),
        "session_duration_minutes": int(schedule.get("session_minutes") or 45),
        "equipment": legacy_equipment(available),
        "current_squat_load_kg": raw_load,
        "optional_height_cm": identity.get("height_cm"),
        "optional_weight_kg": identity.get("weight_kg") if identity.get("weight_kg") is not None else to_kg(identity.get("weight"), unit),
        "limitations": [item for item in limitations if item],
        "age_range": identity.get("age_range") or None,
    }


def planner_view(profile: dict) -> dict:
    """One dict the local planner and Muse context builder both read."""
    assessment = profile.get("assessment") or assessment_from_legacy(profile)
    flat = project_assessment(assessment)
    # Explicit flat fields win when an older client did not send an assessment.
    if not profile.get("assessment"):
        for key in (
            "goal",
            "experience",
            "days_per_week",
            "session_duration_minutes",
            "equipment",
            "current_squat_load_kg",
            "limitations",
            "age_range",
        ):
            if profile.get(key) is not None:
                flat[key] = profile[key]
    goals = assessment.get("goals") or {}
    experience = assessment.get("experience") or {}
    preferences = assessment.get("preferences") or {}
    considerations = assessment.get("considerations") or {}
    identity = assessment.get("identity") or {}
    muscles = [item for item in (goals.get("priority_muscles") or []) if item]
    training_focus = "lower_body" if goals.get("training_focus") == "lower_body" else "balanced"
    if training_focus == "lower_body":
        muscles = ["quadriceps", "hamstrings", "glutes", "calves"]
    priority_specified = bool(muscles)
    if "full_body" in muscles:
        muscles = ["full_body"]
    if not muscles:
        muscles = ["full_body"]
    return {
        **flat,
        "assessment": assessment,
        "primary_goal": goals.get("primary") or LEGACY_TO_GOAL.get(flat["goal"], flat["goal"]),
        "training_focus": training_focus,
        "secondary_goal": goals.get("secondary"),
        "priority_muscles": muscles,
        "priority_specified": priority_specified,
        "enjoyed_exercises": list(preferences.get("enjoyed_exercises") or []),
        "preferred_split": preferences.get("preferred_split") or "ghostrep_decides",
        "training_style": preferences.get("training_style"),
        "other_activities": list(preferences.get("other_activities") or []),
        "avoided_exercises": list(considerations.get("avoided_exercises") or []),
        "age_range": identity.get("age_range") or flat.get("age_range"),
        "under_18": (identity.get("age_range") or flat.get("age_range")) == "under_18",
        "familiarity": dict(experience.get("exercise_familiarity") or {}),
        "working_sets": dict(experience.get("working_sets") or {}),
        "preferred_days": list((assessment.get("schedule") or {}).get("preferred_days") or []),
        "sport": preferences.get("sport"),
        "intensity": preferences.get("intensity"),
        "planning_horizon_weeks": goals.get("planning_horizon_weeks"),
    }


def compact_planning_context(profile: dict) -> dict[str, Any]:
    """Fields a future Muse call may see. No height, weight, or free-text medical history."""
    view = planner_view(profile)
    assessment = view["assessment"]
    considerations = assessment.get("considerations") or {}
    return {
        "purpose": "workout_plan",
        "constraints": {
            "equipment": view["equipment"],
            "avoided_exercises": view["avoided_exercises"],
            "movement_restrictions": considerations.get("movement_restrictions") or [],
            "days_per_week": view["days_per_week"],
            "session_minutes": view["session_duration_minutes"],
        },
        "age_range": view.get("age_range") or None,
        "preferences": {
            "primary_goal": view["primary_goal"],
            "training_focus": view["training_focus"],
            "secondary_goal": view["secondary_goal"],
            "priority_muscles": view["priority_muscles"] if view.get("priority_specified") else [],
            "experience": view["experience"],
            "preferred_split": view["preferred_split"],
            "training_style": view["training_style"],
            "preferred_days": view["preferred_days"],
            "enjoyed_exercises": view["enjoyed_exercises"],
            "other_activities": [
                {"activity": item.get("activity"), "sessions_per_week": item.get("sessions_per_week")}
                for item in view["other_activities"]
                if isinstance(item, dict)
            ],
            "sport": view["sport"],
        },
        "training_history": {
            "familiarity": view["familiarity"],
            "working_sets_kg": {
                key: {"weight_kg": val.get("weight_kg"), "reps": val.get("reps")}
                for key, val in view["working_sets"].items()
                if isinstance(val, dict)
            },
        },
        "missing": _missing(view),
    }


def _missing(view: dict) -> list[str]:
    missing = []
    if not view.get("secondary_goal"):
        missing.append("secondary_goal")
    if not view.get("priority_specified"):
        missing.append("specific_muscle_priority")
    if not view.get("preferred_days"):
        missing.append("preferred_days")
    if view.get("current_squat_load_kg") is None and "barbell" in view["equipment"]:
        missing.append("squat_working_weight")
    return missing
