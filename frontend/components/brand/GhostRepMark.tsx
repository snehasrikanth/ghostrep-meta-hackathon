import { GHOSTREP_AMBER, GHOSTREP_INK, GHOSTREP_TEAL, MARK_VIEWBOX, TWIN_G_PATH } from "@/components/brand/mark";
import { cn } from "@/lib/cn";

type Variant = "color" | "mono" | "onLight";

type Props = {
  className?: string;
  variant?: Variant;
  title?: string;
};

export function GhostRepMark({ className, variant = "color", title = "GhostRep" }: Props) {
  const reference = variant === "mono" ? "currentColor" : variant === "onLight" ? GHOSTREP_INK : GHOSTREP_TEAL;
  const twin = variant === "mono" ? "currentColor" : GHOSTREP_AMBER;
  const twinOpacity = variant === "mono" ? 0.38 : 0.92;

  return (
    <svg
      viewBox={MARK_VIEWBOX}
      className={cn("overflow-visible", className)}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d={TWIN_G_PATH} stroke={twin} strokeWidth="7.1" opacity={twinOpacity} transform="translate(3.6 4.2)" />
        <path d={TWIN_G_PATH} stroke={reference} strokeWidth="7.4" />
      </g>
    </svg>
  );
}

export function GhostRepAppIcon({ className, title = "GhostRep" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} role="img" aria-label={title}>
      <title>{title}</title>
      <rect width="64" height="64" rx="14" fill={GHOSTREP_INK} />
      <g fill="none" strokeLinecap="round" strokeLinejoin="round" transform="translate(2.5 1)">
        <path d={TWIN_G_PATH} stroke={GHOSTREP_AMBER} strokeWidth="6.6" opacity="0.92" transform="translate(3.2 3.8)" />
        <path d={TWIN_G_PATH} stroke={GHOSTREP_TEAL} strokeWidth="6.8" />
      </g>
    </svg>
  );
}
