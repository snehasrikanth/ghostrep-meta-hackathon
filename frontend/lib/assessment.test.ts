import assert from "node:assert/strict";
import test from "node:test";

import {
  blueprintSummary,
  draftFromProfile,
  emptyDraft,
  equipmentMismatch,
  equipmentSummary,
  poundsToKg,
  seedEquipment,
  showMusclePriority,
  showSport,
  showSquatLoad,
  toggleMuscle,
  toProfilePayload,
  validateStep,
} from "./assessment.ts";

test("lower-body training focus survives profile serialization and reopening", () => {
  const draft = emptyDraft();
  draft.goals.primary = "build_muscle";
  draft.goals.training_focus = "lower_body";
  draft.experience.level = "intermediate";
  draft.schedule.days_per_week = 3;
  draft.schedule.duration_band = "45_60";
  draft.equipment.available = ["barbell", "bodyweight"];
  const payload = toProfilePayload(draft);
  assert.equal(payload.assessment.goals.training_focus, "lower_body");
  assert.equal(draftFromProfile({ ...payload, id: "p", user_id: "u" }).goals.training_focus, "lower_body");
  assert.match(blueprintSummary(draft), /lower-body session/);
});

test("pounds convert to kilograms and optional squat load stays out of bodyweight plans", () => {
  assert.equal(poundsToKg(100), 45.36);
  const draft = emptyDraft();
  draft.identity.display_name = "Alex";
  draft.identity.training_environment = "minimal_home";
  draft.identity.preferred_weight_unit = "lb";
  draft.goals.primary = "increase_strength";
  draft.experience.level = "intermediate";
  draft.experience.squat_weight = "100";
  draft.equipment.available = ["bodyweight"];
  draft.preferences.training_style = "strength";
  assert.equal(showSquatLoad(draft), false);
  const payload = toProfilePayload(draft);
  assert.equal(payload.current_squat_load_kg, null);
  draft.identity.weight = "200";
  assert.equal(toProfilePayload(draft).optional_weight_kg, poundsToKg(200));
});

test("barbell squat load is shown only when the lift and equipment are relevant", () => {
  const draft = emptyDraft();
  draft.goals.primary = "increase_strength";
  draft.experience.level = "intermediate";
  draft.equipment.available = ["barbell", "squat_rack"];
  assert.equal(showSquatLoad(draft), true);
  draft.experience.exercise_familiarity.barbell_squat = "new";
  assert.equal(showSquatLoad(draft), false);
  draft.experience.level = "beginner";
  draft.experience.exercise_familiarity = {};
  assert.equal(showSquatLoad(draft), false);
});

test("conditional questions follow the goal", () => {
  const draft = emptyDraft();
  draft.goals.primary = "improve_endurance";
  assert.equal(showMusclePriority(draft), false);
  assert.equal(showSport(draft), false);
  draft.goals.primary = "athletic_performance";
  assert.equal(showSport(draft), true);
  assert.equal(showMusclePriority(draft), true);
});

test("schedule, muscles, and required steps validate", () => {
  const draft = emptyDraft();
  assert.match(validateStep(0, draft) || "", /name/i);
  draft.identity.display_name = "Alex";
  draft.identity.training_environment = "commercial_gym";
  assert.match(validateStep(0, draft) || "", /18 or older/);
  draft.identity.adult_confirmed = true;
  assert.equal(validateStep(0, draft), null);
  draft.schedule.days_per_week = 4;
  draft.schedule.preferred_days = ["monday"];
  draft.schedule.duration_band = "45_60";
  assert.equal(validateStep(3, draft), null);
  assert.match(blueprintSummary(emptyDraft()), /answers will show up here/);
  assert.doesNotMatch(blueprintSummary(emptyDraft()), /4 weekly/);
  draft.equipment.preset = "full_gym";
  draft.equipment.available = ["barbell"];
  assert.match(equipmentSummary(draft), /customized/);
  assert.deepEqual(toggleMuscle(["glutes", "quadriceps", "hamstrings"], "calves"), ["glutes", "quadriceps", "hamstrings"]);
  assert.deepEqual(toggleMuscle(["glutes"], "full_body"), ["full_body"]);
});

test("training environment seeds equipment and the blueprint follows the equipment list", () => {
  const draft = emptyDraft();
  draft.identity.training_environment = "commercial_gym";
  draft.equipment = seedEquipment("commercial_gym", draft.equipment);
  assert.equal(draft.equipment.preset, "full_gym");
  assert.ok(draft.equipment.available.includes("barbell"));
  assert.equal(equipmentMismatch(draft), null);
  const chosen = { preset: "bodyweight", available: ["bodyweight"] };
  assert.deepEqual(seedEquipment("commercial_gym", chosen), chosen);
  draft.equipment = chosen;
  assert.match(equipmentMismatch(draft) || "", /no weights or machines/);
  assert.match(blueprintSummary(draft), /bodyweight/i);
  assert.doesNotMatch(blueprintSummary(draft), /train at commercial gym/);
  draft.identity.training_environment = "minimal_home";
  draft.equipment = { preset: null, available: ["barbell", "bodyweight"] };
  assert.match(equipmentMismatch(draft) || "", /minimal home/);
});

test("a completed draft round-trips the fields the planner reads", () => {
  const draft = emptyDraft();
  draft.identity.display_name = "Alex";
  draft.identity.training_environment = "commercial_gym";
  draft.identity.adult_confirmed = true;
  draft.identity.preferred_weight_unit = "kg";
  draft.goals.primary = "build_muscle";
  draft.goals.secondary = "increase_strength";
  draft.goals.priority_muscles = ["glutes", "quadriceps"];
  draft.experience.level = "intermediate";
  draft.experience.squat_weight = "80";
  draft.experience.squat_reps = "8";
  draft.schedule.days_per_week = 4;
  draft.schedule.preferred_days = ["monday", "tuesday", "thursday", "saturday"];
  draft.preferences.training_style = "hypertrophy";
  draft.equipment.preset = "full_gym";
  draft.equipment.available = ["barbell", "dumbbells", "leg_press"];
  draft.considerations.avoided_exercises = ["bench_press"];
  draft.identity.age_range = "65_74";
  const payload = toProfilePayload(draft);
  assert.equal(payload.age_range, "65_74");
  assert.equal(payload.assessment.identity.age_range, "65_74");
  assert.equal(payload.goal, "build_muscle");
  assert.equal(payload.current_squat_load_kg, 80);
  assert.equal(payload.assessment.schedule.days_per_week, 4);
  assert.deepEqual(payload.assessment.considerations.avoided_exercises, ["bench_press"]);
  assert.ok(payload.equipment.includes("barbell"));
  assert.ok(payload.equipment.includes("machines"));
  draft.identity.age_range = "";
  assert.equal(toProfilePayload(draft).age_range, null);
  assert.equal(validateStep(1, draft), null);
});
