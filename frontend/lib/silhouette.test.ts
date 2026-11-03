import assert from "node:assert/strict";
import test from "node:test";
import { hasSilhouette, outlineInRect, segmentationStatus, shiftOutline, silhouetteCaption } from "./silhouette.ts";
import { videoContentRect } from "./videoSpace.ts";

const box = [
  { x: 0.2, y: 0.2 },
  { x: 0.8, y: 0.2 },
  { x: 0.5, y: 0.8 },
];

test("a missing outline stays missing", () => {
  assert.equal(shiftOutline(null, 1, 1), null);
  assert.equal(shiftOutline([{ x: 0, y: 0 }], 0, 0), null);
  assert.equal(outlineInRect(undefined, { x: 0, y: 0, w: 100, h: 100 }), null);
});

test("shifts the reference outline onto the current athlete", () => {
  const shifted = shiftOutline(box, 0.1, -0.05);
  assert.ok(shifted);
  assert.ok(Math.abs(shifted[0].x - 0.3) < 1e-9);
  assert.ok(Math.abs(shifted[0].y - 0.15) < 1e-9);
});

test("draws the outline inside the letterboxed video, not the full stage", () => {
  const rect = videoContentRect(1000, 500, 720, 1280);
  const placed = outlineInRect(box, rect);
  assert.ok(placed);
  for (const point of placed) {
    assert.ok(point.x >= rect.x && point.x <= rect.x + rect.w);
    assert.ok(point.y >= rect.y && point.y <= rect.y + rect.h);
  }
  assert.ok(placed[0].x > 0);
});

test("silhouette labels stay truthful", () => {
  assert.equal(silhouetteCaption("sam"), "Your movement outline");
  assert.equal(silhouetteCaption("fixture"), "Sample outline");
  assert.equal(silhouetteCaption("unavailable"), "Skeleton view");
  assert.equal(hasSilhouette("sam"), true);
  assert.equal(hasSilhouette("fixture"), true);
  assert.equal(hasSilhouette("unavailable"), false);
  assert.equal(segmentationStatus("skipped_local", "unavailable"), "not requested");
  assert.equal(segmentationStatus("live", "sam"), "available");
  assert.equal(segmentationStatus("fixture", "fixture"), "available");
  assert.equal(segmentationStatus("failed", "unavailable"), "unavailable");
  assert.equal(segmentationStatus("skipped", "unavailable", "SEGMENTING"), "processing");
});
