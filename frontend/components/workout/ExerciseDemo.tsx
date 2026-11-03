"use client";

import { exerciseDemo } from "@/lib/exerciseDemos";
import { Play, X } from "lucide-react";
import { useId, useRef, useState } from "react";

export function ExerciseDemo({ exerciseId }: { exerciseId: string }) {
  const demo = exerciseDemo(exerciseId);
  const titleId = useId(), descriptionId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const retryButton = useRef<HTMLButtonElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!demo) return null;

  function release() {
    const player = video.current;
    if (player) {
      player.pause();
      player.removeAttribute("src");
      player.load();
    }
    setOpen(false);
    trigger.current?.focus();
  }

  return <>
    <button ref={trigger} type="button" aria-haspopup="dialog" onClick={() => {
      setFailed(false);
      setOpen(true);
      dialog.current?.showModal();
    }} className="inline-flex min-h-11 items-center gap-2 rounded-xl px-2 text-sm font-medium text-teal hover:bg-teal/10">
      <Play size={15} aria-hidden="true" />Watch squat demo
    </button>
    <dialog ref={dialog} aria-labelledby={titleId} aria-describedby={descriptionId}
      onClose={release}
      onKeyDown={event => {
        // Keep Escape local when inside the app's mobile-preview iframe.
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); dialog.current?.close(); }
        if (event.key === "Tab" && event.shiftKey && document.activeElement === closeButton.current) {
          event.preventDefault();
          (retryButton.current || video.current || closeButton.current)?.focus();
        }
      }}
      className="fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[min(32rem,calc(100vw-2rem))] max-w-none overflow-y-auto rounded-2xl border border-white/20 bg-[#11151b] p-4 text-white shadow-2xl backdrop:bg-black/80 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <div><p className="text-xs text-teal">Example movement</p><h2 id={titleId} className="mt-1 text-xl font-semibold">{demo.title}</h2></div>
        <button ref={closeButton} type="button" autoFocus onClick={() => dialog.current?.close()} aria-label="Close squat demo" className="flex size-11 shrink-0 items-center justify-center rounded-full border border-white/15 hover:bg-white/10"><X size={20} aria-hidden="true" /></button>
      </div>
      <p id={descriptionId} className="mt-3 text-sm leading-6 text-white/80">{demo.description}</p>
      {open && !failed && <video ref={video} tabIndex={0} src={demo.src} controls playsInline preload="metadata" aria-label="Squat example video"
        onError={() => setFailed(true)} className="mt-4 max-h-[55dvh] w-full rounded-xl bg-black object-contain" />}
      {open && failed && <div role="alert" className="mt-4 rounded-xl border border-amber/30 p-4 text-sm leading-6 text-amber">
        <p>The example video could not play. You can still use the written exercise guidance and your own replay.</p>
        <button ref={retryButton} type="button" className="mt-2 min-h-11 text-teal underline" onClick={() => setFailed(false)}>Try loading the demo again</button>
      </div>}
      <span tabIndex={0} className="sr-only" onFocus={() => closeButton.current?.focus()}>Return to demo controls</span>
    </dialog>
  </>;
}
