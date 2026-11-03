"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import Link from "@/components/ui/Link";
import { api } from "@/lib/api";
import { buttonClass } from "@/lib/buttonStyles";
import { captureHref } from "@/lib/capture";
import {
  displayLoad,
  formatLoad,
  isTimedExercise,
  loadToKg,
  unitFromProfile,
  type WeightUnit,
} from "@/lib/training";
import { ArrowLeft, Check, Video } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type Recording = Awaited<ReturnType<typeof api.getRecording>>;
const TERMINAL = new Set(["SAVED", "COMPLETED", "FAILED", "LOGGED"]);
const inputClass =
  "mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-black/30 px-3 py-3 font-mono text-white";

export default function RecordingPage() {
  const { id } = useParams<{ id: string }>();
  const [recording, setRecording] = useState<Recording | null>(null);
  const [unit, setUnit] = useState<WeightUnit>("kg");
  const [reps, setReps] = useState("");
  const [load, setLoad] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const [saved, profile] = await Promise.all([
          api.getRecording(id),
          api.getProfile().catch(() => null),
        ]);
        if (cancelled) return;
        const preferred = unitFromProfile(profile);
        setRecording(saved);
        setUnit(preferred);
        setReps(
          saved.completed_reps == null ? "" : String(saved.completed_reps),
        );
        setLoad(
          saved.load_kg == null
            ? ""
            : String(displayLoad(saved.load_kg, preferred)),
        );
        setError(null);
        if (!TERMINAL.has(saved.processing_status))
          timer = setTimeout(refresh, 1500);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load this recording.",
          );
      }
    }
    void refresh();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id, retry]);

  async function logSet() {
    if (!recording?.set_index) return;
    const count = Number(reps);
    const weight = load.trim() ? Number(load) : null;
    if (
      !reps.trim() ||
      !Number.isInteger(count) ||
      count < 0 ||
      count > 200 ||
      (weight != null && (!Number.isFinite(weight) || weight < 0))
    ) {
      setError(
        "Enter a whole number from 0 to 200 and a valid load, or leave the load blank for bodyweight.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.logSet(recording.session_id, {
        exercise_id: recording.exercise_id,
        set_index: recording.set_index,
        completed_reps: count,
        load_kg: weight == null ? null : loadToKg(weight, unit),
        target_reps: recording.target_reps,
      });
      setRecording(await api.getRecording(id));
      setNotice(
        count > 0
          ? "Set logged. Your video is attached to the same set."
          : "Set updated. Zero reps won’t count toward workout totals.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log this set.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteVideo() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.deleteMedia(id);
      setRecording(await api.getRecording(id));
      setConfirmDelete(false);
      setNotice("Video deleted. Your logged set is still saved.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not delete this video.",
      );
    } finally {
      setBusy(false);
    }
  }

  const open =
    recording?.session_status === "active" ||
    recording?.session_status === "paused";
  const processing = Boolean(
    recording && !TERMINAL.has(recording.processing_status),
  );
  const seconds = recording ? isTimedExercise(recording.exercise_id) : false;
  const back = recording?.plan_id
    ? `/workouts/${recording.plan_id}#exercise-${recording.exercise_id}`
    : "/history";

  return (
    <AppShell>
      <Link
        href={back}
        className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-teal"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        {recording?.plan_id ? "Back to workout" : "Training history"}
      </Link>
      {!recording && !error && (
        <p role="status" className="mt-6 text-white/85">
          Loading your recording…
        </p>
      )}
      {recording && (
        <>
          <p className="mt-5 text-sm font-medium text-teal">Your set video</p>
          <h1 className="mt-2 text-3xl font-semibold">
            {recording.exercise_name}
            {recording.set_index ? ` · set ${recording.set_index}` : ""}
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-white/85">
            Replay your movement and keep a record of your progress.
          </p>
          <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Card className="overflow-hidden p-4 sm:p-5">
              <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-2xl bg-black">
                {recording.has_video && !mediaError ? (
                  <video
                    src={api.mediaUrl(recording.id)}
                    controls
                    playsInline
                    preload="metadata"
                    className="h-full w-full object-contain"
                    aria-label={`${recording.exercise_name} set ${recording.set_index || ""} replay`}
                    onError={() => setMediaError(true)}
                  />
                ) : (
                  <div className="px-6 text-center">
                    <Video
                      className="mx-auto mb-3 h-9 w-9 text-teal"
                      aria-hidden
                    />
                    <p className="text-white/85">
                      {processing
                        ? "Preparing your video for replay…"
                        : recording.processing_status === "FAILED"
                          ? "This video couldn’t be prepared."
                          : mediaError
                            ? "The video could not be played."
                            : "This video has been deleted."}
                    </p>
                    <p className="mt-2 text-sm text-white/75">
                      {processing
                        ? "You can return to your workout while it saves."
                        : "Your workout log is kept separately."}
                    </p>
                  </div>
                )}
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-white/80">
                <span className="inline-flex items-center gap-2">
                  {!processing && recording.has_video && (
                    <Check className="h-4 w-4 text-teal" aria-hidden />
                  )}
                  {processing
                    ? "Saving video"
                    : recording.has_video
                      ? "Saved for replay"
                      : "Video unavailable"}
                  {recording.duration_seconds
                    ? ` · ${Math.round(recording.duration_seconds)}s`
                    : ""}
                </span>
                <span>
                  {recording.created_at
                    ? new Date(recording.created_at).toLocaleDateString(
                        undefined,
                        { month: "short", day: "numeric", year: "numeric" },
                      )
                    : ""}
                </span>
              </div>
              {recording.processing_status === "FAILED" && (
                <div className="mt-4">
                  <ActionFeedback kind="error">
                    We couldn’t prepare this clip. Delete it below, then try
                    another MP4, MOV, M4V, or WebM video.
                  </ActionFeedback>
                </div>
              )}
            </Card>
            <Card className="p-5">
              <h2 className="text-xl font-medium">Your set log</h2>
              <p className="mt-2 text-sm leading-6 text-white/85">
                {(recording.completed_reps ?? 0) > 0
                  ? `${recording.completed_reps}${seconds ? " seconds" : " reps"} logged${recording.load_kg != null ? ` · ${formatLoad(recording.load_kg, unit)}` : ""}.`
                  : "Your video is saved. This set won’t count as completed until you log what you did."}
              </p>
              {open && !processing && (
                <>
                  <div className="mt-5 grid grid-cols-2 gap-3">
                    <label className="text-sm text-white/85">
                      {seconds ? "Seconds completed" : "Reps completed"}
                      <input
                        inputMode="numeric"
                        value={reps}
                        className={inputClass}
                        disabled={busy}
                        onChange={(event) => setReps(event.target.value)}
                      />
                    </label>
                    <label className="text-sm text-white/85">
                      Load ({unit}, optional)
                      <input
                        inputMode="decimal"
                        value={load}
                        placeholder="Bodyweight"
                        className={inputClass}
                        disabled={busy}
                        onChange={(event) => setLoad(event.target.value)}
                      />
                    </label>
                  </div>
                  <Button
                    className="mt-4"
                    onClick={logSet}
                    loading={busy}
                    loadingLabel="Saving…"
                    disabled={busy || !reps.trim()}
                  >
                    {recording.completed_reps == null
                      ? "Log this set"
                      : "Update set log"}
                  </Button>
                </>
              )}
              {!open && (
                <p className="mt-3 text-sm text-white/75">
                  This workout is closed. Your saved log is read-only.
                </p>
              )}
              <Link
                href={back}
                className={buttonClass("secondary", "mt-4 w-full")}
              >
                {recording.plan_id && open
                  ? "Continue workout"
                  : "Back to training history"}
              </Link>
              {!recording.has_video && open && !processing && (
                <Link
                  href={captureHref({
                    planId: recording.plan_id,
                    sessionId: recording.session_id,
                    exerciseId: recording.exercise_id,
                    setIndex: recording.set_index,
                  })}
                  className={buttonClass("ghost", "mt-2 w-full")}
                >
                  Record another clip
                </Link>
              )}
            </Card>
          </div>
          {!processing &&
            (recording.has_video ||
              recording.processing_status === "FAILED") && (
              <div className="mt-5 max-w-2xl rounded-2xl border border-white/10 p-4">
                {confirmDelete ? (
                  <>
                    <p className="text-sm text-white/85">
                      Delete this video permanently? Reps, weight, and workout
                      totals will stay saved.
                    </p>
                    <div className="mt-3 flex gap-3">
                      <Button
                        variant="secondary"
                        loading={busy}
                        loadingLabel="Deleting…"
                        disabled={busy}
                        onClick={deleteVideo}
                      >
                        Delete video
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={busy}
                        onClick={() => setConfirmDelete(false)}
                      >
                        Keep video
                      </Button>
                    </div>
                  </>
                ) : (
                  <Button
                    variant="ghost"
                    onClick={() => setConfirmDelete(true)}
                  >
                    Delete video
                  </Button>
                )}
              </div>
            )}
        </>
      )}
      {notice && (
        <div className="mt-4">
          <ActionFeedback kind="success">{notice}</ActionFeedback>
        </div>
      )}
      {error && (
        <div className="mt-4">
          <ActionFeedback kind="error">
            <p>{error}</p>
            {!recording && (
              <Button
                variant="secondary"
                className="mt-3"
                onClick={() => setRetry((value) => value + 1)}
              >
                Try again
              </Button>
            )}
          </ActionFeedback>
        </div>
      )}
    </AppShell>
  );
}
