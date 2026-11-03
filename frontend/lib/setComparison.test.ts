import assert from "node:assert/strict";
import test from "node:test";
import { requestedComparisonEvidence } from "./setComparison.ts";
import type { Rep } from "./types.ts";

const reps: Rep[] = [{rep_id:3,start_seconds:7,bottom_seconds:8,end_seconds:9,descent_seconds:1,ascent_seconds:1,is_complete:true,is_reference:false,confidence:.9,comparison_eligible:true,metrics:{}}];

test("previous-set evidence opens the linked measured rep and timestamp", () => {
  assert.deepEqual(requestedComparisonEvidence(reps,"3","8"),{repId:3,seconds:8});
});
test("missing evidence parameters do not select a repetition", () => {
  assert.equal(requestedComparisonEvidence(reps,null,"8"),null);
  assert.equal(requestedComparisonEvidence(reps,"3",null),null);
  assert.equal(requestedComparisonEvidence(reps,"3",""),null);
});
test("unknown reps and timestamps outside the measured rep are rejected", () => {
  for (const [id,t] of [["4","8"],["3","0"],["3","9.1"],["3.5","8"],["3","NaN"],["3","Infinity"]])
    assert.equal(requestedComparisonEvidence(reps,id,t),null);
});
test("partial and ineligible measurements cannot be opened as comparison evidence", () => {
  assert.equal(requestedComparisonEvidence([{...reps[0],is_complete:false}],"3","8"),null);
  assert.equal(requestedComparisonEvidence([{...reps[0],comparison_eligible:false}],"3","8"),null);
});
