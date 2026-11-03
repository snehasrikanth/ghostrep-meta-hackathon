"use client";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import { dayAction, dayHref, exercisePreview } from "@/lib/program";
import { sessionTypeLabel } from "@/lib/training";
import type { ProgramWeek } from "@/lib/types";
import Link from "@/components/ui/Link";

export function WeekGrid({
  week,
  compact = false,
}: {
  week: ProgramWeek;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-3",
        compact
          ? "grid-cols-2 sm:grid-cols-4 lg:grid-cols-7"
          : "grid-cols-1 sm:grid-cols-2 xl:grid-cols-4",
      )}
    >
      {week.days.map((day) => {
        const href = dayHref(day, week.week_index);
        const focus = sessionTypeLabel(day.workout?.session_type);
        const inProgress =
          day.session_status === "active" || day.session_status === "paused";
        return (
          <Link
            key={`${week.week_index}-${day.weekday}`}
            href={href}
            className="relative z-[1] block h-full min-h-11 rounded-[1.5rem] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
          >
            <Card
              className={cn(
                "flex h-full min-h-36 flex-col p-4 transition hover:border-white/20",
                inProgress && "border-amber/40 bg-amber/8",
                day.is_next && !inProgress && "border-teal/40 bg-teal/8",
                day.is_today && !day.is_next && !inProgress && "border-white/20",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-sm uppercase tracking-[0.16em] text-white/80">
                  {day.weekday_label.slice(0, 3)}
                </p>
                {inProgress ? (
                  <span className="rounded-full bg-amber px-2 py-0.5 text-sm font-medium text-[#1a0d04]">
                    Resume
                  </span>
                ) : day.is_next ? (
                  <span className="rounded-full bg-teal px-2 py-0.5 text-sm font-medium text-black">
                    Next
                  </span>
                ) : day.is_today ? (
                  <span className="text-sm uppercase text-white/80">Today</span>
                ) : null}
              </div>
              {day.kind === "recovery" ? (
                <>
                  <p className="mt-3 text-base font-medium">Recovery</p>
                  {!compact && (
                    <p className="mt-2 text-sm leading-6 text-white/80">
                      {day.recovery_copy}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className="mt-3 text-base font-medium leading-snug">
                    {focus || day.workout?.name}
                  </p>
                  {!compact && focus && day.workout?.name && (
                    <p className="mt-1 text-sm text-white/80">
                      {day.workout.name}
                    </p>
                  )}
                  <p className="mt-1 text-sm text-white/80">
                    {day.workout?.estimated_minutes
                      ? `~${day.workout.estimated_minutes} min`
                      : day.workout?.duration_minutes
                        ? `${day.workout.duration_minutes} min`
                        : ""}
                  </p>
                  {!compact && (
                    <p className="mt-2 text-sm leading-6 text-white/80">
                      {exercisePreview(day.workout)}
                    </p>
                  )}
                  {!compact && day.workout?.has_video_analysis && (
                    <p className="mt-2 text-sm text-teal">
                      Video coaching available
                    </p>
                  )}
                </>
              )}
              <p className="mt-auto pt-3 text-sm text-white/80">
                {day.kind === "recovery"
                  ? "Recharge for your next session"
                  : day.session_status === "completed"
                    ? "Completed"
                    : inProgress
                      ? "Unfinished · logged sets saved"
                      : day.is_preview
                        ? "Planned session"
                        : "Ready to train"}
              </p>
              <span className="mt-2 min-h-11 pt-1 text-sm font-medium text-teal">
                {dayAction(day)}
              </span>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
