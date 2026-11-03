import { labelFor } from "@/lib/assessment";
import { formatLoad, type WeightUnit } from "@/lib/training";
import type { ProposalWhy } from "@/lib/types";

function displayValue(value: unknown, unit: WeightUnit): string {
  if (value == null || value === "") return "Not specified";
  if (Array.isArray(value))
    return value.every((item) => typeof item === "string")
      ? value.map((item) => labelFor(item)).join(" · ")
      : `${value.length} logged`;
  if (typeof value === "object")
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const row = item as { weight_kg?: number; reps?: number };
        return `${labelFor(key)}: ${row.weight_kg != null ? formatLoad(row.weight_kg, unit) : "load not set"}${row.reps != null ? ` × ${row.reps} reps` : ""}`;
      })
      .join(" · ");
  return typeof value === "string" ? labelFor(value) : String(value);
}

export function WhyThisWorkout({
  why,
  unit = "kg",
  explanation,
}: {
  why?: ProposalWhy | null;
  unit?: WeightUnit;
  explanation?: string | null;
}) {
  if (!why && !explanation) return null;
  return (
    <details className="mt-5 rounded-2xl border border-white/10 p-5">
      <summary className="flex min-h-11 cursor-pointer items-center text-base font-medium text-white">
        Why this plan?
      </summary>
      {(explanation || why?.model_summary) && (
        <p className="mt-3 text-sm leading-7 text-white/85">
          {explanation || why?.model_summary}
        </p>
      )}
      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        {why?.inputs.map((item) => (
          <div key={item.field}>
            <dt className="text-sm text-white/80">{item.label}</dt>
            <dd className="mt-1 leading-6 text-white/85">
              {displayValue(item.value, unit)}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
