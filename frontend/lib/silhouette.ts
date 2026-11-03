export type Point = { x: number; y: number };
export type Rect = { x: number; y: number; w: number; h: number };

const DRAWABLE = new Set(["sam", "fixture"]);

export function hasSilhouette(source?: string | null): boolean {
  return DRAWABLE.has(source || "");
}

export function silhouetteCaption(source?: string | null): string {
  if (source === "sam") return "Your movement outline";
  if (source === "fixture") return "Sample outline";
  return "Skeleton view";
}

export function segmentationStatus(samStatus?: string | null, source?: string | null, processing?: string | null): string {
  if (processing === "SEGMENTING") return "processing";
  if (source === "sam") return "available";
  if (source === "fixture") return "available";
  if (["skipped", "skipped_local", "none"].includes(samStatus || "")) return "not requested";
  if (["failed", "empty", "unavailable", "blocked", "unsupported"].includes(samStatus || "")) return "unavailable";
  return "unavailable";
}

/** Move a normalized outline by a normalized offset, used when aligning to the current athlete. */
export function shiftOutline(points: Point[] | null | undefined, dx: number, dy: number): Point[] | null {
  if (!points || points.length < 3) return null;
  return points.map((point) => ({ x: point.x + dx, y: point.y + dy }));
}

/** Place a normalized outline inside the letterboxed video rectangle. */
export function outlineInRect(points: Point[] | null | undefined, rect: Rect): Point[] | null {
  const usable = shiftOutline(points, 0, 0);
  if (!usable || rect.w <= 0 || rect.h <= 0) return null;
  return usable.map((point) => ({ x: rect.x + point.x * rect.w, y: rect.y + point.y * rect.h }));
}
