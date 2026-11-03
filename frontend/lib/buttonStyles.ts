import { cn } from "@/lib/cn";

export function buttonClass(
  variant: "primary" | "secondary" | "ghost" | "amber" = "primary",
  className?: string,
) {
  return cn(
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal",
    "disabled:pointer-events-none disabled:opacity-50",
    variant === "primary" && "bg-teal text-[#04110f] hover:brightness-110",
    variant === "amber" && "bg-amber text-[#1a0d04] hover:brightness-110",
    variant === "secondary" &&
      "border border-white/12 bg-white/5 text-white hover:bg-white/10",
    variant === "ghost" && "text-white/80 hover:bg-white/6 hover:text-white",
    className,
  );
}
