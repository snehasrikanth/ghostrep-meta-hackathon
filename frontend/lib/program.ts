import type {
  ProgramDay,
  ProgramWorkout,
  WorkoutPlan,
  TrainingStructure,
  Program,
} from "./types";

export function localISODate(value: Date = new Date()): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function findDay(
  weeks: { days: ProgramDay[] }[] | undefined,
  weekIndex: number,
  weekday: string,
): ProgramDay | null {
  const week = weeks?.[weekIndex];
  if (!week) return null;
  return week.days.find((day) => day.weekday === weekday) || null;
}

export function dayHref(day: ProgramDay, weekIndex: number): string {
  if (!day.is_preview && day.plan_id) return `/workouts/${day.plan_id}`;
  return `/program/preview?week=${weekIndex}&day=${day.weekday}`;
}

export function dayAction(day: ProgramDay): string {
  if (day.kind === "recovery") return "View recovery day";
  if (
    !day.is_preview &&
    (day.session_status === "active" || day.session_status === "paused")
  )
    return "Resume workout";
  if (!day.is_preview && day.plan_id) return "View workout";
  return "Preview workout";
}

/** Recording respects unfinished-workout and acceptance rules. */
export function recordingDestination(program: Program) {
  const days = program.weeks.flatMap(week => week.days.map(day => ({day, week: week.week_index})));
  const openDay = days.find(({day}) => ["active", "paused"].includes(day.session_status || ""));
  const open = program.open_session || (openDay ? {id: "", plan_id: openDay.day.plan_id, status: openDay.day.session_status!} : null);
  if (open) {
    const day = days.find(item => item.day.plan_id === open.plan_id)?.day;
    const canCoach = Boolean(day?.workout?.has_video_analysis);
    return {
      href: open.plan_id ? "/workouts/" + open.plan_id : "/record?session=" + open.id,
      label: canCoach ? "Continue video workout" : "Continue unfinished workout",
      description: canCoach
        ? "Your workout is open. Continue it, then choose Record workout for your video check-in."
        : "Continue your open workout before switching sessions. You can record a replay there; video coaching is available in your barbell-squat sessions.",
      canCoach,
      exerciseName: canCoach ? "Barbell Back Squat" : undefined,
    };
  }
  if (program.proposal_id && !program.is_accepted) {
    return {href: "/workouts/" + program.proposal_id, label: program.proposal_kind === "session" ? "Review your session" : "Review your week",
      description: "Review and accept your proposal before starting a recording.", canCoach: false, exerciseName: undefined};
  }
  const eligible = days.filter(({day}) => day.kind === "training" && day.workout?.has_video_analysis &&
    !["completed", "abandoned"].includes(day.session_status || ""));
  const choice = eligible.find(({day}) => day.is_next) ||
    eligible.find(({day}) => day.date >= program.today) || eligible[0];
  if (choice) return {
    href: dayHref(choice.day, choice.week),
    label: choice.day.is_preview ? "Preview video workout" : "Open video workout",
    description: choice.day.is_preview
      ? "Preview this upcoming session, choose Use this session, then Record workout."
      : "Open your ready-to-train session, then choose Record workout.",
    canCoach: true, exerciseName: "Barbell Back Squat",
  };
  return {href: "/onboarding", label: "Plan another week", canCoach: false, exerciseName: undefined,
    description: "No unfinished video-coached session is available in this plan. Build another week from your profile. Saved recordings remain in Progress."};
}

export function exercisePreview(
  workout: ProgramWorkout | null,
  limit = 3,
): string {
  if (!workout?.exercises?.length) return "Details available in the preview.";
  const names = workout.exercises.map(
    (item) => item.name || item.exercise_id.replaceAll("_", " "),
  );
  if (names.length <= limit) return names.join(" · ");
  return `${names.slice(0, limit).join(" · ")} +${names.length - limit}`;
}

export function splitLabel(split: string | null | undefined): string {
  if (split === "upper_lower") return "upper/lower";
  if (split === "push_pull_legs") return "push/pull/legs";
  if (split === "full_body") return "full-body";
  return split?.replaceAll("_", " ") || "your split";
}

export function structureHeadline(split: string, count: number): string {
  const title =
    (
      {
        full_body: "Full body",
        upper_lower: "Upper/lower",
        push_pull_legs: "Push/pull/legs",
        mixed: "Mixed focus",
      } as Record<string, string>
    )[split] || "Personalized training";
  return `${title} · ${count} ${count === 1 ? "session" : "sessions"} per week`;
}

export function structureDescription(split: string): string {
  if (split === "full_body")
    return "Each session includes upper- and lower-body movements, with a different emphasis. That is different from splitting the body across separate days.";
  if (split === "upper_lower")
    return "Upper- and lower-body sessions alternate. Balanced development comes from the whole week, not from training the whole body in every session.";
  if (split === "push_pull_legs")
    return "Push, pull, and leg sessions each focus on one pattern. Together they cover a balanced week.";
  return "Each session has its own focus. Together, the sessions build a balanced training week.";
}

export function planStructure(plan: WorkoutPlan): TrainingStructure {
  if (plan.training_structure) return plan.training_structure;
  const preferred = plan.why?.inputs.find(
    (item) => item.field === "preferred_split",
  )?.value;
  const count =
    plan.schedule?.length ||
    Number(
      plan.why?.inputs.find((item) => item.field === "days_per_week")?.value,
    ) ||
    1;
  const types = (plan.schedule || []).map((day) => day.session_type || "");
  const split =
    types.length && types.every((type) => type.startsWith("full_body"))
      ? "full_body"
      : typeof preferred === "string"
        ? preferred
        : "mixed";
  return {
    split,
    sessions_per_week: count,
    session_index: Math.max(
      0,
      plan.schedule?.findIndex((day) => day.workout_name === plan.name) ?? 0,
    ),
    proposal_kind: "week",
  };
}
