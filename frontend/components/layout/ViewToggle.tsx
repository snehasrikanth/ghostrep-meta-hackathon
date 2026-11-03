"use client";

import { Monitor, Smartphone, X } from "lucide-react";
import { useRef, useState, useSyncExternalStore } from "react";

const subscribe = () => () => {};
const isTopLevel = () => window.self === window.top;
const serverSnapshot = () => false;

/** A real narrow viewport, so the app's existing mobile breakpoints apply. */
export function ViewToggle() {
  const visible = useSyncExternalStore(subscribe, isTopLevel, serverSnapshot);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [source, setSource] = useState<string | null>(null);

  function close() {
    dialog.current?.close();
  }

  if (!visible) return null;

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-label="Open mobile preview"
        title="Mobile preview"
        aria-haspopup="dialog"
        className="hidden size-11 shrink-0 items-center justify-center rounded-full border border-white/15 text-white/70 transition hover:bg-white/8 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal lg:inline-flex"
        onClick={() => {
          setSource(window.location.href);
          dialog.current?.showModal();
        }}
      >
        <Smartphone size={19} aria-hidden="true" />
      </button>
      <dialog
        ref={dialog}
        aria-label="Mobile preview"
        className="fixed inset-0 m-auto max-h-[95dvh] w-[422px] max-w-[95vw] overflow-hidden rounded-3xl border border-white/15 bg-[#11151b] p-0 text-white shadow-2xl backdrop:bg-black/80"
        onClose={() => {
          setSource(null);
          trigger.current?.focus();
        }}
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <span className="text-sm font-medium">Mobile preview</span>
          <div className="flex items-center gap-1">
            <button type="button" onClick={close} aria-label="Return to desktop view" title="Desktop view" className="flex size-11 items-center justify-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-teal">
              <Monitor size={19} aria-hidden="true" />
            </button>
            <button type="button" onClick={close} aria-label="Close mobile preview" className="flex size-11 items-center justify-center rounded-full hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-teal">
              <X size={19} aria-hidden="true" />
            </button>
          </div>
        </div>
        <p className="px-4 pb-3 text-xs text-white/60">Same account and data. Changes here are saved normally.</p>
        {source && (
          <iframe
            title="GhostRep mobile view"
            src={source}
            className="mx-auto block h-[min(844px,calc(95dvh-120px))] w-[390px] max-w-full border-0 bg-[#07090c]"
            onLoad={(event) => {
              // Escape also works while focus is inside the same-origin preview.
              const previewDocument = event.currentTarget.contentDocument;
              previewDocument?.addEventListener("keydown", (key) => {
                // A nested exercise dialog owns Escape until it has closed.
                if (key.key === "Escape" && !key.defaultPrevented && !previewDocument.querySelector("dialog[open]")) {
                  key.preventDefault();
                  close();
                }
              }, { capture: true });
            }}
          />
        )}
      </dialog>
    </>
  );
}
