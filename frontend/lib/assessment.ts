import { z } from "zod";

import type { AssessmentDocument, Goal, Profile } from "./types";

export const ageRangeSchema = z.enum([
  "18_29",
  "30_39",
  "40_49",
  "50_59",
  "60_64",
  "65_74",
  "75_plus",
  "prefer_not_to_say",
  "under_18",
  "18_24",
  "25_34",
  "35_44",
  "45_54",
  "55_plus",
]).nullable();

export const DRAFT_KEY = "ghostrep.assessment.v1";

export const PRIMARY_GOALS = [
  { id: "build_muscle", label: "Build muscle", hint: "More work for the muscles you want to grow." },
  { id: "increase_strength", label: "Increase strength", hint: "Heavier, lower-rep practice on the main lifts." },
  { id: "lose_body_fat", label: "Lose body fat", hint: "Keep muscle while sessions stay short enough to recover." },
  { id: "improve_endurance", label: "Improve endurance", hint: "Shorter rests and more continuous work." },
  { id: "athletic_performance", label: "Improve athletic performance", hint: "Leave room for the sport you already play." },
  { id: "maintain_fitness", label: "Maintain fitness and general health", hint: "A sustainable plan, not a peak block." },
] as const;

export const MUSCLES = [
  "chest",
  "back",
  "shoulders",
  "arms",
  "core",
  "quadriceps",
  "hamstrings",
  "glutes",
  "calves",
] as const;

export const AMBITIONS = [
  { id: "squat_strength", label: "Improve squat strength" },
  { id: "deadlift_strength", label: "Improve deadlift strength" },
  { id: "upper_strength", label: "Improve upper-body strength" },
  { id: "lower_muscle", label: "Increase lower-body muscle" },
  { id: "consistency", label: "Improve exercise consistency" },
  { id: "conditioning", label: "Build general conditioning" },
  { id: "sport", label: "Improve performance for a sport" },
] as const;

export const ENVIRONMENTS = [
  { id: "commercial_gym", label: "Commercial gym" },
  { id: "home_gym", label: "Home gym" },
  { id: "minimal_home", label: "Home with minimal equipment" },
  { id: "combination", label: "Combination of home and gym" },
  { id: "other", label: "Other" },
] as const;

export const AGE_RANGES = [
  { id: "18_29", label: "18–29" },
  { id: "30_39", label: "30–39" },
  { id: "40_49", label: "40–49" },
  { id: "50_59", label: "50–59" },
  { id: "60_64", label: "60–64" },
  { id: "65_74", label: "65–74" },
  { id: "75_plus", label: "75+" },
  { id: "prefer_not_to_say", label: "Prefer not to say" },
] as const;

export const EXPERIENCE_LEVELS = [
  { id: "beginner", label: "Beginner", hint: "New to structured lifting, or returning after a long break." },
  { id: "intermediate", label: "Intermediate", hint: "You train regularly and know the main movements." },
  { id: "advanced", label: "Advanced", hint: "You have trained consistently for years." },
] as const;

export const HISTORIES = [
  { id: "just_starting", label: "Just starting" },
  { id: "under_6_months", label: "Less than 6 months" },
  { id: "6_to_12_months", label: "6–12 months" },
  { id: "1_to_3", label: "1–3 years" },
  { id: "3_to_5", label: "3–5 years" },
  { id: "over_5", label: "More than 5 years" },
] as const;

export const CONSISTENCY = [
  { id: "new", label: "New to structured exercise" },
  { id: "occasional", label: "Occasionally active" },
  { id: "1_2", label: "Training 1–2 days per week" },
  { id: "3_4", label: "Training 3–4 days per week" },
  { id: "5_plus", label: "Training 5+ days per week" },
  { id: "returning", label: "Returning after a break" },
] as const;

export const SPLITS = [
  { id: "full_body", label: "Full body" },
  { id: "upper_lower", label: "Upper / lower" },
  { id: "push_pull_legs", label: "Push / pull / legs" },
  { id: "body_part", label: "Body-part split" },
  { id: "sports", label: "Sports-focused" },
  { id: "none", label: "No structured routine" },
  { id: "other", label: "Other" },
] as const;

export const FAMILIAR_LIFTS = [
  { id: "barbell_squat", label: "Squat" },
  { id: "deadlift", label: "Deadlift" },
  { id: "bench_press", label: "Bench press" },
  { id: "overhead_press", label: "Overhead press" },
  { id: "row", label: "Rows" },
  { id: "lunge", label: "Lunges" },
] as const;

export const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;

export const DURATION_BANDS = [
  { id: "20_30", label: "20–30 minutes", minutes: 25 },
  { id: "30_45", label: "30–45 minutes", minutes: 40 },
  { id: "45_60", label: "45–60 minutes", minutes: 50 },
  { id: "60_75", label: "60–75 minutes", minutes: 70 },
  { id: "75_90", label: "75–90 minutes", minutes: 80 },
  { id: "custom", label: "Custom", minutes: 0 },
] as const;

export const STYLES = [
  { id: "strength", label: "Strength-focused" },
  { id: "hypertrophy", label: "Muscle-building focused" },
  { id: "general", label: "General fitness" },
  { id: "mixed", label: "Mixed strength and cardio" },
  { id: "sport", label: "Sport-specific conditioning" },
  { id: "none", label: "No preference" },
] as const;

export const PREFERRED_SPLITS = [
  { id: "full_body", label: "Full body", hint: "Upper and lower work in every session" },
  { id: "upper_lower", label: "Upper / lower", hint: "Alternate focus; the week stays balanced" },
  { id: "push_pull_legs", label: "Push / pull / legs", hint: "One movement pattern each session" },
  { id: "body_part", label: "Body-part split", hint: "Isolate muscle groups by day" },
  { id: "ghostrep_decides", label: "Let GhostRep decide", hint: "Pick a split that fits your days" },
] as const;

export const INTENSITIES = [
  { id: "moderate", label: "Prefer moderate intensity" },
  { id: "challenging", label: "Comfortable with challenging workouts" },
  { id: "gradual", label: "Prefer gradual progression" },
  { id: "ghostrep_decides", label: "Let GhostRep decide" },
] as const;

export const ACTIVITIES = ["walking", "running", "cycling", "swimming", "badminton", "tennis", "football", "basketball", "other"] as const;

export const EQUIPMENT_GROUPS = [
  { label: "Free weights", items: ["barbell", "dumbbells", "kettlebells", "weight_plates"] },
  { label: "Machines", items: ["leg_press", "cable_machine", "smith_machine", "leg_extension", "leg_curl", "chest_press", "lat_pulldown"] },
  { label: "Gym accessories", items: ["squat_rack", "adjustable_bench", "resistance_bands", "pull_up_bar"] },
  { label: "Cardio", items: ["treadmill", "exercise_bike", "rowing_machine", "elliptical"] },
  { label: "Other", items: ["bodyweight"] },
] as const;

export const PRESETS: Record<string, string[]> = {
  full_gym: [
    "barbell", "dumbbells", "kettlebells", "weight_plates", "squat_rack", "leg_press", "cable_machine",
    "leg_extension", "leg_curl", "lat_pulldown", "chest_press", "adjustable_bench", "pull_up_bar", "bodyweight",
  ],
  basic_home: ["dumbbells", "adjustable_bench", "resistance_bands", "bodyweight"],
  minimal: ["dumbbells", "bodyweight"],
  bodyweight: ["bodyweight"],
};

export const RESTRICTIONS = [
  { id: "avoid_overhead", label: "Avoid heavy overhead movements" },
  { id: "avoid_impact", label: "Avoid high-impact exercises" },
  { id: "limited_squat_depth", label: "Limited squat depth" },
  { id: "avoid_equipment", label: "Avoid certain equipment" },
] as const;

export const CATALOG_CHOICES = [
  { id: "barbell_squat", label: "Barbell squat" },
  { id: "goblet_squat", label: "Goblet squat" },
  { id: "bodyweight_squat", label: "Bodyweight squat" },
  { id: "romanian_deadlift", label: "Romanian deadlift" },
  { id: "walking_lunge", label: "Walking lunge" },
  { id: "leg_press", label: "Leg press" },
  { id: "leg_curl", label: "Leg curl" },
  { id: "bench_press", label: "Bench press" },
  { id: "push_up", label: "Push-up" },
  { id: "dumbbell_row", label: "Dumbbell row" },
  { id: "glute_bridge", label: "Glute bridge" },
  { id: "plank", label: "Plank" },
  { id: "single_leg_balance", label: "Single-leg balance" },
  { id: "sit_to_stand", label: "Sit to stand" },
] as const;

const LEGACY_GOAL: Record<string, Goal> = {
  build_muscle: "build_muscle",
  increase_strength: "build_strength",
  lose_body_fat: "improve_conditioning",
  improve_endurance: "improve_conditioning",
  athletic_performance: "build_strength",
  maintain_fitness: "learn_technique",
};

const LEGACY_EQUIPMENT: Record<string, string> = {
  barbell: "barbell",
  dumbbells: "dumbbells",
  kettlebells: "kettlebell",
  weight_plates: "barbell",
  leg_press: "machines",
  cable_machine: "machines",
  smith_machine: "machines",
  leg_extension: "machines",
  leg_curl: "machines",
  chest_press: "machines",
  lat_pulldown: "machines",
  squat_rack: "rack",
  bodyweight: "bodyweight",
};

export type AssessmentDraft = {
  ui_step?: number;
  identity: {
    display_name: string;
    preferred_weight_unit: "kg" | "lb";
    training_environment: string;
    age_range: string;
    adult_confirmed: boolean;
    height_cm: string;
    weight: string;
  };
  goals: {
    primary: string;
    training_focus?: "balanced" | "lower_body";
    secondary: string;
    priority_muscles: string[];
    ambitions: string[];
    personal_objective: string;
    planning_horizon_weeks: string;
  };
  experience: {
    level: string;
    training_history: string;
    consistency: string;
    current_split: string;
    exercise_familiarity: Record<string, string>;
    squat_weight: string;
    squat_reps: string;
    squat_sets: string;
  };
  schedule: {
    days_per_week: number;
    preferred_days: string[];
    duration_band: string;
    custom_minutes: string;
  };
  preferences: {
    training_style: string;
    preferred_split: string;
    intensity: string;
    other_activities: { activity: string; sessions_per_week: number }[];
    enjoyed_exercises: string[];
    disliked_exercises: string[];
    sport: string;
  };
  equipment: { preset: string; available: string[] };
  considerations: {
    avoided_exercises: string[];
    movement_restrictions: string[];
    limitation_note: string;
  };
};

export function emptyDraft(): AssessmentDraft {
  return {
    identity: {
      display_name: "",
      preferred_weight_unit: "kg",
      training_environment: "",
      age_range: "",
      adult_confirmed: false,
      height_cm: "",
      weight: "",
    },
    goals: {
      primary: "",
      training_focus: "balanced",
      secondary: "",
      priority_muscles: [],
      ambitions: [],
      personal_objective: "",
      planning_horizon_weeks: "",
    },
    experience: {
      level: "",
      training_history: "",
      consistency: "",
      current_split: "",
      exercise_familiarity: {},
      squat_weight: "",
      squat_reps: "",
      squat_sets: "",
    },
    schedule: {
      days_per_week: 0,
      preferred_days: [],
      duration_band: "",
      custom_minutes: "",
    },
    preferences: {
      training_style: "",
      preferred_split: "",
      intensity: "",
      other_activities: [],
      enjoyed_exercises: [],
      disliked_exercises: [],
      sport: "",
    },
    equipment: { preset: "", available: [] },
    considerations: { avoided_exercises: [], movement_restrictions: [], limitation_note: "" },
  };
}

export function poundsToKg(value: number): number {
  return Math.round(value * 0.45359237 * 100) / 100;
}

export function kgToPounds(value: number): number {
  return Math.round((value / 0.45359237) * 10) / 10;
}

export function hasBarbell(draft: AssessmentDraft): boolean {
  return draft.equipment.available.includes("barbell");
}

export function wantsStrengthDetail(draft: AssessmentDraft): boolean {
  return (
    draft.goals.primary === "increase_strength" ||
    draft.goals.primary === "build_muscle" ||
    draft.goals.secondary === "increase_strength"
  );
}

export function showSquatLoad(draft: AssessmentDraft): boolean {
  if (!hasBarbell(draft) || !wantsStrengthDetail(draft)) return false;
  if (draft.experience.level === "beginner") return false;
  return draft.experience.exercise_familiarity.barbell_squat !== "new";
}

export function ageLabel(range: string): string {
  return AGE_RANGES.find((item) => item.id === range)?.label || range.replaceAll("_", " ");
}

export function showSport(draft: AssessmentDraft): boolean {
  return (
    draft.goals.primary === "athletic_performance" ||
    draft.goals.secondary === "athletic_performance" ||
    draft.preferences.training_style === "sport" ||
    draft.goals.ambitions.includes("sport")
  );
}

export function showMusclePriority(draft: AssessmentDraft): boolean {
  return ["build_muscle", "lose_body_fat", "increase_strength", "athletic_performance"].includes(draft.goals.primary);
}

export function showTechnicalLifts(draft: AssessmentDraft): boolean {
  return draft.experience.level !== "beginner";
}

export function toggleMuscle(current: string[], id: string): string[] {
  if (id === "full_body") return current.includes("full_body") ? [] : ["full_body"];
  const without = current.filter((item) => item !== "full_body" && item !== id);
  if (current.includes(id)) return without;
  if (without.length >= 3) return without;
  return [...without, id];
}

export function sessionMinutes(draft: AssessmentDraft): number {
  if (draft.schedule.duration_band === "custom") {
    const custom = Number(draft.schedule.custom_minutes);
    if (Number.isFinite(custom)) return Math.min(120, Math.max(20, custom));
    return 45;
  }
  return DURATION_BANDS.find((band) => band.id === draft.schedule.duration_band)?.minutes || 45;
}

export function validateStep(step: number, draft: AssessmentDraft): string | null {
  if (step === 0) {
    if (!draft.identity.display_name.trim()) return "Add the name you want GhostRep to use.";
    if (!draft.identity.training_environment) return "Choose where you usually train.";
    if (!draft.identity.adult_confirmed) return "GhostRep is for adults. Confirm that you are 18 or older.";
  }
  if (step === 1 && !draft.goals.primary) return "Choose a primary goal.";
  if (step === 2 && !draft.experience.level) return "Choose your training experience.";
  if (step === 3) {
    if (draft.schedule.days_per_week < 1 || draft.schedule.days_per_week > 7) return "Choose how many days you want to train.";
    if (!draft.schedule.duration_band) return "Choose how long a session should last.";
  }
  if (step === 4 && draft.equipment.available.length === 0) return "Choose the equipment you can use.";
  return null;
}

function storedAge(draft: AssessmentDraft): string | null {
  const raw = draft.identity.adult_confirmed && draft.identity.age_range === "under_18" ? null : draft.identity.age_range || null;
  const parsed = ageRangeSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

function num(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function toProfilePayload(draft: AssessmentDraft) {
  const unit = draft.identity.preferred_weight_unit;
  const weight = num(draft.identity.weight);
  const squat = showSquatLoad(draft) ? num(draft.experience.squat_weight) : null;
  const weightKg = weight == null ? null : unit === "lb" ? poundsToKg(weight) : weight;
  const squatKg = squat == null ? null : unit === "lb" ? poundsToKg(squat) : squat;
  const equipment = legacyEquipment(draft.equipment.available);
  const limitations = [
    ...draft.considerations.movement_restrictions,
    draft.considerations.limitation_note.trim(),
  ].filter(Boolean);
  const workingSets: NonNullable<AssessmentDocument["experience"]["working_sets"]> = squatKg == null
    ? {}
    : {
        barbell_squat: {
          weight_kg: squatKg,
          reps: num(draft.experience.squat_reps),
          sets: num(draft.experience.squat_sets),
        },
      };
  const assessment: AssessmentDocument = {
    identity: {
      display_name: draft.identity.display_name.trim(),
      preferred_weight_unit: unit,
      training_environment: draft.identity.training_environment,
      age_range: storedAge(draft),
      adult_confirmed: draft.identity.adult_confirmed,
      height_cm: num(draft.identity.height_cm),
      weight_kg: weightKg,
    },
    goals: {
      primary: draft.goals.primary,
      training_focus: draft.goals.training_focus || "balanced",
      secondary: draft.goals.secondary || null,
      priority_muscles: draft.goals.priority_muscles,
      ambitions: draft.goals.ambitions,
      personal_objective: draft.goals.personal_objective.trim() || null,
      planning_horizon_weeks: ["4", "8", "12"].includes(draft.goals.planning_horizon_weeks)
        ? Number(draft.goals.planning_horizon_weeks)
        : null,
    },
    experience: {
      level: draft.experience.level,
      training_history: draft.experience.training_history || null,
      consistency: draft.experience.consistency || null,
      current_split: draft.experience.current_split || null,
      exercise_familiarity: draft.experience.exercise_familiarity,
      working_sets: workingSets,
    },
    schedule: {
      days_per_week: draft.schedule.days_per_week,
      preferred_days: draft.schedule.preferred_days,
      session_minutes: sessionMinutes(draft),
      duration_band: draft.schedule.duration_band,
    },
    preferences: {
      training_style: draft.preferences.training_style || null,
      preferred_split: draft.experience.level === "beginner" ? "ghostrep_decides" : draft.preferences.preferred_split || "ghostrep_decides",
      intensity: draft.preferences.intensity || null,
      other_activities: draft.preferences.other_activities,
      enjoyed_exercises: draft.preferences.enjoyed_exercises,
      disliked_exercises: draft.preferences.disliked_exercises,
      sport: showSport(draft) ? draft.preferences.sport || null : null,
    },
    equipment: {
      preset: draft.equipment.preset || null,
      available: draft.equipment.available,
    },
    considerations: {
      avoided_exercises: [...new Set([...draft.considerations.avoided_exercises, ...draft.preferences.disliked_exercises])].filter(
        (id) => !draft.preferences.enjoyed_exercises.includes(id),
      ),
      movement_restrictions: draft.considerations.movement_restrictions,
      limitation_note: draft.considerations.limitation_note.trim() || null,
    },
  };
  return {
    display_name: assessment.identity.display_name || null,
    goal: LEGACY_GOAL[draft.goals.primary] || "build_strength",
    experience: (draft.experience.level || "beginner") as Profile["experience"],
    days_per_week: draft.schedule.days_per_week,
    session_duration_minutes: sessionMinutes(draft),
    equipment: equipment.length ? equipment : ["bodyweight"],
    current_squat_load_kg: squatKg,
    optional_height_cm: assessment.identity.height_cm ?? null,
    optional_weight_kg: weightKg,
    limitations,
    age_range: assessment.identity.age_range ?? null,
    assessment,
  };
}

export function legacyEquipment(available: string[]): string[] {
  const mapped: string[] = [];
  for (const item of available) {
    const alias = LEGACY_EQUIPMENT[item];
    if (alias && !mapped.includes(alias)) mapped.push(alias);
  }
  if (!mapped.includes("bodyweight")) mapped.push("bodyweight");
  return mapped;
}

export function labelFor(id: string | null | undefined): string {
  if (!id) return "Not specified";
  const all = [
    ...PRIMARY_GOALS,
    ...EXPERIENCE_LEVELS,
    ...ENVIRONMENTS,
    ...STYLES,
    ...PREFERRED_SPLITS,
    ...CATALOG_CHOICES,
    ...RESTRICTIONS,
    ...AMBITIONS,
  ];
  return all.find((item) => item.id === id)?.label || id.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function equipmentSummary(draft: AssessmentDraft): string {
  if (!draft.equipment.available.length) return "Not specified";
  const preset = draft.equipment.preset;
  const expected = preset && PRESETS[preset] ? [...PRESETS[preset]].sort().join("|") : "";
  const actual = [...draft.equipment.available].sort().join("|");
  if (preset && expected && expected === actual) return labelFor(preset);
  if (preset && expected) return `${labelFor(preset)} · customized`;
  const count = draft.equipment.available.length;
  return `${count} item${count === 1 ? "" : "s"} selected`;
}

const ENVIRONMENT_PRESET: Record<string, string> = {
  commercial_gym: "full_gym",
  combination: "full_gym",
  home_gym: "basic_home",
  minimal_home: "minimal",
};

const LOADED = new Set(["barbell", "dumbbells", "kettlebells", "weight_plates", "leg_press", "cable_machine", "smith_machine", "leg_extension", "leg_curl", "chest_press", "lat_pulldown"]);

/** Picking where you train fills an empty equipment list; it never overwrites a list you already chose. */
export function seedEquipment(environment: string, equipment: AssessmentDraft["equipment"]): AssessmentDraft["equipment"] {
  const preset = ENVIRONMENT_PRESET[environment];
  if (!preset || equipment.available.length > 0) return equipment;
  return { preset, available: [...PRESETS[preset]] };
}

export function equipmentMismatch(draft: AssessmentDraft): string | null {
  const environment = draft.identity.training_environment;
  if (!environment || !draft.equipment.available.length) return null;
  const loaded = draft.equipment.available.some((item) => LOADED.has(item));
  if ((environment === "commercial_gym" || environment === "combination") && !loaded) {
    return `You train at a ${labelFor(environment).toLowerCase()}, but your equipment list has no weights or machines. GhostRep plans from the list, so add what you use.`;
  }
  if (environment === "minimal_home" && draft.equipment.available.some((item) => ["barbell", "leg_press", "cable_machine", "smith_machine"].includes(item))) {
    return "Your list includes gym equipment for a minimal home setup. GhostRep plans from the list, so remove anything you do not have.";
  }
  return null;
}

export function blueprintSummary(draft: AssessmentDraft): string {
  const parts: string[] = [];
  const muscles = draft.goals.priority_muscles.filter((item) => item !== "full_body");
  if (draft.goals.training_focus === "lower_body") parts.push("prioritize lower-body training and open the week with a lower-body session");
  else if (muscles.length) parts.push(`emphasize ${muscles.map((item) => item.replaceAll("_", " ")).join(" and ")}`);
  else if (draft.goals.priority_muscles.includes("full_body")) parts.push("train for balanced development across the week");
  else if (draft.goals.primary) parts.push(`follow a ${labelFor(draft.goals.primary).toLowerCase()} goal`);
  if (draft.schedule.days_per_week > 0) {
    const days = draft.schedule.days_per_week;
    parts.push(`fit ${days} weekly session${days === 1 ? "" : "s"}`);
  }
  if (draft.equipment.available.length) {
    const count = draft.equipment.available.length;
    parts.push(draft.equipment.preset ? `use ${equipmentSummary(draft).toLowerCase()} equipment` : `use your ${count} selected equipment item${count === 1 ? "" : "s"}`);
  }
  else if (draft.identity.training_environment) parts.push(`train at ${labelFor(draft.identity.training_environment).toLowerCase()}`);
  if (!parts.length) return "Your answers will show up here as you choose them.";
  const mismatch = equipmentMismatch(draft);
  return `Your plan will ${parts.join(" and ")}.${mismatch ? ` ${mismatch}` : ""}`;
}

export function draftHasAnswers(draft: AssessmentDraft): boolean {
  return Boolean(
    draft.identity.display_name.trim() ||
      draft.goals.primary ||
      draft.experience.level ||
      draft.equipment.available.length,
  );
}

export function draftFromProfile(profile: Profile): AssessmentDraft {
  const draft = emptyDraft();
  const assessment: AssessmentDocument | null | undefined = profile.assessment;
  if (!assessment) {
    draft.identity.display_name = profile.display_name || "";
    draft.experience.level = profile.experience;
    draft.schedule.days_per_week = profile.days_per_week;
    draft.equipment.available = profile.equipment.includes("barbell") ? ["barbell", "bodyweight"] : ["bodyweight"];
    if (profile.current_squat_load_kg) draft.experience.squat_weight = String(profile.current_squat_load_kg);
    return draft;
  }
  draft.identity.display_name = assessment.identity.display_name || profile.display_name || "";
  draft.identity.preferred_weight_unit = assessment.identity.preferred_weight_unit === "lb" ? "lb" : "kg";
  draft.identity.training_environment = assessment.identity.training_environment || "";
  draft.identity.age_range = assessment.identity.age_range || "";
  draft.identity.adult_confirmed = Boolean(assessment.identity.adult_confirmed) || (Boolean(assessment.identity.age_range) && assessment.identity.age_range !== "under_18");
  draft.identity.height_cm = assessment.identity.height_cm ? String(assessment.identity.height_cm) : "";
  const unit = draft.identity.preferred_weight_unit;
  if (assessment.identity.weight_kg) {
    draft.identity.weight = String(unit === "lb" ? kgToPounds(assessment.identity.weight_kg) : assessment.identity.weight_kg);
  }
  draft.goals.primary = assessment.goals.primary || "";
  draft.goals.training_focus = assessment.goals.training_focus === "lower_body" ? "lower_body" : "balanced";
  draft.goals.secondary = assessment.goals.secondary || "";
  draft.goals.priority_muscles = assessment.goals.priority_muscles || [];
  draft.goals.ambitions = assessment.goals.ambitions || [];
  draft.goals.personal_objective = assessment.goals.personal_objective || "";
  draft.goals.planning_horizon_weeks = assessment.goals.planning_horizon_weeks ? String(assessment.goals.planning_horizon_weeks) : "";
  draft.experience.level = assessment.experience.level || profile.experience;
  draft.experience.training_history = assessment.experience.training_history || "";
  draft.experience.consistency = assessment.experience.consistency || "";
  draft.experience.current_split = assessment.experience.current_split || "";
  draft.experience.exercise_familiarity = assessment.experience.exercise_familiarity || {};
  const squat = assessment.experience.working_sets?.barbell_squat;
  if (squat?.weight_kg) {
    draft.experience.squat_weight = String(unit === "lb" ? kgToPounds(squat.weight_kg) : squat.weight_kg);
    draft.experience.squat_reps = squat.reps ? String(squat.reps) : "";
    draft.experience.squat_sets = squat.sets ? String(squat.sets) : "";
  }
  draft.schedule.days_per_week = assessment.schedule.days_per_week || profile.days_per_week;
  draft.schedule.preferred_days = assessment.schedule.preferred_days || [];
  const minutes = assessment.schedule.session_minutes;
  const matched = DURATION_BANDS.find((band) => band.id !== "custom" && band.minutes === minutes);
  draft.schedule.duration_band = assessment.schedule.duration_band || matched?.id || "";
  if (draft.schedule.duration_band === "custom") draft.schedule.custom_minutes = String(minutes || "");
  draft.preferences.training_style = assessment.preferences.training_style || "";
  draft.preferences.preferred_split = assessment.preferences.preferred_split || "";
  draft.preferences.intensity = assessment.preferences.intensity || "";
  draft.preferences.other_activities = assessment.preferences.other_activities || [];
  draft.preferences.enjoyed_exercises = assessment.preferences.enjoyed_exercises || [];
  draft.preferences.disliked_exercises = assessment.preferences.disliked_exercises || [];
  draft.preferences.sport = assessment.preferences.sport || "";
  draft.equipment.preset = assessment.equipment.preset || "";
  draft.equipment.available = assessment.equipment.available || [];
  draft.considerations.avoided_exercises = assessment.considerations.avoided_exercises || [];
  draft.considerations.movement_restrictions = assessment.considerations.movement_restrictions || [];
  draft.considerations.limitation_note = assessment.considerations.limitation_note || "";
  return draft;
}
