// Original RT-08 out-of-order fixture, exercising the integrated controller.
import assert from 'node:assert/strict';
import {harness,bundle,tick} from '../ui_harness.mjs';
const h=harness();
const first=h.context.openDemo('si');const last=h.context.openDemo('approved');
h.finish('/api/demos/approved',{run_id:'approved-last-choice'});await tick();
h.finish('/api/runs/approved-last-choice',bundle('approved-last-choice'));await last;
h.finish('/api/demos/si',{run_id:'si-earlier-choice'});await first;
const visible=h.state.bundle?.run.run_id;
console.log(JSON.stringify({last_user_choice:'approved-last-choice',actual_visible:visible,source:'current openDemo/openRun functions; deterministic out-of-order local response fixture'}));
assert.equal(visible,'approved-last-choice','Late completion of an earlier selection must not overwrite the newest user selection');
