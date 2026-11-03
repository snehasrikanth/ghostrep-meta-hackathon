import assert from "node:assert/strict";
import test from "node:test";
import { hipOffset, mapNormalized, videoContentRect } from "./videoSpace.ts";

test("letterboxes a portrait video inside a landscape stage", () => {
  const rect = videoContentRect(1000, 500, 720, 1280);
  assert.ok(rect.w < 1000);
  assert.equal(rect.h, 500);
  assert.ok(rect.x > 0);
  assert.equal(rect.y, 0);
});

test("maps normalized landmarks into the video rectangle", () => {
  const rect = { x: 100, y: 0, w: 200, h: 400 };
  const point = mapNormalized(0.5, 1, rect);
  assert.equal(point.x, 200);
  assert.equal(point.y, 400);
});

test("shifts the reference skeleton onto the current hip", () => {
  const offset = hipOffset(
    [{ name: "right_hip", x: 0.6, y: 0.5 }],
    [{ name: "right_hip", x: 0.4, y: 0.45 }],
  );
  assert.ok(Math.abs(offset.x - 0.2) < 1e-9);
  assert.ok(Math.abs(offset.y - 0.05) < 1e-9);
});
