import { GhostRepAppIcon, GhostRepMark } from "@/components/brand/GhostRepMark";
import { cn } from "@/lib/cn";

type Props = {
  className?: string;
  markClassName?: string;
  wordmarkClassName?: string;
  variant?: "color" | "mono" | "onLight";
  compact?: boolean;
  appIcon?: boolean;
};

export function BrandLockup({
  className,
  markClassName,
  wordmarkClassName,
  variant = "color",
  compact = false,
  appIcon = false,
}: Props) {
  const size = compact ? "h-7 w-7" : "h-8 w-8";
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      {appIcon ? (
        <GhostRepAppIcon className={cn(size, markClassName)} />
      ) : (
        <GhostRepMark className={cn(size, markClassName)} variant={variant} />
      )}
      <span
        className={cn(
          "font-display font-semibold tracking-[-0.045em] text-white",
          compact ? "text-[1.05rem] leading-none" : "text-[1.35rem] leading-none",
          wordmarkClassName,
        )}
      >
        Ghost<span className={variant === "mono" ? "opacity-80" : "text-teal"}>Rep</span>
      </span>
    </span>
  );
}
