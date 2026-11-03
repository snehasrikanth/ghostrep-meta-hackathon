import assert from "node:assert/strict";
import test from "node:test";
import {extendRest, restoreRest} from "./rest.ts";

test("pause, refresh and resume preserve remaining rest", () => {
  const start = {label: "Squat", endsAt: 100_000, total: 90};
  const paused = restoreRest(start, "paused", 40_000, new Date(30_000).toISOString())!;
  assert.equal(paused.pausedRemainingMs, 70_000);
  const refreshed = restoreRest(paused, "paused", 90_000)!;
  assert.equal(refreshed.pausedRemainingMs, 70_000);
  const resumed = restoreRest(refreshed, "active", 120_000)!;
  assert.equal(resumed.endsAt, 190_000);
  assert.equal(resumed.pausedRemainingMs, undefined);
  assert.equal(restoreRest(resumed, "active", 130_000)?.endsAt, 190_000);
});

test("closed and malformed clocks clear; extending a paused clock preserves pause", () => {
  const clock = {label: "Long exercise label", endsAt: 50_000, total: 45};
  for (const status of ["completed", "abandoned", "sample"]) assert.equal(restoreRest(clock, status, 10_000), null);
  assert.equal(restoreRest({...clock, total: -1}, "active", 10_000), null);
  assert.equal(restoreRest({...clock, endsAt: Number.NaN}, "active", 10_000), null);
  const more = extendRest({...clock, pausedRemainingMs: 20_000});
  assert.equal(more.pausedRemainingMs, 35_000);
  assert.equal(more.total, 60);
});
