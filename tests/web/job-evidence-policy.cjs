const fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/service-features.js','utf8');
const expression=source.match(/const evidenceWritable=(\(job,actor\)=>[^;]+);/);
assert.ok(expression,'Missing actual web permission predicate');
const check=Function('return '+expression[1])();let cases=0;
for(const role of ['user','service','admin'])for(const actor of [1,2,-1])
for(const status of ['received','in_progress','completed','handed_over','cancelled'])
for(const consent of ['pending','rejected','approved','revoked','ownership_changed']) {
 const expected=role==='service'&&actor===1&&['received','in_progress','completed'].includes(status)&&['pending','rejected','approved'].includes(consent);
 assert.equal(check({service_id:1,status,consent_status:consent},{id:actor,role}),expected,JSON.stringify({role,actor,status,consent}));cases++;
}
console.log(`Web job attachment permissions: ${cases} cases passed`);
