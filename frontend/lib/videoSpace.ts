export type Rect = { x: number; y: number; w: number; h: number };

/** object-contain rectangle of a video inside a container. */
export function videoContentRect(containerW: number, containerH: number, videoW: number, videoH: number): Rect {
  if (containerW <= 0 || containerH <= 0) return { x: 0, y: 0, w: 0, h: 0 };
  if (videoW <= 0 || videoH <= 0) return { x: 0, y: 0, w: containerW, h: containerH };
  const scale = Math.min(containerW / videoW, containerH / videoH);
  const w = videoW * scale;
  const h = videoH * scale;
  return { x: (containerW - w) / 2, y: (containerH - h) / 2, w, h };
}

export function mapNormalized(nx: number, ny: number, rect: Rect) {
  return { x: rect.x + nx * rect.w, y: rect.y + ny * rect.h };
}

export function hipOffset(
  current: { name: string; x: number; y: number }[],
  reference: { name: string; x: number; y: number }[],
) {
  const cur = current.find((p) => p.name === "right_hip") || current.find((p) => p.name === "left_hip");
  const ref = reference.find((p) => p.name === cur?.name);
  if (!cur || !ref) return { x: 0, y: 0 };
  return { x: cur.x - ref.x, y: cur.y - ref.y };
}
