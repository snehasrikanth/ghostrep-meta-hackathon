"use client";

import { Camera, Video } from "lucide-react";
import Link from "@/components/ui/Link";
import { Button } from "@/components/ui/button";
import { buttonClass } from "@/lib/buttonStyles";
import { captureHref } from "@/lib/capture";
import { cn } from "@/lib/cn";

export function CaptureEntry({
  planId,
  exerciseName,
  onRecord,
  href,
  label = "Record workout",
  canCoach = true,
  disabled = false,
  loading = false,
  sticky = false,
  description,
}: {
  planId?: string | null;
  exerciseName?: string;
  onRecord?: () => void;
  href?: string;
  label?: string;
  canCoach?: boolean;
  disabled?: boolean;
  loading?: boolean;
  sticky?: boolean;
  description?: string;
}) {
  return (
    <section
      className={cn(
        "mt-5 rounded-3xl border border-teal/30 bg-[#0b181b] p-4 shadow-lg sm:p-5",
        sticky && "sm:sticky sm:top-[calc(var(--app-header-height,4rem)+1rem)] z-20",
      )}
      aria-label="Workout recording"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl">
          <p className="flex items-center gap-2 text-sm font-medium text-teal">
            <Video className="h-4 w-4" aria-hidden />
            {canCoach ? "Video coaching" : "Workout video"}
          </p>
          <h2 className="mt-1 text-lg font-semibold sm:text-xl">Record your workout</h2>
          <p className={cn("mt-1 text-sm leading-6 text-white/85", sticky && "hidden sm:block")}>
            {description ||
              (canCoach
                ? "Capture one working set. Compare your movement with your own reference rep and get a focus for the next set."
                : "Capture a working set and keep a replay in your training history.")}
          </p>
          {exerciseName && (
            <p className="mt-1 text-sm text-white/85">
              Recording exercise:{" "}
              <span className="font-medium text-white">{exerciseName}</span>
            </p>
          )}
        </div>
        {onRecord ? (
          <Button
            onClick={onRecord}
            disabled={disabled}
            loading={loading}
            loadingLabel="Opening camera…"
          >
            <Camera className="h-4 w-4" aria-hidden />
            {label}
          </Button>
        ) : (
          <Link
            href={href || captureHref({ planId })}
            className={buttonClass("primary")}
          >
            <Camera className="h-4 w-4" aria-hidden />
            {label}
          </Link>
        )}
      </div>
    </section>
  );
}
