"use client";

import { api } from "@/lib/api";
import type { Landmark, Overlay } from "@/lib/types";
import { hasSilhouette, shiftOutline, silhouetteCaption } from "@/lib/silhouette";
import { hipOffset, mapNormalized, videoContentRect } from "@/lib/videoSpace";
import { useEffect, useRef, useState } from "react";

export type SeekCue = { t: number; key: number };

type Props = {
  overlay: Overlay;
  setId: string;
  seekTo?: SeekCue | number | null;
  onTime: (t: number) => void;
};

export function GhostPlayer({ overlay, setId, seekTo, onTime }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const clockRef = useRef(0);
  const playingRef = useRef(true);
  const rateRef = useRef(1);
  const [showRef, setShowRef] = useState(!hasSilhouette(overlay.silhouette_source));
  const [showCurrent, setShowCurrent] = useState(!hasSilhouette(overlay.silhouette_source));
  const [showOutline, setShowOutline] = useState(true);
  const [showRefOutline, setShowRefOutline] = useState(true);
  const [alignBody, setAlignBody] = useState(true);
  const [opacity, setOpacity] = useState(0.35);
  const [playing, setPlaying] = useState(true);
  const [rate, setRate] = useState(1);
  const src = overlay.video_url ? api.mediaUrl(setId) : "";
  const duration = overlay.frames.at(-1)?.t ?? 0;
  const onTimeRef = useRef(onTime);

  useEffect(() => {
    onTimeRef.current = onTime;
  }, [onTime]);

  useEffect(() => {
    if (seekTo == null) return;
    const t = typeof seekTo === "number" ? seekTo : seekTo.t;
    clockRef.current = t;
    if (videoRef.current) videoRef.current.currentTime = t;
  }, [seekTo]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const video = videoRef.current;
      let t = clockRef.current;
      if (video && src) {
        t = Number.isFinite(video.currentTime) ? video.currentTime : 0;
      } else if (playingRef.current) {
        clockRef.current += dt * rateRef.current;
        if (duration > 0 && clockRef.current > duration) clockRef.current = 0;
        t = clockRef.current;
      }
      paint(canvas, overlay, t, showRef, showCurrent, showOutline, showRefOutline, alignBody, opacity, video);
      onTimeRef.current(t);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [overlay, showRef, showCurrent, showOutline, showRefOutline, alignBody, opacity, src, duration]);

  function setPlayback(next: number) {
    rateRef.current = next;
    setRate(next);
    if (videoRef.current) videoRef.current.playbackRate = next;
  }

  function toggle() {
    const next = !playingRef.current;
    playingRef.current = next;
    setPlaying(next);
    const video = videoRef.current;
    if (!video || !src) return;
    if (next) void video.play();
    else video.pause();
  }

  return (
    <div>
      <div className="relative overflow-hidden rounded-3xl bg-black">
        {src ? (
          <video
            ref={videoRef}
            src={src}
            className="aspect-[9/16] w-full bg-black object-contain md:aspect-video"
            controls
            muted
            autoPlay
            playsInline
            onRateChange={(e) => setPlayback((e.target as HTMLVideoElement).playbackRate)}
            onPlay={() => {
              playingRef.current = true;
              setPlaying(true);
            }}
            onPause={() => {
              playingRef.current = false;
              setPlaying(false);
            }}
          />
        ) : (
          <div className="aspect-[9/16] w-full bg-[#0b0d11] md:aspect-video" />
        )}
        <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
      </div>
        {!hasSilhouette(overlay.silhouette_source) && (
          <p className="mt-3 font-mono text-xs leading-5 text-white/80">
            Movement outline unavailable. Showing the tracked skeleton.
          </p>
        )}
        {overlay.silhouette_source === "fixture" && (
          <p className="mt-3 font-mono text-xs leading-5 text-amber">
            Sample movement overlay · illustrative result.
          </p>
        )}
        {overlay.silhouette_source === "sam" && (
          <p className="mt-3 font-mono text-xs leading-5 text-teal">
            Saved movement outlines · teal is your reference rep; orange is the selected rep.
          </p>
        )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <button className="min-h-11 min-w-11 rounded-full border border-white/10 px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" onClick={toggle}>
          {playing ? "Pause" : "Play"}
        </button>
        {overlay.reference_rep != null && <Toggle on={showRef} color="#20D6C7" onClick={() => setShowRef((v) => !v)} label="Reference skeleton" />}
        <Toggle on={showCurrent} color="#FF8A3D" onClick={() => setShowCurrent((v) => !v)} label="Current skeleton" />
        {hasSilhouette(overlay.silhouette_source) && (
          <Toggle on={showOutline} color="#FF8A3D" onClick={() => setShowOutline((v) => !v)} label="Your outline" />
        )}
        {overlay.reference_rep != null && hasSilhouette(overlay.silhouette_source) && (
          <Toggle on={showRefOutline} color="#20D6C7" onClick={() => setShowRefOutline((v) => !v)} label="Reference outline" />
        )}
        <button className="min-h-11 min-w-11 rounded-full border border-white/10 px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" onClick={() => setPlayback(0.5)}>0.5x</button>
        <button className="min-h-11 min-w-11 rounded-full border border-white/10 px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" onClick={() => setPlayback(1)}>1x</button>
        <span className="font-mono text-white/75">
          {rate.toFixed(1)}x · {silhouetteCaption(overlay.silhouette_source)}
        </span>
        <details className="w-full text-white/80"><summary className="flex min-h-11 cursor-pointer items-center">Advanced comparison settings</summary><div className="flex flex-wrap items-center gap-3">        <Toggle on={alignBody} color="#f4f6f8" onClick={() => setAlignBody((v) => !v)} label="Align to body" />
        {hasSilhouette(overlay.silhouette_source) && (
          <label className="flex items-center gap-2 font-mono text-white/80">
            Opacity
            <input
              aria-label="Silhouette opacity"
              type="range"
              min={0.1}
              max={0.7}
              step={0.05}
              value={opacity}
              onChange={(event) => setOpacity(Number(event.target.value))}
            />
          </label>
        )}
</div></details>
      </div>
    </div>
  );
}

function Toggle({ on, color, onClick, label }: { on: boolean; color: string; onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} aria-pressed={on} className="min-h-11 min-w-11 rounded-full border border-white/10 px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" style={{ color: on ? color : "#8b93a1" }}>
      {label}
    </button>
  );
}

function paint(
  canvas: HTMLCanvasElement,
  overlay: Overlay,
  t: number,
  showRef: boolean,
  showCurrent: boolean,
  showOutline: boolean,
  showRefOutline: boolean,
  alignBody: boolean,
  opacity: number,
  video: HTMLVideoElement | null,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  canvas.width = Math.max(1, cssW * devicePixelRatio);
  canvas.height = Math.max(1, cssH * devicePixelRatio);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const frame = nearestFrame(overlay.frames, t);
  if (!frame) return;
  const rect = videoContentRect(
    canvas.width,
    canvas.height,
    video?.videoWidth || 0,
    video?.videoHeight || 0,
  );
  const map = (lm: { x: number; y: number }) => mapNormalized(lm.x, lm.y, rect);
  if (showCurrent) drawSkeleton(ctx, frame.current, overlay.skeleton_edges, map, "#FF8A3D");
  const shift = alignBody && frame.reference ? hipOffset(frame.current, frame.reference) : { x: 0, y: 0 };
  if (showRef && frame.reference) {
    const shifted = frame.reference.map((lm) => ({ ...lm, x: lm.x + shift.x, y: lm.y + shift.y }));
    drawSkeleton(ctx, shifted, overlay.skeleton_edges, map, "#20D6C7");
  }
  if (hasSilhouette(overlay.silhouette_source)) {
    if (showOutline) drawOutline(ctx, frame.silhouette, map, opacity, "#FF8A3D");
    if (showRefOutline) drawOutline(ctx, shiftOutline(frame.reference_silhouette, shift.x, shift.y), map, opacity, "#20D6C7");
  }
}

function drawOutline(
  ctx: CanvasRenderingContext2D,
  points: { x: number; y: number }[] | null | undefined,
  map: (point: { x: number; y: number }) => { x: number; y: number },
  opacity: number,
  color: string,
) {
  if (!points || points.length < 3) return;
  ctx.beginPath();
  points.forEach((point, index) => {
    const placed = map(point);
    if (index === 0) ctx.moveTo(placed.x, placed.y);
    else ctx.lineTo(placed.x, placed.y);
  });
  ctx.closePath();
  const red = parseInt(color.slice(1, 3), 16);
  const green = parseInt(color.slice(3, 5), 16);
  const blue = parseInt(color.slice(5, 7), 16);
  ctx.fillStyle = `rgba(${red},${green},${blue},${opacity})`;
  ctx.fill();
  ctx.lineWidth = 1.5 * devicePixelRatio;
  ctx.strokeStyle = `rgba(${red},${green},${blue},${Math.min(1, opacity + 0.35)})`;
  ctx.stroke();
}

function nearestFrame(frames: Overlay["frames"], t: number) {
  if (!frames.length) return undefined;
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (frames[mid].t < t) lo = mid + 1;
    else hi = mid;
  }
  const prev = frames[Math.max(0, lo - 1)];
  const next = frames[lo];
  return Math.abs(prev.t - t) <= Math.abs(next.t - t) ? prev : next;
}

function drawSkeleton(
  ctx: CanvasRenderingContext2D,
  landmarks: Landmark[],
  edges: [string, string][],
  map: (lm: { x: number; y: number }) => { x: number; y: number },
  color: string,
) {
  const byName = new Map(landmarks.map((l) => [l.name, l]));
  ctx.lineWidth = 2 * devicePixelRatio;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  for (const [a, b] of edges) {
    const pa = byName.get(a);
    const pb = byName.get(b);
    if (!pa || !pb || pa.visibility < 0.25 || pb.visibility < 0.25) continue;
    const A = map(pa);
    const B = map(pb);
    ctx.beginPath();
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(B.x, B.y);
    ctx.stroke();
  }
  for (const lm of landmarks) {
    if (lm.visibility < 0.3) continue;
    const p = map(lm);
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3.2 * devicePixelRatio, 0, Math.PI * 2);
    ctx.fill();
  }
}
