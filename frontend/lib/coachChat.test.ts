import assert from "node:assert/strict";
import test from "node:test";
import { COACH_QUESTIONS, coachActions, coachReplayHref, questionHistory, safeCoachHref, validCoachQuestion, type CoachReply, type CoachTurn } from "./coachChat.ts";

test("questions and follow-ups are bounded without sending while typing",()=>{
  assert.equal(COACH_QUESTIONS.length,5);
  assert.ok(COACH_QUESTIONS.every(validCoachQuestion));
  assert.equal(validCoachQuestion("  "),false);assert.equal(validCoachQuestion("x".repeat(401)),false);
  assert.equal(validCoachQuestion("bad\u0000question"),false);
  const turns=["first","second","third"].map(question=>({question,reply:{} as CoachReply}));
  assert.deepEqual(questionHistory(turns),["second","third"]);
  assert.deepEqual(questionHistory([] as CoachTurn[]),[]);
});

test("replay href ignores arbitrary provider markup and requires finite owned-reference shape",()=>{
  const e={id:"current:r3",set_id:"d64e7b15-85af-4b87-bfc6-fd16ca2a8866",rep_id:3,seconds:11.25,label:"Replay rep 3",href:"javascript:evil"};
  assert.equal(coachReplayHref(e),`/analysis/${e.set_id}?rep=3&t=11.25`);
  for(const bad of [{set_id:"https://evil.example"},{seconds:NaN},{seconds:Infinity},{seconds:-1},{rep_id:3.5},{rep_id:0}])assert.equal(coachReplayHref({...e,...bad}),null);
  assert.equal(safeCoachHref("/workouts/d64e7b15-85af-4b87-bfc6-fd16ca2a8866"), "/workouts/d64e7b15-85af-4b87-bfc6-fd16ca2a8866");
  assert.equal(safeCoachHref("https://evil.example/workouts/d64e7b15-85af-4b87-bfc6-fd16ca2a8866"), null);
  assert.equal(safeCoachHref("/analysis/d64e7b15-85af-4b87-bfc6-fd16ca2a8866"), null);
});

test("new action lists are used and older replies still expose one relevant control", () => {
  const evidence = {id:"current:r3", set_id:"d64e7b15-85af-4b87-bfc6-fd16ca2a8866", rep_id:3, seconds:10, label:"Compare rep 3", href:"javascript:alert(1)"};
  const base = {set_id:evidence.set_id, answer:"Rep 3", evidence:[evidence], uncertainty:null, suggested_ui_action:"review_recommendation" as const, source:"basic" as const, notice:null, basis:"saved"};
  const legacy = coachActions(base);
  assert.equal(legacy[0]?.label, "Compare rep 3");
  assert.equal(legacy.some(action => action.kind === "review_recommendation"), true);
  assert.equal(legacy[0]?.href, `/analysis/${evidence.set_id}?rep=3&t=10`);
  const current = coachActions({...base, actions:[{kind:"review_recommendation", label:"Review rest suggestion", emphasis:"primary"}, {kind:"workout", label:"Back to workout", href:"javascript:alert(1)"}]});
  assert.deepEqual(current.map(action => action.label), ["Review rest suggestion"]);
  assert.equal(coachActions({...base, evidence:[], suggested_ui_action:"watch_demo", actions:undefined}).at(-1)?.label, "Watch squat demo");
});
