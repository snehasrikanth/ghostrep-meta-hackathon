import type { AssessmentDraft } from "./assessment";
import { resolveApiBase } from "./apiBase";
import type { CoachReply, CoachStatus } from "./coachChat";
import type {
  Analysis,
  Coaching,
  Overlay,
  Profile,
  Program,
  RecordedSet,
  SavedLiveWorkout,
  Session,
  StoredCoachingVersion,
  WorkoutPlan,
} from "./types";

const BASE = resolveApiBase(
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  typeof window === "undefined" ? undefined : window.location.hostname,
);

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...(init?.headers || {}),
      },
    });
  } catch {
    throw new ApiError(
      0,
      "GhostRep could not reach the server. Check that the backend is running.",
      null,
    );
  }
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      detail = await response.text().catch(() => response.statusText);
    }
    throw new ApiError(response.status, messageFrom(detail), detail);
  }
  return response.json() as Promise<T>;
}

function messageFrom(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((item) => item?.msg || JSON.stringify(item)).join(" ");
  if (detail && typeof detail === "object" && "message" in detail)
    return String((detail as { message: unknown }).message);
  return JSON.stringify(detail);
}

export type SetLog = {
  exercise_id: string;
  set_index: number;
  completed_reps: number;
  load_kg?: number | null;
  target_reps?: number | null;
  reported_rpe?: number | null;
};

export type MetaStatus = {
  enable_meta_api: boolean;
  workout_ready: boolean;
  coaching_ready: boolean;
  sam_ready: boolean;
  sam_target_fps: number | null;
  sam_max_video_seconds: number;
  sam_min_frames: number;
  call_limit_reached: boolean;
  call_limit_reason: string | null;
  remaining_calls: number | null;
  estimates: {
    muse_small_call_usd: number;
    muse_coaching_call_usd: number;
    sam_video_per_1000_frames_usd: number;
  };
};

export const api = {
  catalog: () => request<{ exercises: { id: string; name: string; video_analysis: boolean }[] }>("/catalog"),
  health: () =>
    request<{
      ok: boolean;
      ai_provider: string;
      enable_meta_api: boolean;
      mode: string;
    }>("/health"),
  metaStatus: () => request<MetaStatus>("/meta/status"),
  getProfile: () => request<Profile>("/profiles/me"),
  getDraft: () =>
    request<{ draft: AssessmentDraft; submitted: boolean }>("/profiles/draft"),
  saveDraft: (draft: AssessmentDraft) =>
    request<{ draft: AssessmentDraft; submitted: boolean }>("/profiles/draft", {
      method: "PUT",
      body: JSON.stringify({ draft }),
    }),
  saveProfile: (payload: Omit<Profile, "id" | "user_id">) =>
    request<Profile>("/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  generateWorkout: async (consent = false) => {
    const status = consent ? await request<MetaStatus>("/meta/status") : null;
    return request<WorkoutPlan>("/workouts/generate", {
      method: "POST",
      body: JSON.stringify({
        approve_meta_spend: Boolean(consent && status?.workout_ready),
      }),
    });
  },
  listWorkouts: () => request<{ plans: WorkoutPlan[] }>("/workouts"),
  nextWorkout: () => request<{ plan: WorkoutPlan | null }>("/workouts/next"),
  getProposal: () =>
    request<{ plan: WorkoutPlan | null }>("/workouts/proposal"),
  getSavedLiveWorkout: () => request<SavedLiveWorkout>("/workouts/saved-live"),
  importSavedWorkout: () =>
    request<WorkoutPlan>("/workouts/import-saved", { method: "POST" }),
  acceptWorkout: (id: string) =>
    request<WorkoutPlan>(`/workouts/${id}/accept`, { method: "POST" }),
  discardWorkout: (id: string) =>
    request<{ plan: WorkoutPlan | null; discarded: boolean }>(
      `/workouts/${id}/discard`,
      { method: "POST" },
    ),
  getWorkout: (id: string) => request<WorkoutPlan>(`/workouts/${id}`),
  getProgram: (today: string, weeks = 1) => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return request<Program>(
      `/program?today=${encodeURIComponent(today)}&weeks=${weeks}&tz=${encodeURIComponent(tz)}`,
    );
  },
  prepareSession: (today: string, weekIndex: number, weekday: string) =>
    request<WorkoutPlan>("/program/prepare", {
      method: "POST",
      body: JSON.stringify({
        today,
        week_index: weekIndex,
        weekday,
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }),
    }),
  demoStatus: () =>
    request<{
      available: boolean;
      active: boolean;
      seeded: boolean;
      can_return: boolean;
      display_name?: string | null;
    }>("/demo/status"),
  enterDemo: () =>
    request<{ ok: boolean; active: boolean; already: boolean }>("/demo/enter", {
      method: "POST",
    }),
  exitDemo: () =>
    request<{ ok: boolean; active: boolean; already: boolean }>("/demo/exit", {
      method: "POST",
    }),
  patchWorkout: (id: string, payload: unknown) =>
    request<WorkoutPlan>(`/workouts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  startSession: (plan_id?: string) =>
    request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify(plan_id ? { plan_id } : {}),
    }),
  currentSession: () =>
    request<{ session: Session | null }>("/sessions/current"),
  listSessions: () => request<{ sessions: Session[] }>("/sessions"),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  pauseSession: (id: string) =>
    request<Session>(`/sessions/${id}/pause`, { method: "POST" }),
  resumeSession: (id: string) =>
    request<Session>(`/sessions/${id}/resume`, { method: "POST" }),
  completeSession: (id: string) =>
    request<Session>(`/sessions/${id}/complete`, { method: "POST" }),
  abandonSession: (id: string) =>
    request<Session>(`/sessions/${id}/abandon`, { method: "POST" }),
  logSet: (id: string, body: SetLog) =>
    request<RecordedSet>(`/sessions/${id}/sets`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteSet: (id: string, setId: string) =>
    request<{ deleted: string }>(`/sessions/${id}/sets/${setId}`, {
      method: "DELETE",
    }),
  uploadVideo: (form: FormData) =>
    request<RecordedSet>("/videos/upload", {
      method: "POST",
      body: form,
    }),
  getRecording: (id: string) =>
    request<RecordedSet & { plan_id: string | null; session_status: string }>(`/recordings/${id}`),
  deleteMedia: (id: string) =>
    request<{ verified: boolean }>(`/recordings/${id}`, { method: "DELETE" }),
  getAnalysis: (id: string) => request<Analysis>(`/analysis/${id}`),
  getOverlay: (id: string) => request<Overlay>(`/analysis/${id}/overlay`),
  getCoaching: (id: string) => request<Coaching>(`/coaching/${id}`),
  coachChatStatus: (id:string) => request<CoachStatus>(`/coaching/${id}/chat/status`),
  askCoach: (id:string, body:{request_id:string;question:string;previous_questions:string[];selected_rep:number|null;approve_question:boolean;consent_version:string|null}, signal?:AbortSignal) => request<CoachReply>(`/coaching/${id}/chat`, {method:"POST",body:JSON.stringify(body),signal}),
  decideCoaching: (coaching: Coaching, decision: "accepted" | "rejected") =>
    request<Coaching>(`/coaching/${coaching.set_id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        recommendation_id: coaching.id,
        expected_revision: coaching.revision ?? 0,
      }),
    }),
  activateCoaching: (coaching: Coaching, versionId: string) =>
    request<Coaching>(
      `/coaching/${coaching.set_id}/versions/${versionId}/activate`,
      {
        method: "POST",
        body: JSON.stringify({
          recommendation_id: coaching.id,
          expected_revision: coaching.revision ?? 0,
        }),
      },
    ),
  importSavedCoaching: (id: string) =>
    request<StoredCoachingVersion>(`/coaching/${id}/import-saved`, {
      method: "POST",
    }),
  mediaUrl: (setId: string) => `${BASE}/media/${setId}`,
};

export { BASE as API_BASE };
