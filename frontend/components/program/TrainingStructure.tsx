import { structureDescription, structureHeadline } from "@/lib/program";

export function TrainingStructure({
  split,
  count,
  accepted = false,
  compact = false,
}: {
  split: string;
  count: number;
  accepted?: boolean;
  compact?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border border-teal/20 bg-teal/5 ${compact ? "p-4" : "p-5 sm:p-6"}`}
    >
      <p className="text-sm font-medium text-teal">
        {accepted ? "Active weekly plan" : "Weekly training structure"}
      </p>
      <p
        className={`mt-1 font-semibold ${compact ? "text-lg" : "text-xl sm:text-2xl"}`}
      >
        {structureHeadline(split, count)}
      </p>
      <p
        className={`mt-2 max-w-2xl leading-6 text-white/80 ${compact ? "text-sm" : "text-sm sm:text-base"}`}
      >
        {structureDescription(split)}
      </p>
    </div>
  );
}
