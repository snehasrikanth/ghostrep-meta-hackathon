import { GHOSTREP_AMBER, GHOSTREP_TEAL } from "@/components/brand/mark";

type Props = {
  depth: number;
  className?: string;
};

/** Side-view squat silhouettes. depth 0 is standing, 1 is a deeper squat. */
export function TwinFigures({ depth, className }: Props) {
  return (
    <svg viewBox="0 0 320 380" className={className} aria-hidden>
      <defs>
        <linearGradient id="floor" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#20D6C7" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#20D6C7" stopOpacity="0" />
        </linearGradient>
      </defs>
      <ellipse cx="168" cy="352" rx="92" ry="10" fill="url(#floor)" />
      <path d={trailPath(0.18)} fill="none" stroke={GHOSTREP_TEAL} strokeWidth="2" opacity="0.28" />
      <path d={trailPath(depth)} fill="none" stroke={GHOSTREP_AMBER} strokeWidth="2" opacity="0.45" />
      {drawAthlete(0.18, GHOSTREP_TEAL, 0.55)}
      {drawAthlete(depth, GHOSTREP_AMBER, 0.95)}
    </svg>
  );
}

function drawAthlete(depth: number, color: string, opacity: number) {
  const p = pose(depth);
  return (
    <g stroke={color} fill="none" strokeLinecap="round" strokeLinejoin="round" opacity={opacity}>
      <line x1={p.barL} y1={p.barY} x2={p.barR} y2={p.barY} strokeWidth="7" />
      <circle cx={p.headX} cy={p.headY} r="13" strokeWidth="4" />
      <path
        d={`M ${p.lShoulderX} ${p.shoulderY} L ${p.rShoulderX} ${p.shoulderY} L ${p.hipX} ${p.hipY} Z`}
        fill={color}
        fillOpacity="0.16"
        strokeWidth="4"
      />
      <line x1={p.rShoulderX} y1={p.shoulderY} x2={p.hipX} y2={p.hipY} strokeWidth="6" />
      <line x1={p.lShoulderX} y1={p.shoulderY} x2={p.hipX - 10} y2={p.hipY + 2} strokeWidth="4" opacity="0.5" />
      <line x1={p.hipX} y1={p.hipY} x2={p.kneeX} y2={p.kneeY} strokeWidth="6" />
      <line x1={p.kneeX} y1={p.kneeY} x2={p.ankleX} y2={p.ankleY} strokeWidth="6" />
      <line x1={p.hipX - 10} y1={p.hipY + 2} x2={p.backKneeX} y2={p.kneeY + 6} strokeWidth="4" opacity="0.5" />
      <line x1={p.backKneeX} y1={p.kneeY + 6} x2={p.ankleX - 14} y2={p.ankleY} strokeWidth="4" opacity="0.5" />
      <line x1={p.ankleX - 8} y1={p.ankleY} x2={p.ankleX + 18} y2={p.ankleY} strokeWidth="5.5" />
    </g>
  );
}

function pose(depth: number) {
  const d = Math.max(0, Math.min(1, depth));
  const hipX = 158 + d * 14;
  const hipY = 196 + d * 62;
  const shoulderY = hipY - 84 + d * 8;
  const headY = shoulderY - 28;
  const kneeX = 176 + d * 26;
  const kneeY = 278 + d * 16;
  return {
    headX: 154 + d * 16,
    headY,
    shoulderY,
    lShoulderX: 128 + d * 10,
    rShoulderX: 176 + d * 18,
    barY: shoulderY - 2,
    barL: 108 + d * 8,
    barR: 228 + d * 12,
    hipX,
    hipY,
    kneeX,
    kneeY,
    backKneeX: 150 + d * 10,
    ankleX: 168,
    ankleY: 348,
  };
}

function trailPath(depth: number) {
  const a = pose(0);
  const b = pose(depth);
  return `M ${a.hipX} ${a.hipY} Q ${a.hipX + 8} ${(a.hipY + b.hipY) / 2} ${b.hipX} ${b.hipY}`;
}
