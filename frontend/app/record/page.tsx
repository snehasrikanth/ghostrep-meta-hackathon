"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, api, type MetaStatus } from "@/lib/api";
import {
  recordingHref,
  canRetryRecording,
  recordingMimeType,
  supportsAnalysis,
  type CaptureMode,
} from "@/lib/capture";
import {
  displayLoad,
  loadToKg,
  unitFromProfile,
  isTimedExercise,
  isSampleSet,
  type WeightUnit,
} from "@/lib/training";
import type { Analysis, RecordedSet, WorkoutExercise } from "@/lib/types";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Camera, Upload, Video } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

const MAX_SECONDS = 90;
const MIN_SECONDS = 3;
const MAX_MB = 80;
const EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm"];

const STAGES = [
  { id: "UPLOADED", label: "Uploading" },
  { id: "VALIDATING", label: "Checking the video" },
  { id: "PREPROCESSING", label: "Preparing frames" },
  { id: "ESTIMATING_POSE", label: "Tracking body landmarks" },
  { id: "DETECTING_REPS", label: "Finding squat reps" },
  { id: "SEGMENTING", label: "Building your movement outline" },
  { id: "COMPUTING_METRICS", label: "Measuring each rep" },
  { id: "GENERATING_COACHING", label: "Building coaching" },
  { id: "COMPLETED", label: "Done" },
];

type FileCheck = { ok: boolean; message: string; seconds?: number };
type CaptureExercise = {
  id: string;
  name: string;
  video_analysis: boolean;
  target_reps?: number;
  suggested_load_kg?: number | null;
  rest_seconds?: number;
};

function saveRecordingRestTimer(sessionId: string, label: string, total: number) {
  localStorage.setItem(`ghostrep.rest.${sessionId}`, JSON.stringify({
    label, total, endsAt: Date.now() + total * 1000,
  }));
}

async function checkFile(file: File): Promise<FileCheck> {
  const name = file.name.toLowerCase();
  if (
    !EXTENSIONS.some((ext) => name.endsWith(ext)) &&
    !file.type.startsWith("video/")
  ) {
    return { ok: false, message: "Choose an MP4, MOV, M4V, or WEBM video." };
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    return {
      ok: false,
      message: `This file is ${(file.size / 1024 / 1024).toFixed(0)} MB. The limit is ${MAX_MB} MB; trim the clip to the set.`,
    };
  }
  const seconds = await new Promise<number | null>((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(video.duration) ? video.duration : null);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    video.src = url;
  });
  if (seconds == null) {
    return {
      ok: true,
      message:
        "Your browser could not read the length of this file. The server will check it.",
    };
  }
  if (seconds > MAX_SECONDS) {
    return {
      ok: false,
      message: `This clip is ${seconds.toFixed(0)} s. Keep it under ${MAX_SECONDS} s, ideally 20–40 s covering one set.`,
      seconds,
    };
  }
  if (seconds < MIN_SECONDS) {
    return {
      ok: false,
      message: `This clip is ${seconds.toFixed(1)} s. Record the whole set, including standing before the first rep.`,
      seconds,
    };
  }
  return { ok: true, message: `${seconds.toFixed(1)} s video ready.`, seconds };
}

function cameraError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError")
    return "Camera access was blocked. Allow camera access in your browser settings, or upload a video instead.";
  if (name === "NotFoundError")
    return "No camera was found on this device. Upload a recorded video instead.";
  if (name === "NotReadableError")
    return "Another app is using the camera. Close it and try again.";
  return err instanceof Error ? err.message : "The camera could not start.";
}

function RecordInner() {
  const params = useSearchParams();
  const router = useRouter();
  const demo = params.get("demo") === "1";
  const planId = params.get("plan");
  const setIndex = params.get("set");
  const [exerciseId, setExerciseId] = useState(
    params.get("exercise") || "barbell_squat",
  );
  const [setNumber, setSetNumber] = useState(setIndex || "1");
  const [exercises, setExercises] = useState<CaptureExercise[]>([]);
  const [sessionSets, setSessionSets] = useState<RecordedSet[]>([]);
  const [contextReady, setContextReady] = useState(false);
  const [completed, setCompleted] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [attachedPlanId, setAttachedPlanId] = useState(planId);
  const [sessionId, setSessionId] = useState(params.get("session") || "");
  const [unit, setUnit] = useState<WeightUnit>("kg");
  const [load, setLoad] = useState("");
  const [reps, setReps] = useState(params.get("reps") || "");
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<FileCheck | null>(null);
  const [consent, setConsent] = useState(false);
  const [effort, setEffort] = useState(params.get("effort") || "");
  const [retryRecordingId, setRetryRecordingId] = useState(params.get("retry"));
  const [meta, setMeta] = useState<MetaStatus | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const loadProviderStatus = useCallback(async () => {
    setMetaLoading(true);
    setMetaError(null);
    try {
      setMeta(await api.metaStatus());
    } catch {
      setMeta(null);
      setMetaError("Video coaching availability could not be checked. Your clip and entries are still here. Try again, or save a replay without analysis.");
    } finally {
      setMetaLoading(false);
    }
  }, []);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (active) void loadProviderStatus(); });
    return () => { active = false; };
  }, [loadProviderStatus]);
  const [mode, setMode] = useState<CaptureMode>(
    params.get("mode") === "upload" ? "upload" : "camera",
  );
  const [cameraReady, setCameraReady] = useState(false);
  const [openingCamera, setOpeningCamera] = useState(false);
  const [facing, setFacing] = useState<"user" | "environment">("environment");
  const [previewUrl, setPreviewUrl] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [withOutlines, setWithOutlines] = useState(false);
  const [stageMessage, setStageMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unusable, setUnusable] = useState<{
    id: string;
    analysis: Analysis;
  } | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [openWorkout, setOpenWorkout] = useState<string | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const previewRef = useRef<HTMLVideoElement>(null);
  const fileUrlRef = useRef("");
  const chosenFileRef = useRef<File | null>(null);
  const startedAtRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getProfile().catch(() => null),
      api.currentSession().catch(() => ({ session: null })),
      planId ? api.getWorkout(planId).catch(() => null) : Promise.resolve(null),
      params.get("session")
        ? api.getSession(params.get("session")!)
        : Promise.resolve(null),
      api.catalog(),
    ])
      .then(
        async ([
          profile,
          current,
          requestedPlan,
          requestedSession,
          catalog,
        ]) => {
          const active = demo ? null :
            requestedSession ||
            (current.session && (!planId || current.session.plan_id === planId)
              ? current.session
              : null);
          const resolvedId = demo ? null : planId || active?.plan_id || null;
          const plan =
            (!demo && requestedPlan) ||
            (resolvedId
              ? await api.getWorkout(resolvedId).catch(() => null)
              : null);
          if (cancelled) return;
          setAttachedPlanId(resolvedId);
          if (!demo && current.session)
            setOpenWorkout(current.session.plan_name || "your open workout");
          if (!params.get("session") && active) setSessionId(active.id);
          setSessionSets(active?.sets || []);
          const preferred = unitFromProfile(profile);
          setUnit(preferred);
          const choices: CaptureExercise[] = demo
            ? catalog.exercises.filter(item => item.id === "barbell_squat")
            : plan?.exercises.map((item: WorkoutExercise) => ({
              ...item,
              id: item.exercise_id,
              name: item.name || item.exercise_id.replaceAll("_", " "),
              video_analysis: Boolean(item.video_analysis),
            })) || catalog.exercises;
          setExercises(choices);
          const exercise =
            choices.find((item) => item.id === params.get("exercise")) ||
            (params.get("exercise")
              ? null
              : choices.find((item) => item.id === "barbell_squat") ||
                choices[0]);
          if (!exercise) {
            setError(
              "This exercise is not in the selected workout. Choose an exercise below.",
            );
            setExerciseId("");
          } else setExerciseId(exercise.id);
          if (!params.get("set") && exercise) {
            const done =
              active?.sets.filter((item) => item.exercise_id === exercise.id) ||
              [];
            setSetNumber(
              String(
                Math.max(0, ...done.map((item) => item.set_index || 0)) + 1,
              ),
            );
          }
          const previous = active?.sets
            .toReversed()
            .find(
              (item) =>
                item.exercise_id === exercise?.id &&
                !isSampleSet(item) &&
                (item.completed_reps ?? 0) > 0,
            );
          const kg =
            params.get("load") != null
              ? Number(params.get("load"))
              : (exercise?.suggested_load_kg ?? previous?.load_kg);
          if (kg != null && Number.isFinite(kg))
            setLoad((value) => value || String(displayLoad(kg, preferred)));
          if (!params.get("reps") && exercise)
            setReps(
              (value) =>
                value ||
                ("target_reps" in exercise ? String(exercise.target_reps) : ""),
            );
          setContextReady(true);
        },
      )
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load your workout. Please reload this page.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [params, planId, demo]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const recorder = mediaRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.onstop = null;
        recorder.ondataavailable = null;
        recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current);
    };
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRef.current?.state === "recording") mediaRef.current.stop();
    setRecording(false);
  }, []);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => {
      const elapsed = Math.floor(
        (performance.now() - startedAtRef.current) / 1000,
      );
      setRecordSeconds(elapsed);
      // Leave room for the final encoder chunk under the server's 90-second limit.
      if (elapsed >= MAX_SECONDS - 1) stopRecording();
    }, 250);
    return () => window.clearInterval(timer);
  }, [recording, stopRecording]);

  async function chooseFile(next: File | null) {
    chosenFileRef.current = next;
    if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current);
    fileUrlRef.current = next ? URL.createObjectURL(next) : "";
    setPreviewUrl(fileUrlRef.current);
    setFile(next);
    setUnusable(null);
    setError(null);
    setCheck(null);
    if (next) {
      const result = await checkFile(next);
      if (chosenFileRef.current === next) setCheck(result);
    }
  }

  function closeCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (previewRef.current) previewRef.current.srcObject = null;
    setCameraReady(false);
  }

  async function openCamera(nextFacing = facing) {
    setError(null);
    setOpeningCamera(true);
    try {
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined"
      ) {
        throw new Error(
          "Camera recording is unavailable in this browser. Upload a video, or use a browser on localhost or HTTPS.",
        );
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: nextFacing },
          width: { ideal: 720 },
          height: { ideal: 1280 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: false,
      });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      closeCamera();
      streamRef.current = stream;
      if (!previewRef.current)
        throw new Error("Camera preview is not ready. Please try again.");
      previewRef.current.srcObject = stream;
      await previewRef.current.play();
      await chooseFile(null);
      setCameraReady(true);
      setFacing(nextFacing);
    } catch (err) {
      closeCamera();
      setError(cameraError(err));
    } finally {
      if (mountedRef.current) setOpeningCamera(false);
    }
  }

  function startRecording() {
    const stream = streamRef.current;
    if (!stream) return;
    const mime = recordingMimeType((value) =>
      MediaRecorder.isTypeSupported(value),
    );
    const recorder = new MediaRecorder(
      stream,
      mime ? { mimeType: mime } : undefined,
    );
    chunks.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.current.push(event.data);
    };
    recorder.onstop = () => {
      const type = recorder.mimeType || chunks.current[0]?.type || "video/webm";
      const blob = new Blob(chunks.current, { type });
      closeCamera();
      void chooseFile(
        new File(
          [blob],
          `${exerciseId}-set.${type.includes("mp4") ? "mp4" : "webm"}`,
          { type },
        ),
      );
    };
    recorder.start(250);
    mediaRef.current = recorder;
    setRecordSeconds(0);
    startedAtRef.current = performance.now();
    setRecording(true);
  }

  function changeMode(next: CaptureMode) {
    if (cameraReady) closeCamera();
    setMode(next);
  }

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    const session = await api.startSession(attachedPlanId || undefined);
    setSessionId(session.id);
    return session.id;
  }

  const existingClip = sessionSets.find(
    (item) =>
      item.exercise_id === exerciseId &&
      item.set_index === Number(setNumber) &&
      item.entry_source !== "manual" &&
      (item.has_video ||
        item.analysis_requested !== false ||
        item.processing_status !== "SAVED"),
  );
  const retryAuthorized = Boolean(existingClip && canRetryRecording(existingClip) && retryRecordingId === existingClip.id);

  async function submit(
    useDemo: boolean,
    analyze = supportsAnalysis(exerciseId),
  ) {
    setError(null);
    setUnusable(null);
    if (analyze && !useDemo && !consent) {
      setError("Confirm consent before anything is uploaded.");
      return;
    }
    if (!useDemo && (!file || !check?.ok)) {
      setError(check?.message || "Choose a video or record a set first.");
      return;
    }
    const loadValue = load.trim() ? Number(load) : null;
    if (loadValue != null && (!Number.isFinite(loadValue) || loadValue < 0)) {
      setError("Enter a valid load, or leave it blank for bodyweight.");
      return;
    }
    if (
      !contextReady ||
      !exerciseId ||
      !Number.isInteger(Number(setNumber)) ||
      Number(setNumber) < 1 ||
      Number(setNumber) > 100
    ) {
      setError("Choose an exercise and a set number between 1 and 100.");
      return;
    }
    if (
      !analyze &&
      completed.trim() &&
      (!Number.isInteger(Number(completed)) ||
        Number(completed) < 0 ||
        Number(completed) > 200)
    ) {
      setError(
        "Enter a whole number between 0 and 200, or leave completed reps blank to log later.",
      );
      return;
    }
    setAnalyzing(analyze);
    setWithOutlines(analyze && !useDemo && Boolean(meta?.sam_ready));
    setStage("UPLOADED");
    setStageMessage(null);
    try {
      const form = new FormData();
      if (!useDemo) form.append("session_id", await ensureSession());
      form.append("exercise_id", exerciseId);
      form.append("analyze", String(analyze));
      form.append("clear_load", String(!load.trim()));
      form.append("consent", "true");
      form.append("demo", useDemo ? "true" : "false");
      form.append(
        "approve_meta_spend",
        analyze && !useDemo && consent && meta?.coaching_ready
          ? "true"
          : "false",
      );
      form.append(
        "approve_sam_spend",
        analyze && !useDemo && consent && meta?.sam_ready ? "true" : "false",
      );
      if (reps) form.append("target_reps", reps);
      if (effort) form.append("reported_rpe", effort);
      if (loadValue != null)
        form.append("load_kg", String(loadToKg(loadValue, unit)));
      form.append("set_index", setNumber);
      if (!useDemo && retryAuthorized && existingClip) form.append("replace_failed_recording_id", existingClip.id);
      if (!analyze && completed.trim())
        form.append("completed_reps", completed);
      if (!useDemo && file) form.append("file", file);
      const rec = await api.uploadVideo(form);
      if (!mountedRef.current) return;
      if (!analyze) {
        let saved = rec;
        while (!["SAVED", "FAILED"].includes(saved.processing_status)) {
          await new Promise((resolve) => setTimeout(resolve, 700));
          if (!mountedRef.current) return;
          saved = await api.getRecording(rec.id);
          setStage(saved.processing_status);
        }
        if (saved.processing_status === "FAILED")
          throw new Error(
            "This video could not be saved. " +
              (saved.processing_message || "Try another clip."),
          );
        if (completed.trim() && Number(completed) > 0) {
          const item = exercises.find((item) => item.id === exerciseId);
          const total = item?.rest_seconds || 60;
          try {
            saveRecordingRestTimer(rec.session_id, item?.name || "Rest after your set", total);
          } catch {
            /* Saving the video still works without browser storage. */
          }
        }
        router.push(
          attachedPlanId
            ? `/workouts/${attachedPlanId}?recorded=${rec.id}#exercise-${exerciseId}`
            : `/recordings/${rec.id}`,
        );
        return;
      }
      router.push(`/analysis/${rec.id}${planId ? `?plan=${planId}` : ""}`);
    } catch (err) {
      setStage(null);
      if (err instanceof ApiError && err.status === 409)
        setError(`${err.message} Open your current workout to continue.`);
      else setError(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  const busy = stage !== null;
  const canAnalyze = supportsAnalysis(exerciseId);
  const seconds = isTimedExercise(exerciseId);
  const exerciseName =
    exercises.find((item) => item.id === exerciseId)?.name || "Your exercise";
  const locked = busy || recording || openingCamera;
  const stages = STAGES.filter((item) =>
    analyzing
      ? item.id !== "SEGMENTING" || withOutlines
      : ["UPLOADED", "VALIDATING", "PREPROCESSING"].includes(item.id),
  );
  const stageIndex = stages.findIndex((item) => item.id === stage);

  return (
    <AppShell>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">
        {canAnalyze ? "Video coaching" : "Workout recording"}
      </p>
      <h1 className="mt-2 text-3xl font-semibold">{demo ? "Explore a sample set" : "Record your workout"}</h1>
      <p className="mt-2 max-w-2xl text-sm text-white/85">
        {demo ? "Explore how a reference rep, comparison, and explanation fit together. This example is separate from your training." : canAnalyze
          ? "Capture one working set. Compare your movement with your own reference rep and get a clear focus for the next set."
          : "Capture one working set and save a replay to your training history."}
      </p>
      {attachedPlanId && (
        <Link
          href={`/workouts/${attachedPlanId}`}
          className="mt-2 inline-block text-sm text-teal hover:underline"
        >
          ← Back to workout
        </Link>
      )}
      {!demo && !sessionId && (
        <p className="mt-3 max-w-2xl text-sm text-white/75">
          {planId
            ? "This recording will be attached to the selected workout when you save it."
            : openWorkout
              ? `This recording will be added to ${openWorkout}.`
              : "No workout is open, so this recording will be saved as its own capture session."}
        </p>
      )}
      {demo && <p className="mt-3 max-w-2xl text-sm leading-6 text-teal">Built-in illustrative data · no camera, upload, or model call. Samples stay outside your workout and never change targets or training totals.</p>}
      <div className="mt-6 grid max-w-2xl grid-cols-[minmax(0,1fr)_6rem] gap-3">
        <label className="text-sm text-white/85">
          Exercise
          <select
            className="mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-card px-3 py-3 text-white"
            value={exerciseId}
            disabled={!contextReady || locked || Boolean(file) || cameraReady}
            onChange={(event) => {
              const id = event.target.value;
              setExerciseId(id);
              setCompleted("");
              setError(null);
              setConsent(false);
              const item = exercises.find((item) => item.id === id);
              setLoad(
                item?.suggested_load_kg != null
                  ? String(displayLoad(item.suggested_load_kg, unit))
                  : "",
              );
              setReps(
                item?.target_reps != null ? String(item.target_reps) : "",
              );
              setSetNumber(
                String(
                  Math.max(
                    0,
                    ...sessionSets
                      .filter((set) => set.exercise_id === id)
                      .map((set) => set.set_index || 0),
                  ) + 1,
                ),
              );
            }}
          >
            <option value="" disabled>
              Choose exercise
            </option>
            {exercises.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-white/85">
          Set
          <input
            type="number"
            min={1}
            max={100}
            value={setNumber}
            disabled={locked}
            onChange={(event) => {
              setSetNumber(event.target.value);
              setCompleted("");
            }}
            className="mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-black/30 px-3 py-3 font-mono"
          />
        </label>
      </div>
      {existingClip && (
        <p className="mt-3 text-sm text-amber">
          {canRetryRecording(existingClip) ? "This set’s recording failed. Choose a replacement clip or record again, then review consent before submitting." : "A recording is already attached to this set."}{" "}
          <Link href={recordingHref(existingClip)} className="underline">
            Open recording
          </Link>
          {canRetryRecording(existingClip) ? (
            <button type="button" disabled={locked} onClick={() => {
              setRetryRecordingId(existingClip.id);
              setLoad(existingClip.load_kg == null ? "" : String(displayLoad(existingClip.load_kg, unit)));
              setReps(existingClip.target_reps == null ? "" : String(existingClip.target_reps));
              setEffort(existingClip.reported_rpe == null ? "" : String(existingClip.reported_rpe));
            }} className="ml-2 inline-flex min-h-11 items-center underline">
              {retryAuthorized ? "Ready to replace this recording" : "Replace recording and retry"}
            </button>
          ) : ", or choose another set."}
        </p>
      )}

      {!demo && (
      <div
        className="mt-6 inline-flex gap-1 rounded-full border border-white/10 p-1"
        aria-label="Capture method"
      >
        <button
          type="button"
          disabled={locked}
          aria-pressed={mode === "camera"}
          onClick={() => changeMode("camera")}
          className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm ${mode === "camera" ? "bg-teal text-black" : "text-white/80"}`}
        >
          <Camera className="h-4 w-4" aria-hidden />
          Camera
        </button>
        <button
          type="button"
          disabled={locked}
          aria-pressed={mode === "upload"}
          onClick={() => changeMode("upload")}
          className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm ${mode === "upload" ? "bg-teal text-black" : "text-white/80"}`}
        >
          <Upload className="h-4 w-4" aria-hidden />
          Upload video
        </button>
      </div>
      )}
      <div className={demo ? "mt-5 grid max-w-2xl gap-5" : "mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]"}>
        <Card className={demo ? "hidden" : "p-5"}>
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-medium">
              {file && !cameraReady
                ? "Review your recording"
                : mode === "camera"
                  ? "Position your camera"
                  : `Choose your ${exerciseName.toLowerCase()} clip`}
            </h2>
            {recording && (
              <span className="font-mono text-sm text-amber">
                ● {recordSeconds}s / {MAX_SECONDS}s
              </span>
            )}
          </div>
          <div className="relative mt-4 aspect-video overflow-hidden rounded-2xl bg-black">
            <video
              ref={previewRef}
              className={`absolute inset-0 h-full w-full object-contain ${cameraReady ? "" : "invisible"}`}
              muted
              playsInline
              aria-label="Live camera preview"
            />
            {!cameraReady && previewUrl && (
              <video
                src={previewUrl}
                className="absolute inset-0 h-full w-full object-contain"
                controls
                playsInline
                aria-label="Recorded video preview"
              />
            )}
            {!cameraReady && !previewUrl && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center text-white/75">
                {mode === "camera" ? (
                  <Camera className="h-10 w-10 text-teal" aria-hidden />
                ) : (
                  <Upload className="h-10 w-10 text-teal" aria-hidden />
                )}
                <p className="text-sm">
                  {mode === "camera"
                    ? "Enable your camera, check your position, then start recording."
                    : "Choose a clip of this set to preview it before saving."}
                </p>
                <p className="text-xs">
                  Your whole body should stay visible. Audio is not recorded.
                </p>
              </div>
            )}
          </div>
          {mode === "camera" && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {!cameraReady ? (
                <Button disabled={locked} onClick={() => void openCamera()}>
                  <Camera className="mr-2 h-4 w-4" aria-hidden />
                  {openingCamera
                    ? "Opening camera…"
                    : file
                      ? "Record another set"
                      : "Enable camera"}
                </Button>
              ) : recording ? (
                <Button variant="amber" onClick={stopRecording}>
                  Stop & review
                </Button>
              ) : (
                <>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      try {
                        startRecording();
                      } catch (err) {
                        setError(cameraError(err));
                      }
                    }}
                  >
                    <Video className="mr-2 h-4 w-4" aria-hidden />
                    Start recording
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() =>
                      void openCamera(
                        facing === "user" ? "environment" : "user",
                      )
                    }
                  >
                    Switch camera
                  </Button>
                  <Button variant="ghost" onClick={closeCamera}>
                    Close camera
                  </Button>
                </>
              )}
            </div>
          )}
          {mode === "upload" && (
            <label className="mt-4 block text-sm text-white/70">
              Video file
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm"
                className="mt-2 block w-full text-sm"
                disabled={locked}
                onChange={(event) =>
                  void chooseFile(event.target.files?.[0] || null)
                }
              />
            </label>
          )}
          {file && (
            <p
              className={
                check?.ok === false
                  ? "mt-3 text-sm text-red-400"
                  : "mt-3 text-sm text-teal"
              }
            >
              {file.name} · {check?.message || "Checking video…"}
            </p>
          )}
          {file && !locked && (
            <Button
              variant="ghost"
              className="mt-2"
              onClick={() => void chooseFile(null)}
            >
              Remove clip
            </Button>
          )}
          <h3 className="mt-5 text-sm font-medium">Before your set</h3>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-white/80">
            <li>
              Put the phone on a stable surface at about hip height, 2–3 m away.
            </li>
            <li>
              {canAnalyze
                ? "Film from the side, either side, so the bar, hips, knees, and ankles stay visible."
                : "Choose an angle where you can see the full movement and your equipment."}
            </li>
            <li>
              Keep your whole body in frame from head to feet, with only you in
              the shot.
            </li>
            <li>
              Start recording before the first rep, then do the set. Aim for
              20–40 seconds; the limit is {MAX_SECONDS} s.
            </li>
          </ol>
          {canAnalyze && (
            <p className="mt-3 text-xs text-white/80">
              A front view still runs, but depth and torso lean are less
              reliable.
            </p>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="text-lg font-medium">
            {exerciseName} · set {setNumber}
          </h2>
          <p className="mt-2 text-sm leading-6 text-white/80">
            {demo ? "These optional numbers describe the example only. Try the sample to explore its reference and explanation." : "Add your working weight and how the set felt. Your video stays on this device until you choose to save or analyze it."}
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3">
            <label className="text-sm text-white/80">
              Load ({unit}, optional)
              <input
                inputMode="decimal"
                className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm"
                value={load}
                disabled={busy}
                onChange={(event) => setLoad(event.target.value)}
              />
            </label>
            <label className="text-sm text-white/80">
              {canAnalyze
                ? "Target reps (optional)"
                : seconds
                  ? "Seconds completed (optional)"
                  : "Reps completed (optional)"}
              <input
                inputMode="numeric"
                className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm"
                value={canAnalyze ? reps : completed}
                disabled={busy}
                onChange={(event) =>
                  (canAnalyze ? setReps : setCompleted)(
                    event.target.value.replace(/\D/g, ""),
                  )
                }
              />
            </label>
          </div>
          {!canAnalyze && (
            <p className="mt-3 text-sm leading-6 text-white/80">
              Leave {seconds ? "seconds" : "reps"} blank to save just the video.
              Enter what you completed to log this set at the same time.
            </p>
          )}

          <fieldset className="mt-6">
            <legend className="text-sm font-medium">
              How hard was this set?
            </legend>
            <p className="mt-1 text-xs text-white/75">
              Optional · keep a note of how the set felt
              {canAnalyze ? " to help your coach" : " for next time"}.
            </p>
            <div className="mt-3 grid grid-cols-5 gap-1.5">
              {[
                ["6", "Easy"],
                ["7", "Steady"],
                ["8", "Hard"],
                ["9", "Very hard"],
                ["10", "Max effort"],
              ].map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  disabled={locked}
                  aria-pressed={effort === value}
                  onClick={() => setEffort(effort === value ? "" : value)}
                  className={`rounded-xl border px-1 py-3 text-xs ${effort === value ? "border-teal bg-teal/10 text-teal" : "border-white/10 text-white/80 hover:border-white/30"}`}
                >
                  <span className="block font-mono text-base">{value}</span>
                  <span className="mt-1 block">{label}</span>
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-white/70">
              8 means about 2 more reps were possible; 10 means none.
            </p>
          </fieldset>
          {canAnalyze && !demo && (
            <label className="mt-6 flex cursor-pointer items-start gap-3 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-white/85">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 shrink-0 accent-teal"
                checked={consent}
                disabled={locked}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span>
                I agree to send this video and training details to the analysis
                service for movement tracking and personalized coaching. An
                audio-free copy is used for outlines and deletion is requested
                after processing. I can delete the saved replay from my
                analysis.
              </span>
            </label>
          )}
          {canAnalyze && !demo && metaLoading && <p role="status" className="mt-3 text-sm text-white/80">Checking video coaching availability…</p>}
          {canAnalyze && !demo && metaError && (
            <div role="alert" className="mt-3 rounded-2xl border border-amber/30 p-4">
              <p className="text-sm leading-6 text-white/85">{metaError}</p>
              <Button variant="secondary" className="mt-3" disabled={metaLoading || locked} onClick={() => void loadProviderStatus()}>Retry availability check</Button>
            </div>
          )}
          {canAnalyze && !demo && meta && (!meta.sam_ready || !meta.coaching_ready) && (
            <p className="mt-3 text-xs text-amber">
              Basic movement analysis and rule-based coaching are available.
              Personalized model coaching or movement outlines are not enabled for this session.
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            {!demo && (<Button
              disabled={
                locked ||
                !contextReady ||
                Boolean(existingClip && !retryAuthorized) ||
                (canAnalyze && (!consent || !meta)) ||
                !file ||
                !check?.ok
              }
              onClick={() => submit(false)}
            >
              {busy
                ? analyzing
                  ? "Analyzing your set…"
                  : "Saving video…"
                : canAnalyze
                  ? "Analyze my set"
                  : completed.trim()
                    ? "Save video & log set"
                    : "Save video"}
            </Button>)}

            {canAnalyze && !demo && (
              <Button
                variant="secondary"
                disabled={
                  locked ||
                  !contextReady ||
                  Boolean(existingClip && !retryAuthorized) ||
                  !file ||
                  !check?.ok
                }
                onClick={() => submit(false, false)}
              >
                Save video only
              </Button>
            )}
            {demo && (
              <Button
                variant="secondary"
                disabled={locked || !contextReady}
                onClick={() => submit(true)}
              >
                Try sample set
              </Button>
            )}
          </div>
          {canAnalyze && !demo && !consent && (
            <p className="mt-2 text-xs text-white/70">
              Consent is required before analysis.
            </p>
          )}
          <p className="mt-3 text-sm leading-6 text-white/80">
            {demo ? "Replay and explanation are available for practice. Example targets cannot be applied to your workout." : canAnalyze
              ? "Analysis includes a replay, a personal reference comparison, and a next-set recommendation. Review any target change before it takes effect."
              : "Your video stays in your workout history for replay. No AI service receives this clip. You can delete the video and keep your logged set."}
          </p>
          {demo && (
            <p className="mt-3 font-mono text-xs text-amber">
              The labeled sample is synthetic data, not a live recording.
            </p>
          )}

          {busy && (
            <ol className="mt-5 space-y-1.5" aria-live="polite">
              {stages.map((item, index) => (
                <li
                  key={item.id}
                  className={
                    index < stageIndex
                      ? "text-sm text-white/70"
                      : index === stageIndex
                        ? "text-sm font-medium text-teal"
                        : "text-sm text-white/80"
                  }
                >
                  {index < stageIndex ? "✓" : index === stageIndex ? "●" : "○"}{" "}
                  {item.label}
                </li>
              ))}
              {stageMessage && (
                <li className="pt-2 text-xs text-white/75">
                  This can take a few minutes. Keep this page open while we
                  assess your set.
                </li>
              )}
            </ol>
          )}

          {unusable && (
            <div className="mt-5 rounded-2xl border border-amber/30 bg-amber/5 p-4 text-sm">
              <p className="font-medium text-amber">
                This recording could not be assessed.
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-white/85">
                {(unusable.analysis.tracking_quality?.issues || []).map(
                  (issue) => (
                    <li key={issue.code}>{issue.message}</li>
                  ),
                )}
                {!unusable.analysis.tracking_quality?.issues?.length && (
                  <li>No complete squat repetitions were found.</li>
                )}
              </ul>
              <p className="mt-2 text-white/80">
                Record again from the side with your whole body in frame, then
                upload the new clip.
              </p>
              <Link
                href={`/analysis/${unusable.id}`}
                className="mt-2 inline-block text-teal hover:underline"
              >
                See what was detected
              </Link>
            </div>
          )}
          {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
        </Card>
      </div>
    </AppShell>
  );
}

export default function RecordPage() {
  return (
    <Suspense>
      <RecordInner />
    </Suspense>
  );
}
