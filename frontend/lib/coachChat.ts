export const COACH_QUESTIONS = [
  "Explain this set.",
  "What happened in rep 3?",
  "Did I improve since my previous set?",
  "What should I focus on next?",
  "Why was this rest change suggested?",
];

export type CoachEvidence = {id:string;set_id:string;rep_id:number;seconds:number;label:string;href:string};
export type CoachAction = {
  kind: "replay" | "review_recommendation" | "view_comparison" | "watch_demo" | "workout";
  label: string;
  emphasis?: "primary" | "secondary";
  set_id?: string;
  rep_id?: number;
  seconds?: number;
  href?: string | null;
};
export type CoachReply = {
  set_id: string;
  headline?: string;
  answer: string;
  evidence: CoachEvidence[];
  uncertainty: string | null;
  suggested_ui_action: "none" | "replay" | "view_comparison" | "watch_demo" | "review_recommendation";
  actions?: CoachAction[];
  source: "basic" | "muse_spark";
  notice: string | null;
  basis: string;
};
export type CoachStatus = {available:boolean;consent_version:string;max_question_chars:number;previous_question_limit:number;timeout_seconds:number};
export type CoachTurn = {question:string;reply:CoachReply};

export function questionHistory(turns:CoachTurn[]) {
  return turns.slice(-2).map(t=>t.question.slice(0,400));
}

export function validCoachQuestion(question:string) {
  return question.trim().length>0 && question.length<=400 && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(question);
}

// Generate application links, ignoring any model/server-supplied href markup.
export function coachReplayHref(e:Pick<CoachEvidence,"set_id"|"rep_id"|"seconds">) {
  if (!/^[a-f0-9-]{36}$/i.test(e.set_id) || !Number.isInteger(e.rep_id) || e.rep_id<1 || !Number.isFinite(e.seconds) || e.seconds<0) return null;
  return `/analysis/${e.set_id}?rep=${e.rep_id}&t=${e.seconds}`;
}

export function safeCoachHref(href?:string|null) {
  return href && /^\/workouts\/[a-f0-9-]{36}$/i.test(href) ? href : null;
}

/** New replies carry actions. Older replies still render from evidence and the single action. */
export function coachActions(reply:CoachReply):CoachAction[] {
  if (reply.actions) return reply.actions.filter(action => Boolean(action?.label) && (action.kind !== "workout" || Boolean(safeCoachHref(action.href)))).slice(0, 2);
  const actions:CoachAction[] = [];
  for (const evidence of reply.evidence || []) {
    const href = coachReplayHref(evidence);
    if (!href) continue;
    actions.push({kind:"replay", label:evidence.label || `Compare rep ${evidence.rep_id}`, emphasis:actions.length?"secondary":"primary", set_id:evidence.set_id, rep_id:evidence.rep_id, seconds:evidence.seconds, href});
  }
  const extra:Record<string, CoachAction> = {
    review_recommendation:{kind:"review_recommendation", label:"Review recommendation"},
    view_comparison:{kind:"view_comparison", label:"View comparison"},
    watch_demo:{kind:"watch_demo", label:"Watch squat demo"},
  };
  const suggested = extra[reply.suggested_ui_action];
  if (suggested && !actions.some(action => action.kind===suggested.kind)) actions.push({...suggested, emphasis:actions.length?"secondary":"primary"});
  return actions.slice(0, 2);
}
