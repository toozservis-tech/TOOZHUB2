// Execute the shipped calendar helpers, including edit-form round trips.
process.env.TZ = 'Europe/Prague';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/legacy-app.js', 'utf8');
const names = ['parseReservationInstant', 'getReservationTimestamp', 'padReservationDatePart',
    'parseReservationDateKey', 'getReservationDateKey', 'formatReservationDateTime',
    'formatReservationLocalDateInput', 'formatReservationLocalTimeInput', 'formatReservationTimeRange'];
const functions = names.map(name => {
    const start = source.indexOf(`        function ${name}(`);
    assert.ok(start >= 0, name);
    const end = source.indexOf('\n        }', start);
    return source.slice(start, end + 10);
}).join('\n');
const context = vm.createContext({ Date });
vm.runInContext(functions, context);
for (const [raw, day, time] of [
    ['2026-10-28T07:50:00', '2026-10-28', '08:50'],
    ['2026-10-28T07:50:00Z', '2026-10-28', '08:50'],
    ['2026-10-28T08:50:00+01:00', '2026-10-28', '08:50'],
    ['2026-07-28T06:50:00.123456', '2026-07-28', '08:50'],
    ['2026-03-29T01:30:00', '2026-03-29', '03:30'],
    ['2026-10-25T00:30:00', '2026-10-25', '02:30'],
    ['2026-10-25T01:30:00', '2026-10-25', '02:30'],
    ['2026-10-28T23:30:00', '2026-10-29', '00:30'],
]) {
    assert.equal(context.getReservationDateKey(raw), day);
    assert.equal(context.formatReservationLocalDateInput(raw), day);
    assert.equal(context.formatReservationLocalTimeInput(raw), time);
    assert.ok(context.formatReservationDateTime(raw).endsWith(time));
}
assert.equal(context.getReservationTimestamp('2026-10-28T07:50:00'), Date.parse('2026-10-28T07:50:00Z'));
assert.equal(new Date(context.formatReservationLocalDateInput('2026-10-28T07:50:00') + 'T' +
    context.formatReservationLocalTimeInput('2026-10-28T07:50:00')).toISOString(), '2026-10-28T07:50:00.000Z');
assert.equal(context.parseReservationDateKey('2026-10-28').getHours(), 0);
assert.equal(context.formatReservationTimeRange({ start_datetime:'2026-10-28T07:50:00', end_datetime:'2026-10-28T08:20:00' }), '08:50 - 09:20');
assert.equal(context.formatReservationLocalTimeInput(null), '');
console.log('Reservation timezone: winter, summer, DST, midnight, calendar and edit round-trip passed.');
