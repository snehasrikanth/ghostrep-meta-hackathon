export type Goal =
  | "build_strength"
  | "build_muscle"
  | "improve_conditioning"
  | "learn_technique";
export type Experience = "beginner" | "intermediate" | "advanced";

export type AssessmentDocument = {
  identity: {
    display_name?: string | null;
    preferred_weight_unit?: "kg" | "lb";
    training_environment?: string | null;
    age_range?: string | null;
    adult_confirmed?: boolean;
    height_cm?: number | null;
    weight_kg?: number | null;
  };
  goals: {
    primary?: string;
    training_focus?: "balanced" | "lower_body";
    secondary?: string | null;
    priority_muscles?: string[];
    ambitions?: string[];
    personal_objective?: string | null;
    planning_horizon_weeks?: number | null;
  };
  experience: {
    level?: string;
    training_history?: string | null;
    consistency?: string | null;
    current_split?: string | null;
    exercise_familiarity?: Record<string, string>;
    working_sets?: Record<
      string,
      { weight_kg?: number | null; reps?: number | null; sets?: number | null }
    >;
  };
  schedule: {
    days_per_week?: number;
    preferred_days?: string[];
    session_minutes?: number;
    duration_band?: string;
  };
  preferences: {
    training_style?: string | null;
    preferred_split?: string | null;
    intensity?: string | null;
    other_activities?: { activity: string; sessions_per_week: number }[];
    enjoyed_exercises?: string[];
    disliked_exercises?: string[];
    sport?: string | null;
  };
  equipment: { preset?: string | null; available?: string[] };
  considerations: {
    avoided_exercises?: string[];
    movement_restrictions?: string[];
    limitation_note?: string | null;
  };
};

export type Profile = {
  id: string;
  user_id: string;
  goal: Goal;
  experience: Experience;
  days_per_week: number;
  session_duration_minutes: number;
  equipment: string[];
  current_squat_load_kg: number | null;
  optional_height_cm: number | null;
  optional_weight_kg: number | null;
  limitations: string[];
  display_name?: string | null;
  age_range?: string | null;
  assessment?: AssessmentDocument | null;
};

export type WorkoutExercise = {
  id: string;
  exercise_id: string;
  name?: string;
  video_analysis?: boolean;
  measure?: "reps" | "seconds";
  position: number;
  sets: number;
  target_reps: number;
  rest_seconds: number;
  suggested_load_kg: number | null;
  notes: string | null;
};

export type ProposalInput = {
  field: string;
  label: string;
  value: unknown;
};

export type ProposalWhy = {
  kind: "inputs_used";
  disclaimer: string;
  inputs: ProposalInput[];
  recent_sessions: unknown[];
  generated_at?: string | null;
  model_summary?: string | null;
  model_explanation_present: boolean;
};

export type TrainingStructure = {
  week_id?: string;
  split: string;
  sessions_per_week: number;
  session_index: number;
  proposal_kind: "week" | "session";
  preferred_days?: string[];
};

export type WorkoutPlan = {
  training_structure?: TrainingStructure;
  id: string;
  name: string;
  status: string;
  source: string;
  source_label: string;
  duration_minutes: number;
  estimated_minutes?: number | null;
  session_type?: string | null;
  created_at?: string | null;
  notes: string | null;
  warnings?: string[];
  why?: ProposalWhy | null;
  rationale?: string;
  warmup?: string[];
  schedule?:
    | {
        workout_name: string;
        rationale?: string;
        warmup?: string[];
        session_type?: string | null;
        duration_minutes: number;
        estimated_minutes?: number | null;
        exercises?: WorkoutExercise[];
      }[]
    | null;
  exercises: WorkoutExercise[];
};

export type ProgramSource =
  | "saved_muse"
  | "saved_fixture"
  | "saved_local"
  | "local_preview"
  | "sample";

export type ProgramWorkout = {
  rationale?: string;
  warmup?: string[];
  name: string;
  session_type: string | null;
  duration_minutes: number;
  estimated_minutes: number | null;
  notes: string | null;
  exercises: WorkoutExercise[];
  has_video_analysis: boolean;
  is_preview: boolean;
};

export type ProgramDay = {
  date: string;
  weekday: string;
  weekday_label: string;
  kind: "training" | "recovery";
  is_today: boolean;
  is_next: boolean;
  is_preview: boolean;
  plan_id: string | null;
  session_status: string | null;
  source: ProgramSource;
  source_label: string;
  placement_note: string | null;
  detail_note: string | null;
  recovery_copy: string | null;
  workout: ProgramWorkout | null;
};

export type ProgramWeek = {
  week_index: number;
  start: string;
  label: string;
  is_repeat: boolean;
  days: ProgramDay[];
};

export type Program = {
  is_accepted?: boolean;
  proposal_id?: string | null;
  proposal_kind?: "week" | "session" | null;
  open_session?: {id: string; plan_id: string | null; status: string} | null;
  split: string;
  days_per_week: number;
  preferred_days: string[];
  training_days: string[];
  placement_mode: "preferred" | "suggested";
  placement_note: string | null;
  today: string;
  week_count: number;
  weeks: ProgramWeek[];
};

export type RecordedSet = {
  id: string;
  session_id: string;
  exercise_id: string;
  exercise_name?: string;
  entry_source: "manual" | "video" | "demo";
  set_index: number | null;
  load_kg: number | null;
  target_reps: number | null;
  completed_reps: number | null;
  reported_rpe: number | null;
  processing_status: string;
  processing_message: string | null;
  duration_seconds: number | null;
  created_at: string | null;
  raw_deleted: boolean;
  has_video: boolean;
  analysis_requested?: boolean;
  has_analysis?: boolean;
  is_sample?: boolean;
  reference_rep?: number | null;
  sam_status?: string | null;
  coaching_decision?: string | null;
  coaching_action?: string | null;
  coaching_source?: string | null;
};

export type SessionStatus = "active" | "paused" | "completed" | "abandoned" | "sample";

export type Session = {
  sample_only?: boolean;
  id: string;
  plan_id: string | null;
  plan_name: string | null;
  session_type: string | null;
  status: SessionStatus;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  summary: {
    completed_sets: number;
    planned_sets: number | null;
    total_reps: number;
    timed_seconds?: number;
    volume_kg: number;
    exercises: string[];
  };
  sets: RecordedSet[];
};

export type Landmark = {
  name: string;
  x: number;
  y: number;
  visibility: number;
};

export type Rep = {
  rep_id: number;
  start_seconds: number;
  bottom_seconds: number;
  end_seconds: number;
  descent_seconds: number;
  ascent_seconds: number;
  is_complete: boolean;
  is_reference: boolean;
  confidence: number;
  comparison_eligible?: boolean;
  movement_status?: string;
  reliability?: {valid_fraction:number;issues:string[]};
  metrics: Record<string, number | null>;
};

export type DriftPoint = {
  rep_id: number;
  similarity: number | null;
  reference_deviation?: number | null;
  progressive_drift?: number | null;
  /** Legacy alias: unsigned RMS magnitude, never anatomical direction. */
  torso_lean_difference_deg: number | null;
  torso_angle_rmse_deg?: number | null;
  upper_body_comparison?: {direction:string;method:string;signed_mean_difference_deg:number|null;valid_samples:number};
  depth_difference_percent: number | null;
  ascent_duration_difference_percent: number | null;
  descent_duration_difference_percent: number | null;
  knee_angle_rmse_deg: number | null;
  hip_rmse: number | null;
  comparison_valid?: boolean;
  onset: boolean;
};

export type CoachingObservation = {
  rep_id?: number;
  metric: string;
  statement: string;
  evidence_seconds: number[];
  magnitude: number | null;
};

export type AppliedChange = {
  applied: boolean;
  action?: string;
  reason?: string;
  session_status?: string | null;
  plan_id?: string | null;
  exercise_id?: string | null;
  before?: {
    target_reps: number;
    rest_seconds: number;
    suggested_load_kg: number | null;
  };
  after?: {
    target_reps: number;
    rest_seconds: number;
    suggested_load_kg: number | null;
  };
};

export type Analysis = {
  set_index?: number | null;
  previous_set_comparison?: SetComparison | null;
  detected_reps?: number;
  planned_reps?: number | null;
  partial_movements?: number;
  uncertain_movements?: number;
  measurement_warning?: string | null;
  processing_started_at?: string | null;
  stage_started_at?: string | null;
  stage_timings?: Record<string,number>;
  processing_stalled?: boolean;
  is_sample?: boolean;
  session_paused_at?: string | null;
  id: string;
  set_id: string;
  session_id?: string | null;
  plan_id?: string | null;
  session_status?: string | null;
  status: string;
  message: string | null;
  exercise_id: string;
  duration_seconds: number | null;
  completed_reps: number | null;
  reference_rep: number | null;
  tracking_quality: {
    comparison_usable?: boolean;
    unreliable_rep_ids?: number[];
    unreliable_intervals?: {start_seconds:number;end_seconds:number;reason:string}[];
    usable: boolean;
    score: number;
    side: string;
    issues: { code: string; message: string; severity: string }[];
    notes: string[];
  } | null;
  reps: Rep[];
  drift: DriftPoint[];
  pose_available: boolean;
  sam_available: boolean;
  sam_status: string;
  analysis_version: string;
  mode: string;
};

export type ComparedSet = {
  set_id: string;
  label: string;
  set_number: number | null;
  recorded_at: string;
  detected_reps: number;
  usable_reps: number;
  planned_reps: number | null;
  logged_reps: number | null;
  load_kg: number | null;
  reported_effort: number | null;
};

export type SetComparison = {
  version: "set-comparison-v1";
  status: "first" | "compared" | "unavailable";
  emoji: string;
  headline: string;
  summary: string;
  previous: ComparedSet | null;
  current: ComparedSet | null;
  metrics: {key:string;label:string;unit:"reps"|"seconds_per_rep";previous:number;current:number;change:string|null}[];
  follow_up: {
    status: "improved" | "remains" | "unavailable";
    metric: string | null;
    previous_observation: string | null;
    explanation: string;
    evidence: {set_id:string;rep_id:number;seconds:number} | null;
  } | null;
  next_step: string | null;
  details: string[];
};

export type OverlayFrame = {
  t: number;
  active_rep: number | null;
  phase: string;
  phase_progress: number;
  current: Landmark[];
  reference: Landmark[] | null;
  silhouette?: { x: number; y: number }[] | null;
  reference_silhouette?: { x: number; y: number }[] | null;
};

export type Overlay = {
  analysis_id: string;
  video_url: string | null;
  reference_rep: number | null;
  skeleton_edges: [string, string][];
  frames: OverlayFrame[];
  sam_available: boolean;
  sam_status: string;
  color_reference: string;
  color_current: string;
  silhouette_source?: string;
  silhouette_label?: string;
};

export type Coaching = {
  presentation?: {
    version: "set-decision-v1";
    decision_basis: string;
    explanation_key: string;
    explanation_source: "deterministic" | "validated_model_selection";
    reported_effort: number | null;
    measurement_uncertain: boolean;
    review_only: boolean;
    evidence: {id:string;rep_id:number;seconds:number}[];
    observations: CoachingObservation[];
  };
  interpretation_version?: string;
  historical_interpretation_corrected?: boolean;
  interpretation_notice?: string;
  is_sample?: boolean;
  primary_cue?: string | null;
  id: string;
  set_id: string;
  plan_id?: string | null;
  session_status?: string | null;
  source: string;
  source_label: string;
  summary: string;
  observations: CoachingObservation[];
  evidence_references: number[];
  confidence_notes: string[];
  uncertainties: string[];
  suggested_action: string;
  reason: string;
  requires_confirmation: boolean;
  suggested_reps: number | null;
  suggested_rest_seconds: number | null;
  suggested_load_kg: number | null;
  current_reps: number | null;
  current_rest_seconds: number | null;
  current_load_kg: number | null;
  planned_set_reps?: number | null;
  planned_set_load_kg?: number | null;
  completed_reps?: number | null;
  workout_reps?: number | null;
  workout_rest_seconds?: number | null;
  workout_load_kg?: number | null;
  user_decision: "pending" | "accepted" | "rejected";
  actionable?: boolean;
  state?: "review_only" | "actionable" | "superseded" | "already_decided";
  revision?: number;
  active_version_id?: string | null;
  action_blocked_reason?: string | null;
  applied_change?: AppliedChange | null;
  stored_versions?: StoredCoachingVersion[];
};

export type StoredCoachingVersion = {
  id: string;
  set_id: string;
  source: string;
  source_label: string;
  suggested_action: string;
  summary: string;
  reason: string;
  observations: CoachingObservation[];
  uncertainties: string[];
  artifact_id: string;
  actionable: boolean;
  state: "review_only" | "actionable" | "superseded" | "already_decided";
  can_activate: boolean;
  activation_blocked_reason?: string | null;
  user_decision: "pending" | "accepted" | "rejected";
  suggested_reps?: number | null;
  suggested_rest_seconds?: number | null;
  suggested_load_kg?: number | null;
  created_at: string | null;
};

export type SavedLiveWorkout = {
  available: boolean;
  reason?: string;
  attempt_id?: string;
  source?: string;
  source_label?: string;
  name?: string;
  notes?: string;
  session_type?: string | null;
  duration_minutes?: number;
  estimated_minutes?: number | null;
  exercises?: WorkoutExercise[];
  schedule?: WorkoutPlan["schedule"];
  warnings?: string[];
  chat_calls?: number;
  schema_validation?: string;
};
