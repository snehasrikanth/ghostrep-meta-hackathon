import assert from 'node:assert/strict';
import test from 'node:test';
import { setDecision,restDuration,feedbackLabel,fallbackCoaching } from './decision.ts';
import type {Coaching,Analysis} from './types.ts';
const base:Coaching={id:'c',set_id:'s',source:'muse_spark',source_label:'Muse Spark live API local-v4',summary:'Perfect bracing and strong reference',reason:'Brace better',primary_cue:'Rep 1 took less time to stand up',observations:[],evidence_references:[],confidence_notes:[],uncertainties:[],suggested_action:'EXTEND_REST',requires_confirmation:true,suggested_reps:8,current_reps:8,suggested_load_kg:40,current_load_kg:40,current_rest_seconds:180,suggested_rest_seconds:210,user_decision:'pending',actionable:true,session_status:'active',presentation:{version:'set-decision-v1',decision_basis:'reported_effort',reported_effort:10,explanation_key:'effort_rest',explanation_source:'deterministic',measurement_uncertain:false,review_only:false,evidence:[],observations:[]}};

test('effort drives the rest explanation, not an unrelated percentage or observational cue',()=>{
 const d=setDecision(base);assert.equal(d.state,'pending');assert.equal(d.mayDecide,true);assert.equal(d.proposed,true);assert.match(d.explanation,/10\/10 effort/);assert.equal(restDuration(base.suggested_rest_seconds!), '3 min 30 sec');
 assert.doesNotMatch(JSON.stringify(d),/brac|strong reference|Rep 1|Muse|SAM|API|local-v4/);assert.match(d.reviewLabel,/Review rest/);
 assert.equal(setDecision({...base,presentation:undefined}).explanation,'Review the suggested change and its evidence before applying it.');
});
test('pending/applied/rejected/review/closed states cannot describe an unapplied target as saved',()=>{
 assert.equal(setDecision({...base,user_decision:'accepted',applied_change:{applied:true}}).state,'applied');
 assert.equal(setDecision({...base,user_decision:'rejected'}).state,'rejected');
 for(const c of [{...base,actionable:false},{...base,suggested_rest_seconds:null}]){const d=setDecision(c);assert.equal(d.state,'review');assert.equal(d.mayDecide,false);assert.equal(d.proposed,false);}
 const closed=setDecision({...base,session_status:'completed'});assert.equal(closed.state,'closed');assert.doesNotMatch(closed.headline,/next set/);assert.equal(closed.mayDecide,false);
 const rejected=setDecision({...base,user_decision:'rejected'});assert.equal(rejected.proposed,false);assert.match(rejected.explanation,/no change was applied/);
 assert.equal(setDecision({...base,user_decision:'accepted',applied_change:{applied:true},historical_interpretation_corrected:true}).state,'review');
});
test('KEEP_PLAN, safety, recording quality and sample states stay distinct',()=>{
 assert.equal(setDecision({...base,suggested_action:'KEEP_PLAN'}).headline,'Keep your current targets');
 assert.match(setDecision({...base,suggested_action:'STOP_AND_SEEK_PROFESSIONAL_ADVICE',actionable:false}).headline,/Pause/);
 assert.match(setDecision({...base,suggested_action:'REQUEST_NEW_RECORDING',actionable:false}).headline,/clearer view/);
 assert.equal(setDecision(base,true).state,'sample');assert.equal(setDecision(base,true).mayDecide,false);
 assert.equal(feedbackLabel(base),'Saved analysis');assert.equal(feedbackLabel({...base,source:'local'}),'Basic movement feedback');assert.equal(feedbackLabel({...base,source:'fixture'}),'Sample demonstration');
});
test('missing coaching never invents a prescription or action eligibility',()=>{
 const c=fallbackCoaching({set_id:'s',session_status:'active',plan_id:'p'} as Analysis);assert.equal(c.actionable,false);assert.equal(c.current_rest_seconds,null);assert.equal(setDecision(c).state,'review');
});

test('a validated model focus materially changes the explanation while preserving the action and actual values',()=>{
 const standard=setDecision(base);
 const scoped=setDecision({...base,presentation:{...base.presentation!,explanation_key:'effort_scope',explanation_source:'validated_model_selection'}});
 assert.notEqual(scoped.explanation,standard.explanation);assert.match(scoped.explanation,/10\/10 effort.*8-rep target/);
 assert.equal(scoped.headline,standard.headline);assert.equal(scoped.proposed,true);
 const blocked=setDecision({...base,actionable:false,presentation:{...base.presentation!,explanation_key:'effort_scope'}});assert.equal(blocked.state,'review');assert.doesNotMatch(blocked.explanation,/keeping your/);
});
