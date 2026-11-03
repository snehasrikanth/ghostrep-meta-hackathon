import { ChevronDown, Flame } from "lucide-react";

export function Warmup({
  steps,
  mainLift,
  expanded = false,
}: {
  steps?: string[];
  mainLift?: string;
  expanded?: boolean;
}) {
  const items = steps?.length
    ? steps
    : [
        "Start with 3–5 minutes of easy movement to feel ready.",
        `Practice ${mainLift || "the first movement"} with no load or a comfortable light load.`,
        "Build up with a few gradual practice sets. Keep these easy before your working sets.",
      ];
  return (
    <details
      className="group mt-5 rounded-2xl border border-teal/15 bg-teal/5 p-5"
      open={expanded}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-base font-medium">
        <Flame className="h-4 w-4 text-teal" />
        Prepare for your session
        <span className="ml-auto text-sm font-normal text-white/80">
          Warm-up
        </span>
        <ChevronDown
          aria-hidden
          className="h-4 w-4 shrink-0 text-white/80 transition group-open:rotate-180"
        />
      </summary>
      <ol className="mt-4 space-y-3">
        {items.map((step, i) => (
          <li key={i} className="flex gap-3 text-sm leading-6 text-white/85">
            <span className="font-mono text-sm leading-6 text-teal">
              0{i + 1}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
