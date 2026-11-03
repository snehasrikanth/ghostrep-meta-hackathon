import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { exerciseDemo } from "./exerciseDemos.ts";

test("only configured exercises expose a same-origin packaged example", () => {
  const demo = exerciseDemo("barbell_squat");
  assert.ok(demo);
  assert.equal(demo.src, "/demos/squat-example.mp4");
  assert.equal(exerciseDemo("barbell_row"), null);
  assert.equal(exerciseDemo("goblet_squat"), null);
  assert.equal(exerciseDemo(""), null);
  assert.equal(exerciseDemo("toString"), null);
  assert.equal(exerciseDemo("__proto__"), null);
  assert.equal(exerciseDemo("../../Downloads/private.mp4"), null);
  const media = readFileSync(new URL(`../public${demo.src}`, import.meta.url));
  assert.equal(media.subarray(4,8).toString(), "ftyp");
  assert.ok(media.length < 3_000_000);
});
