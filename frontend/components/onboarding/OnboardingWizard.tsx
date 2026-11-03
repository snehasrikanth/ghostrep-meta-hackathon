"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { TrainingConsent } from "@/components/workout/TrainingConsent";
import { api } from "@/lib/api";
import {
  ACTIVITIES,
  AGE_RANGES,
  AMBITIONS,
  CATALOG_CHOICES,
  CONSISTENCY,
  DAYS,
  DRAFT_KEY,
  DURATION_BANDS,
  ENVIRONMENTS,
  EQUIPMENT_GROUPS,
  EXPERIENCE_LEVELS,
  HISTORIES,
  INTENSITIES,
  MUSCLES,
  PREFERRED_SPLITS,
  PRESETS,
  PRIMARY_GOALS,
  RESTRICTIONS,
  SPLITS,
  STYLES,
  ageLabel,
  blueprintSummary,
  draftFromProfile,
  draftHasAnswers,
  emptyDraft,
  equipmentMismatch,
  seedEquipment,
  equipmentSummary,
  labelFor,
  showMusclePriority,
  showSport,
  hasBarbell,
  showSquatLoad,
  showTechnicalLifts,
  toggleMuscle,
  toProfilePayload,
  validateStep,
  type AssessmentDraft,
} from "@/lib/assessment";
import { cn } from "@/lib/cn";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

const STEPS = [
  "About You",
  "Your Goals",
  "Training Experience",
  "Training Preferences",
  "Equipment & Considerations",
  "Review & Generate",
];

// Only wizard navigation/validation uses this. Answer and save updates do not.
function focusWizardDestination(element: HTMLElement | null) {
  element?.focus({ preventScroll: true });
  element?.scrollIntoView({ block: "start", behavior: "instant" });
}

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<AssessmentDraft>(emptyDraft);
  const [ready, setReady] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasPlan, setHasPlan] = useState(false);
  const [saving, setSaving] = useState(false);
  const [planConsent, setPlanConsent] = useState(false);
  const [query, setQuery] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const [draftState, setDraftState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");

  useLayoutEffect(() => {
    if (ready) focusWizardDestination(headingRef.current);
  }, [ready, step]);

  useLayoutEffect(() => {
    if (error) focusWizardDestination(errorRef.current);
  }, [error]);

  useEffect(() => {
    let cancelled = false;
    const stored = readDraft();
    Promise.allSettled([
      api.getProfile(),
      api.getDraft(),
      api.listWorkouts(),
    ]).then(([profile, serverDraft, plans]) => {
      if (cancelled) return;
      if (plans.status === "fulfilled")
        setHasPlan(plans.value.plans.length > 0);
      const storedDraft = stored?.draft;
      const storedIsUseful = Boolean(
        stored?.dirty && storedDraft && draftHasAnswers(storedDraft),
      );
      const remote =
        serverDraft.status === "fulfilled" ? serverDraft.value.draft : null;
      if (storedIsUseful && storedDraft) {
        setDraft(storedDraft);
        setStep(savedStep(storedDraft.ui_step));
      }
      else if (remote && draftHasAnswers(remote)) {
        setDraft(remote);
        setStep(savedStep(remote.ui_step));
      }
      else if (profile.status === "fulfilled")
        setDraft(draftFromProfile(profile.value));
      else if (storedDraft) setDraft(storedDraft);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ready || !touched) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ dirty: true, draft: {...draft, ui_step: step} }));
    const handle = window.setTimeout(() => {
      api
        .saveDraft({...draft, ui_step: step})
        .then(() => setDraftState("saved"))
        .catch(() => setDraftState("error"));
    }, 400);
    return () => window.clearTimeout(handle);
  }, [draft, ready, touched, step]);

  const summary = useMemo(() => blueprintSummary(draft), [draft]);

  function update(patch: (current: AssessmentDraft) => AssessmentDraft) {
    setTouched(true);
    setDraftState("saving");
    setError(null);
    setDraft(patch);
  }

  function goToStep(next: number) {
    setTouched(true);
    setError(null);
    if (next === step) focusWizardDestination(headingRef.current);
    setStep(next);
  }

  function continueStep() {
    const message = validateStep(step, draft);
    if (message) {
      if (message === error) focusWizardDestination(errorRef.current);
      setError(message);
      return;
    }
    goToStep(Math.min(STEPS.length - 1, step + 1));
  }

  async function generate() {
    const message = [0, 1, 2, 3, 4]
      .map((index) => validateStep(index, draft))
      .find(Boolean);
    if (message) {
      setError(message);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.saveProfile(toProfilePayload(draft));
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ dirty: false, draft }));
      const plan = await api.generateWorkout(planConsent);
      router.push(`/workouts/${plan.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save the profile.",
      );
      setSaving(false);
    }
  }

  if (!ready) return <p role="status" className="text-sm text-white/80">Loading your training profile…</p>;

  return (
    <div className="mx-auto grid max-w-7xl gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div>
        <p className="font-mono text-sm uppercase tracking-[0.2em] text-teal">
          Training profile
        </p>
        <h1
          ref={headingRef}
          tabIndex={-1}
          style={{ scrollMarginTop: "calc(var(--app-header-height, 4rem) + 1.25rem)" }}
          className="mt-2 font-display text-3xl font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal sm:text-4xl"
        >
          {STEPS[step]}
        </h1>
        <p className="mt-2 max-w-xl text-base leading-7 text-white/85">
          {step === 5
            ? "Confirm your week, then review the sessions before you start."
            : "Answer what you know. Optional questions can be skipped."}
        </p>
        {step === 0 && <p className="mt-3 max-w-xl text-sm leading-6 text-white/80">Video coaching currently supports barbell squats. Manual logging and saved video replay are available for other lifts. Optional questions can be left blank.</p>}
        <ol
          className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6"
          aria-label="Onboarding progress"
        >
          {STEPS.map((label, index) => (
            <li key={label}>
              <button
                type="button"
                className={cn(
                  "h-full min-h-11 w-full rounded-2xl border px-3 py-2 text-left text-sm leading-4",
                  index === step
                    ? "border-teal bg-teal/10 text-white"
                    : "border-white/10 text-white/80 hover:border-white/25",
                )}
                aria-current={index === step ? "step" : undefined}
                onClick={() => goToStep(index)}
              >
                <span className="font-mono text-[10px] tracking-wider text-teal">
                  0{index + 1}
                </span>
                <span className="mt-1 block">{label}</span>
              </button>
            </li>
          ))}
        </ol>

        <Card className="mt-6 p-5 sm:p-7">
          {step === 0 && <About draft={draft} update={update} />}
          {step === 1 && <Goals draft={draft} update={update} />}
          {step === 2 && <Experience draft={draft} update={update} />}
          {step === 3 && <Preferences draft={draft} update={update} />}
          {step === 4 && (
            <EquipmentStep
              draft={draft}
              update={update}
              query={query}
              setQuery={setQuery}
            />
          )}
          {step === 5 && (
            <Review
              draft={draft}
              summary={summary}
              hasPlan={hasPlan}
              onEdit={goToStep}
            />
          )}
          {step === 5 && (
            <TrainingConsent
              checked={planConsent}
              onChange={setPlanConsent}
              disabled={saving}
            />
          )}
          {error && (
            <div
              ref={errorRef}
              tabIndex={-1}
              role="group"
              aria-label="Profile needs attention"
              style={{ scrollMarginTop: "calc(var(--app-header-height, 4rem) + 1.25rem)" }}
              className="mt-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal"
            >
              <ActionFeedback kind="error">{error}</ActionFeedback>
            </div>
          )}
          {saving && (
            <div className="mt-4">
              <ActionFeedback kind="loading">
                Building your week around these preferences. This can take about
                a minute.
              </ActionFeedback>
            </div>
          )}
          {step === 5 && !planConsent && (
            <p className="mt-3 text-sm text-white/80">
              Agree above to enable plan generation. You’ll review the week
              before accepting.
            </p>
          )}
          {draftState !== "idle" && (
            <p role="status" className="mt-3 text-sm text-white/80">
              {draftState === "saving"
                ? "Saving your draft…"
                : draftState === "saved"
                  ? "Draft saved"
                  : "Your draft is saved on this device. The server couldn’t be reached."}
            </p>
          )}
          <div className="mt-6 flex items-center justify-between gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => goToStep(Math.max(0, step - 1))}
              disabled={step === 0}
            >
              Back
            </Button>
            {step < 5 ? (
              <Button type="button" onClick={continueStep}>
                Continue
              </Button>
            ) : (
              <Button
                type="button"
                loading={saving}
                loadingLabel="Building your week…"
                onClick={generate}
                disabled={saving || !planConsent}
              >
                {saving ? "Building your plan…" : "Build my week"}
              </Button>
            )}
          </div>
        </Card>
      </div>
      <aside className="xl:sticky xl:top-24 xl:self-start">
        <Summary draft={draft} summary={summary} />
      </aside>
    </div>
  );
}

function savedStep(value: number | undefined): number {
  return Number.isInteger(value) && value! >= 0 && value! < STEPS.length ? value! : 0;
}

function readDraft(): { dirty?: boolean; draft?: AssessmentDraft } | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function Summary({
  draft,
  summary,
}: {
  draft: AssessmentDraft;
  summary: string;
}) {
  const muscles =
    draft.goals.training_focus === "lower_body"
      ? "Legs & glutes"
      : draft.goals.priority_muscles.length
        ? draft.goals.priority_muscles.map((item) => labelFor(item)).join(", ")
        : "Not specified";
  return (
    <Card className="p-5">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal">
        Your training blueprint
      </p>
      <dl className="mt-4 space-y-3 text-sm">
        <Row label="Primary goal" value={labelFor(draft.goals.primary)} />
        <Row
          label="Training focus"
          value={
            draft.goals.training_focus === "lower_body"
              ? "Lower body"
              : "Balanced"
          }
        />
        <Row label="Secondary goal" value={labelFor(draft.goals.secondary)} />
        <Row
          label="Weekly training"
          value={
            draft.schedule.days_per_week
              ? `${draft.schedule.days_per_week} sessions`
              : "Not specified"
          }
        />
        <Row
          label="Age range"
          value={
            draft.identity.age_range
              ? ageLabel(draft.identity.age_range)
              : "Not specified"
          }
        />
        <Row label="Experience" value={labelFor(draft.experience.level)} />
        <Row label="Main focus" value={muscles} />
        <Row label="Training access" value={equipmentSummary(draft)} />
      </dl>
      <p className="mt-4 text-sm leading-6 text-white/80">{summary}</p>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-white/80">{label}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}

function About({ draft, update }: StepProps) {
  return (
    <div className="space-y-5">
      <Field label="Name" hint="This is the name shown on your dashboard.">
        <input
          className={inputClass}
          value={draft.identity.display_name}
          onChange={(event) =>
            update((current) => ({
              ...current,
              identity: {
                ...current.identity,
                display_name: event.target.value,
              },
            }))
          }
        />
      </Field>
      <ChoiceGroup
        label="Training environment"
        hint="Used to set a starting equipment list. You can change every item later."
      >
        <div className="grid gap-2 sm:grid-cols-2">
          {ENVIRONMENTS.map((item) => (
            <Choice
              key={item.id}
              selected={draft.identity.training_environment === item.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  identity: {
                    ...current.identity,
                    training_environment: item.id,
                  },
                  equipment: seedEquipment(item.id, current.equipment),
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup
        label="Weight units"
        hint="GhostRep stores loads in kilograms and shows the unit you pick."
      >
        <div className="flex gap-2">
          {(["kg", "lb"] as const).map((unit) => (
            <Choice
              key={unit}
              selected={draft.identity.preferred_weight_unit === unit}
              onClick={() =>
                update((current) => ({
                  ...current,
                  identity: {
                    ...current.identity,
                    preferred_weight_unit: unit,
                  },
                }))
              }
            >
              {unit === "kg" ? "Kilograms" : "Pounds"}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <label className="flex items-start gap-3 rounded-2xl border border-white/10 px-4 py-3">
        <input
          type="checkbox"
          className="mt-1 accent-teal"
          checked={draft.identity.adult_confirmed}
          onChange={(event) =>
            update((current) => ({
              ...current,
              identity: {
                ...current.identity,
                adult_confirmed: event.target.checked,
              },
            }))
          }
        />
        <span>
          <span className="block text-sm font-medium">I am 18 or older</span>
          <span className="mt-1 block text-sm leading-5 text-white/80">
            GhostRep is for adults. We do not ask for a birth date, and age is
            not used to judge ability.
          </span>
        </span>
      </label>
      <ChoiceGroup
        label="Age range"
        optional
        hint="Your age range can help tailor training recommendations. Your experience and abilities matter more than age alone."
      >
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {AGE_RANGES.map((range) => (
            <Choice
              key={range.id}
              selected={draft.identity.age_range === range.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  identity: {
                    ...current.identity,
                    age_range:
                      current.identity.age_range === range.id ? "" : range.id,
                  },
                }))
              }
            >
              {range.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
    </div>
  );
}

function Goals({ draft, update }: StepProps) {
  return (
    <div className="space-y-6">
      <ChoiceGroup label="Primary goal">
        <div className="grid gap-2 sm:grid-cols-2">
          {PRIMARY_GOALS.map((goal) => (
            <Choice
              key={goal.id}
              selected={draft.goals.primary === goal.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  goals: {
                    ...current.goals,
                    primary: goal.id,
                    secondary:
                      current.goals.secondary === goal.id
                        ? ""
                        : current.goals.secondary,
                  },
                }))
              }
            >
              <span className="block font-medium">{goal.label}</span>
              <span className="mt-1 block text-sm text-white/75">
                {goal.hint}
              </span>
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup label="Secondary goal" optional>
        <div className="flex flex-wrap gap-2">
          {PRIMARY_GOALS.filter((goal) => goal.id !== draft.goals.primary).map(
            (goal) => (
              <Choice
                key={goal.id}
                selected={draft.goals.secondary === goal.id}
                onClick={() =>
                  update((current) => ({
                    ...current,
                    goals: {
                      ...current.goals,
                      secondary:
                        current.goals.secondary === goal.id ? "" : goal.id,
                    },
                  }))
                }
              >
                {goal.label}
              </Choice>
            ),
          )}
        </div>
      </ChoiceGroup>
      <ChoiceGroup
        label="Training focus"
        hint="Choose how you want to begin your training week."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Choice
            selected={draft.goals.training_focus !== "lower_body"}
            onClick={() =>
              update((current) => ({
                ...current,
                goals: { ...current.goals, training_focus: "balanced" },
              }))
            }
          >
            <span className="block font-medium">Balanced</span>
            <span className="mt-1 block text-sm text-white/80">
              Spread your emphasis across the week using your preferred split.
            </span>
          </Choice>
          <Choice
            selected={draft.goals.training_focus === "lower_body"}
            onClick={() =>
              update((current) => ({
                ...current,
                goals: { ...current.goals, training_focus: "lower_body" },
              }))
            }
          >
            <span className="block font-medium">Lower body</span>
            <span className="mt-1 block text-sm text-white/80">
              Begin with a lower-body session. Barbell squats lead when your
              equipment and movement preferences support them.
            </span>
          </Choice>
        </div>
        {draft.goals.training_focus === "lower_body" && !hasBarbell(draft) && (
          <p className="mt-3 text-sm leading-6 text-white/80">
            Your equipment list doesn’t include a barbell. Add it in Equipment
            if you use one; otherwise your plan will use an available squat
            variation.
          </p>
        )}
      </ChoiceGroup>
      {showMusclePriority(draft) &&
        draft.goals.training_focus !== "lower_body" && (
          <ChoiceGroup
            label="Priority areas"
            hint="Choose up to 3 areas. Deselect one to add another. Balanced across the week replaces individual choices; your split still sets each session’s focus."
          >
            <div className="flex flex-wrap gap-2">
              <Choice
                selected={draft.goals.priority_muscles.includes("full_body")}
                onClick={() =>
                  update((current) => ({
                    ...current,
                    goals: {
                      ...current.goals,
                      priority_muscles: toggleMuscle(
                        current.goals.priority_muscles,
                        "full_body",
                      ),
                    },
                  }))
                }
              >
                Balanced across the week
              </Choice>
              {MUSCLES.map((muscle) => (
                <Choice
                  key={muscle}
                  selected={draft.goals.priority_muscles.includes(muscle)}
                  disabled={!draft.goals.priority_muscles.includes(muscle) && draft.goals.priority_muscles.filter(item => item !== "full_body").length >= 3}
                  onClick={() =>
                    update((current) => ({
                      ...current,
                      goals: {
                        ...current.goals,
                        priority_muscles: toggleMuscle(
                          current.goals.priority_muscles,
                          muscle,
                        ),
                      },
                    }))
                  }
                >
                  {labelFor(muscle)}
                </Choice>
              ))}
            </div>
          </ChoiceGroup>
        )}
      {showSport(draft) && (
        <Field label="Sport to prioritize" optional>
          <input
            className={inputClass}
            value={draft.preferences.sport}
            onChange={(event) =>
              update((current) => ({
                ...current,
                preferences: {
                  ...current.preferences,
                  sport: event.target.value,
                },
              }))
            }
          />
        </Field>
      )}
      <ChoiceGroup label="Specific ambitions" optional>
        <div className="flex flex-wrap gap-2">
          {AMBITIONS.map((item) => (
            <Choice
              key={item.id}
              selected={draft.goals.ambitions.includes(item.id)}
              onClick={() =>
                update((current) => ({
                  ...current,
                  goals: {
                    ...current.goals,
                    ambitions: toggleList(current.goals.ambitions, item.id),
                  },
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <Field label="Personal objective" optional>
        <input
          className={inputClass}
          value={draft.goals.personal_objective}
          onChange={(event) =>
            update((current) => ({
              ...current,
              goals: {
                ...current.goals,
                personal_objective: event.target.value,
              },
            }))
          }
        />
      </Field>
      <ChoiceGroup
        label="Planning horizon"
        optional
        hint="This sets the block length. It is not a promise of a physical result."
      >
        <div className="flex flex-wrap gap-2">
          {["4", "8", "12", "ongoing"].map((weeks) => (
            <Choice
              key={weeks}
              selected={draft.goals.planning_horizon_weeks === weeks}
              onClick={() =>
                update((current) => ({
                  ...current,
                  goals: {
                    ...current.goals,
                    planning_horizon_weeks:
                      current.goals.planning_horizon_weeks === weeks
                        ? ""
                        : weeks,
                  },
                }))
              }
            >
              {weeks === "ongoing" ? "Ongoing" : `${weeks} weeks`}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
    </div>
  );
}

function Experience({ draft, update }: StepProps) {
  return (
    <div className="space-y-6">
      <ChoiceGroup label="General experience">
        <div className="grid gap-2">
          {EXPERIENCE_LEVELS.map((level) => (
            <Choice
              key={level.id}
              selected={draft.experience.level === level.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  experience: { ...current.experience, level: level.id },
                }))
              }
            >
              <span className="block font-medium">{level.label}</span>
              <span className="mt-1 block text-sm text-white/75">
                {level.hint}
              </span>
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup label="Training history" optional>
        <div className="flex flex-wrap gap-2">
          {HISTORIES.map((item) => (
            <Choice
              key={item.id}
              selected={draft.experience.training_history === item.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  experience: {
                    ...current.experience,
                    training_history:
                      current.experience.training_history === item.id
                        ? ""
                        : item.id,
                  },
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup label="Current consistency" optional>
        <div className="flex flex-wrap gap-2">
          {CONSISTENCY.map((item) => (
            <Choice
              key={item.id}
              selected={draft.experience.consistency === item.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  experience: {
                    ...current.experience,
                    consistency:
                      current.experience.consistency === item.id ? "" : item.id,
                  },
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup label="Current routine" optional>
        <div className="flex flex-wrap gap-2">
          {SPLITS.map((item) => (
            <Choice
              key={item.id}
              selected={draft.experience.current_split === item.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  experience: {
                    ...current.experience,
                    current_split:
                      current.experience.current_split === item.id
                        ? ""
                        : item.id,
                  },
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
    </div>
  );
}

function Preferences({ draft, update }: StepProps) {
  return (
    <div className="space-y-6">
      <ChoiceGroup
        label="Weekly workout frequency"
        hint="How many GhostRep sessions you want, separate from other sports."
      >
        <div className="grid grid-cols-7 gap-2">
          {[1, 2, 3, 4, 5, 6, 7].map((count) => (
            <Choice
              key={count}
              selected={draft.schedule.days_per_week === count}
              onClick={() =>
                update((current) => ({
                  ...current,
                  schedule: { ...current.schedule, days_per_week: count },
                }))
              }
            >
              {count}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup
        label="Preferred training days"
        optional
        hint="Optional. These are preferences, so the count does not have to match your weekly frequency."
      >
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
          {DAYS.map((day) => (
            <Choice
              key={day}
              selected={draft.schedule.preferred_days.includes(day)}
              onClick={() =>
                update((current) => ({
                  ...current,
                  schedule: {
                    ...current.schedule,
                    preferred_days: toggleList(
                      current.schedule.preferred_days,
                      day,
                    ),
                  },
                }))
              }
            >
              {day.slice(0, 3)}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup label="Workout duration">
        <div className="flex flex-wrap gap-2">
          {DURATION_BANDS.map((band) => (
            <Choice
              key={band.id}
              selected={draft.schedule.duration_band === band.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  schedule: { ...current.schedule, duration_band: band.id },
                }))
              }
            >
              {band.label}
            </Choice>
          ))}
        </div>
        {draft.schedule.duration_band === "custom" && (
          <input
            className={cn(inputClass, "mt-3")}
            inputMode="numeric"
            placeholder="Minutes"
            value={draft.schedule.custom_minutes}
            onChange={(event) =>
              update((current) => ({
                ...current,
                schedule: {
                  ...current.schedule,
                  custom_minutes: event.target.value,
                },
              }))
            }
          />
        )}
      </ChoiceGroup>
      <ChoiceGroup label="Training style" optional>
        <div className="flex flex-wrap gap-2">
          {STYLES.map((style) => (
            <Choice
              key={style.id}
              selected={draft.preferences.training_style === style.id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  preferences: {
                    ...current.preferences,
                    training_style: style.id,
                  },
                }))
              }
            >
              {style.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      {showTechnicalLifts(draft) && (
        <ChoiceGroup
          label="Preferred split"
          optional
          hint="This sets each session’s focus. Balanced development can still come from the whole week."
        >
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {PREFERRED_SPLITS.map((split) => (
              <Choice
                key={split.id}
                selected={draft.preferences.preferred_split === split.id}
                onClick={() =>
                  update((current) => ({
                    ...current,
                    preferences: {
                      ...current.preferences,
                      preferred_split: split.id,
                    },
                  }))
                }
              >
                <span className="block font-medium">{split.label}</span>
                <span className="mt-1 block text-sm text-white/80">
                  {split.hint}
                </span>
              </Choice>
            ))}
          </div>
          {draft.preferences.preferred_split === "push_pull_legs" &&
            draft.schedule.days_per_week > 0 &&
            draft.schedule.days_per_week < 3 && (
              <p className="text-sm text-white/80">
                Push / pull / legs needs at least three days. The plan will use
                a full-body session instead.
              </p>
            )}
        </ChoiceGroup>
      )}
      {showTechnicalLifts(draft) && (
        <ChoiceGroup
          label="Intensity preference"
          optional
          hint="Willingness to work hard is not the same as readiness."
        >
          <div className="grid grid-cols-2 gap-2">
            {INTENSITIES.map((item) => (
              <Choice
                key={item.id}
                selected={draft.preferences.intensity === item.id}
                onClick={() =>
                  update((current) => ({
                    ...current,
                    preferences: {
                      ...current.preferences,
                      intensity:
                        current.preferences.intensity === item.id
                          ? ""
                          : item.id,
                    },
                  }))
                }
              >
                {item.label}
              </Choice>
            ))}
          </div>
        </ChoiceGroup>
      )}
      <ChoiceGroup
        label="Other physical activity"
        optional
        hint="Frequent lower-body sports reduce extra squat volume."
      >
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {ACTIVITIES.map((activity) => {
            const selected = draft.preferences.other_activities.find(
              (item) => item.activity === activity,
            );
            return (
              <Choice
                key={activity}
                selected={Boolean(selected)}
                onClick={() =>
                  update((current) => ({
                    ...current,
                    preferences: {
                      ...current.preferences,
                      other_activities: selected
                        ? current.preferences.other_activities.filter(
                            (item) => item.activity !== activity,
                          )
                        : [
                            ...current.preferences.other_activities,
                            { activity, sessions_per_week: 1 },
                          ],
                    },
                  }))
                }
              >
                {labelFor(activity)}
              </Choice>
            );
          })}
        </div>
        {draft.preferences.other_activities.length > 0 && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {draft.preferences.other_activities.map((item) => (
              <label key={item.activity} className="text-sm text-white/75">
                {labelFor(item.activity)} / week
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-transparent px-2 py-1 text-white"
                  type="number"
                  min={1}
                  max={14}
                  value={item.sessions_per_week}
                  onChange={(event) =>
                    update((current) => ({
                      ...current,
                      preferences: {
                        ...current.preferences,
                        other_activities:
                          current.preferences.other_activities.map((entry) =>
                            entry.activity === item.activity
                              ? {
                                  ...entry,
                                  sessions_per_week: Number(event.target.value),
                                }
                              : entry,
                          ),
                      },
                    }))
                  }
                />
              </label>
            ))}
          </div>
        )}
      </ChoiceGroup>
      <ExercisePicker draft={draft} update={update} />
    </div>
  );
}

function ExercisePicker({ draft, update }: StepProps) {
  const [search, setSearch] = useState("");
  const matches = CATALOG_CHOICES.filter((item) =>
    item.label.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div>
      <p className="text-sm font-medium">
        Exercises you enjoy <span className="text-white/75">· optional</span>
      </p>
      <p className="mt-1 text-sm text-white/75">
        These are preferences. Anything you mark to leave out on the next step
        is never programmed.
      </p>
      <input
        className={cn(inputClass, "mt-3")}
        placeholder="Search exercises"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {matches.map((item) => (
          <Choice
            key={item.id}
            selected={draft.preferences.enjoyed_exercises.includes(item.id)}
            onClick={() =>
              update((current) => ({
                ...current,
                preferences: {
                  ...current.preferences,
                  enjoyed_exercises: toggleList(
                    current.preferences.enjoyed_exercises,
                    item.id,
                  ),
                },
                considerations: {
                  ...current.considerations,
                  avoided_exercises:
                    current.considerations.avoided_exercises.filter(
                      (id) => id !== item.id,
                    ),
                },
              }))
            }
          >
            {item.label}
          </Choice>
        ))}
      </div>
    </div>
  );
}

function SquatLoad({ draft, update }: StepProps) {
  const unit = draft.identity.preferred_weight_unit;
  return (
    <div>
      <p className="text-sm font-medium">
        Barbell squat working set{" "}
        <span className="text-white/75">· optional</span>
      </p>
      <p className="mt-1 text-sm text-white/75">
        A typical weight you already use, not a one-rep max. GhostRep will not
        raise it.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Field label={`Weight (${unit})`}>
          <input
            className={inputClass}
            inputMode="decimal"
            value={draft.experience.squat_weight}
            onChange={(event) =>
              update((current) => ({
                ...current,
                experience: {
                  ...current.experience,
                  squat_weight: event.target.value,
                },
              }))
            }
          />
        </Field>
        <Field label="Reps">
          <input
            className={inputClass}
            inputMode="numeric"
            value={draft.experience.squat_reps}
            onChange={(event) =>
              update((current) => ({
                ...current,
                experience: {
                  ...current.experience,
                  squat_reps: event.target.value,
                },
              }))
            }
          />
        </Field>
        <Field label="Sets">
          <input
            className={inputClass}
            inputMode="numeric"
            value={draft.experience.squat_sets}
            onChange={(event) =>
              update((current) => ({
                ...current,
                experience: {
                  ...current.experience,
                  squat_sets: event.target.value,
                },
              }))
            }
          />
        </Field>
      </div>
    </div>
  );
}

function EquipmentStep({
  draft,
  update,
  query,
  setQuery,
}: StepProps & { query: string; setQuery: (value: string) => void }) {
  const mismatch = equipmentMismatch(draft);
  return (
    <div className="space-y-6">
      {mismatch && (
        <p className="rounded-2xl border border-amber/30 bg-amber/5 p-3 text-sm text-amber">
          {mismatch}
        </p>
      )}
      <ChoiceGroup
        label="Equipment presets"
        hint="A preset fills the list. You can remove anything you do not have."
      >
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            ["full_gym", "Full commercial gym"],
            ["basic_home", "Basic home gym"],
            ["minimal", "Minimal equipment"],
            ["bodyweight", "Bodyweight only"],
          ].map(([id, label]) => (
            <Choice
              key={id}
              selected={draft.equipment.preset === id}
              onClick={() =>
                update((current) => ({
                  ...current,
                  equipment: { preset: id, available: PRESETS[id] },
                }))
              }
            >
              {label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <Field label="Search equipment">
        <input
          className={inputClass}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </Field>
      {EQUIPMENT_GROUPS.map((group) => {
        const items = group.items.filter((item) =>
          item.replaceAll("_", " ").includes(query.toLowerCase()),
        );
        if (!items.length) return null;
        return (
          <ChoiceGroup key={group.label} label={group.label}>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {items.map((item) => (
                <Choice
                  key={item}
                  selected={draft.equipment.available.includes(item)}
                  onClick={() =>
                    update((current) => ({
                      ...current,
                      equipment: {
                        preset: current.equipment.preset,
                        available: toggleList(
                          current.equipment.available,
                          item,
                        ),
                      },
                    }))
                  }
                >
                  {labelFor(item)}
                </Choice>
              ))}
            </div>
          </ChoiceGroup>
        );
      })}
      <ChoiceGroup
        label="Movements you prefer to avoid"
        optional
        hint="These are preferences, not a diagnosis. Matching exercises are left out of the plan."
      >
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {RESTRICTIONS.map((item) => (
            <Choice
              key={item.id}
              selected={draft.considerations.movement_restrictions.includes(
                item.id,
              )}
              onClick={() =>
                update((current) => ({
                  ...current,
                  considerations: {
                    ...current.considerations,
                    movement_restrictions: toggleList(
                      current.considerations.movement_restrictions,
                      item.id,
                    ),
                  },
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      <ChoiceGroup label="Exercises to leave out" optional>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {CATALOG_CHOICES.map((item) => (
            <Choice
              key={item.id}
              selected={draft.considerations.avoided_exercises.includes(
                item.id,
              )}
              onClick={() =>
                update((current) => ({
                  ...current,
                  considerations: {
                    ...current.considerations,
                    avoided_exercises: toggleList(
                      current.considerations.avoided_exercises,
                      item.id,
                    ),
                  },
                }))
              }
            >
              {item.label}
            </Choice>
          ))}
        </div>
      </ChoiceGroup>
      {showTechnicalLifts(draft) && hasBarbell(draft) && (
        <ChoiceGroup
          label="Barbell squat familiarity"
          optional
          hint="Asked only when a barbell is available and you are past the beginner stage."
        >
          <div className="grid gap-2 sm:grid-cols-3">
            {[
              ["new", "New to this"],
              ["some", "Some experience"],
              ["confident", "Confident"],
            ].map(([id, label]) => (
              <Choice
                key={id}
                selected={
                  draft.experience.exercise_familiarity.barbell_squat === id
                }
                onClick={() =>
                  update((current) => ({
                    ...current,
                    experience: {
                      ...current.experience,
                      exercise_familiarity: {
                        ...current.experience.exercise_familiarity,
                        barbell_squat:
                          current.experience.exercise_familiarity
                            .barbell_squat === id
                            ? ""
                            : id,
                      },
                    },
                  }))
                }
              >
                {label}
              </Choice>
            ))}
          </div>
        </ChoiceGroup>
      )}
      {showSquatLoad(draft) && <SquatLoad draft={draft} update={update} />}
      <Field
        label="Anything else to work around"
        optional
        hint="Share only what GhostRep needs in order to skip a movement. This is not a medical record, and GhostRep will not diagnose or prescribe rehab."
      >
        <textarea
          className={cn(inputClass, "min-h-24")}
          value={draft.considerations.limitation_note}
          onChange={(event) =>
            update((current) => ({
              ...current,
              considerations: {
                ...current.considerations,
                limitation_note: event.target.value,
              },
            }))
          }
        />
      </Field>
    </div>
  );
}

function Review({
  draft,
  summary,
  hasPlan,
  onEdit,
}: {
  draft: AssessmentDraft;
  summary: string;
  hasPlan: boolean;
  onEdit: (step: number) => void;
}) {
  const payload = toProfilePayload(draft);
  const sections = [
    [
      "Training focus",
      draft.goals.training_focus === "lower_body"
        ? "Lower body · open with your lower-body session"
        : "Balanced across the week",
      1,
    ],
    [
      "Your goals",
      `${labelFor(draft.goals.primary)} · ${labelFor(draft.goals.secondary)} · ${draft.goals.training_focus === "lower_body" ? "Lower-body emphasis" : (payload.assessment.goals.priority_muscles || []).map((item) => (item === "full_body" ? "Balanced across the week" : labelFor(item))).join(", ")}`,
      1,
    ],
    [
      "Your experience",
      `${labelFor(draft.experience.level)} · ${labelFor(draft.experience.current_split)}`,
      2,
    ],
    [
      "Your schedule",
      `${draft.schedule.days_per_week > 0 ? `${draft.schedule.days_per_week} days` : "Frequency not specified"} · ${draft.schedule.preferred_days.join(", ") || "days flexible"} · ${draft.schedule.duration_band ? `${payload.session_duration_minutes} min` : "duration not specified"}`,
      3,
    ],
    [
      "Your preferences",
      `${labelFor(draft.preferences.training_style)} · ${labelFor(draft.preferences.preferred_split)}`,
      3,
    ],
    [
      "Your equipment",
      draft.equipment.available.map(labelFor).join(", ") || "Not specified",
      4,
    ],
    [
      "Your considerations",
      [
        ...draft.considerations.avoided_exercises.map(labelFor),
        ...draft.considerations.movement_restrictions.map(labelFor),
        draft.considerations.limitation_note,
      ]
        .filter(Boolean)
        .join(", ") || "None specified",
      4,
    ],
  ] as const;
  return (
    <div className="space-y-4">
      <p className="text-base leading-7 text-white/85">{summary}</p>
      {sections.map(([title, body, step]) => (
        <div
          key={title}
          className="flex items-start justify-between gap-4 rounded-2xl border border-white/8 px-4 py-3"
        >
          <div>
            <p className="text-sm uppercase tracking-wider text-white/80">
              {title}
            </p>
            <p className="mt-1 text-sm">{body}</p>
          </div>
          <button
            type="button"
            className="inline-flex min-h-11 items-center px-2 text-sm font-medium text-teal"
            onClick={() => onEdit(step)}
          >
            Edit
          </button>
        </div>
      ))}
      {hasPlan && (
        <p className="text-sm leading-6 text-white/80">
          Your accepted plan stays active until you accept a new week. Logged
          workouts stay saved.
        </p>
      )}
      <p className="text-sm leading-6 text-white/80">
        Next: review each session, then activate the week.
      </p>
    </div>
  );
}

type StepProps = {
  draft: AssessmentDraft;
  update: (patch: (current: AssessmentDraft) => AssessmentDraft) => void;
};

function ChoiceGroup({
  label,
  hint,
  optional,
  children,
}: {
  label: string;
  hint?: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">
        {label} {optional && <span className="text-white/80">· optional</span>}
      </legend>
      {hint && <p className="mt-1 text-sm text-white/80">{hint}</p>}
      <div className="mt-3">{children}</div>
    </fieldset>
  );
}

function Field({
  label,
  hint,
  optional,
  children,
}: {
  label: string;
  hint?: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium">
        {label} {optional && <span className="text-white/80">· optional</span>}
      </span>
      {hint && <span className="mt-1 block text-sm text-white/80">{hint}</span>}
      <span className="mt-2 block">{children}</span>
    </label>
  );
}

function Choice({
  selected,
  disabled = false,
  children,
  onClick,
}: {
  selected: boolean;
  disabled?: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "min-h-11 rounded-2xl border px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal",
        selected
          ? "border-teal bg-teal/12 text-white"
          : "border-white/10 bg-white/4 text-white/80 hover:border-white/25",
      )}
    >
      {children}
    </button>
  );
}

function toggleList(values: string[], id: string): string[] {
  return values.includes(id)
    ? values.filter((item) => item !== id)
    : [...values, id];
}

const inputClass =
  "min-h-11 w-full rounded-xl border border-white/10 bg-transparent px-3 py-2 text-sm outline-none focus:border-teal";
