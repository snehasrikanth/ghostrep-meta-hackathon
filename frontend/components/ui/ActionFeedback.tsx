import { CheckCircle2, CircleAlert, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

export function ActionFeedback({
  kind,
  children,
}: {
  kind: "loading" | "success" | "error" | "blocked";
  children: ReactNode;
}) {
  const Icon =
    kind === "loading"
      ? LoaderCircle
      : kind === "success"
        ? CheckCircle2
        : CircleAlert;
  return (
    <div
      role={kind === "error" || kind === "blocked" ? "alert" : "status"}
      className={`flex items-start gap-3 rounded-2xl border p-4 text-sm leading-6 ${kind === "error" ? "border-red-400/30 bg-red-400/5 text-red-200" : kind === "blocked" ? "border-amber/30 bg-amber/5 text-white/90" : "border-teal/25 bg-teal/5 text-white/90"}`}
    >
      <Icon
        aria-hidden
        className={`mt-0.5 h-5 w-5 shrink-0 ${kind === "loading" ? "animate-spin text-teal motion-reduce:animate-none" : kind === "success" ? "text-teal" : kind === "error" ? "text-red-300" : "text-amber"}`}
      />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
