'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../../app/modules/comparison/static/main.js'), 'utf8');

function comparison(now) {
    class Clock extends Date {
        constructor(...args) { super(...(args.length ? args : [now])); }
    }
    const context = {Date: Clock, window: {}};
    vm.createContext(context);
    vm.runInContext(source, context);
    return context;
}

for (const timezone of ['Europe/Helsinki', 'America/New_York', 'UTC']) {
    test(`local date inputs and displayed ranges agree in ${timezone}`, () => {
        const previous = process.env.TZ;
        process.env.TZ = timezone;
        try {
            const c = comparison('2026-09-10T12:34:00Z');
            const dates = c._cmpPresetDates('yesterday_today');
            assert.equal(dates.fromB, '2026-09-10T00:00');
            assert.equal(dates.fromA, '2026-09-09T00:00');
            for (const value of Object.values(dates)) {
                assert.equal(c._cmpShortDate(c._cmpToISO(value)), value.replace('T', ' '));
            }
            assert.equal(c._cmpToISO(''), '');
        } finally {
            if (previous === undefined) delete process.env.TZ;
            else process.env.TZ = previous;
        }
    });
}

test('calendar presets remain on the correct dates across Helsinki DST changes', () => {
    const previous = process.env.TZ;
    process.env.TZ = 'Europe/Helsinki';
    try {
        for (const [now, yesterday, monday, lastMonday] of [
            ['2026-03-30T12:00:00Z', '2026-03-29', '2026-03-30', '2026-03-23'],
            ['2026-10-26T12:00:00Z', '2026-10-25', '2026-10-26', '2026-10-19'],
        ]) {
            const c = comparison(now);
            assert.equal(c._cmpPresetDates('yesterday_today').fromA, yesterday + 'T00:00');
            const week = c._cmpPresetDates('last_this_week');
            assert.equal(week.fromB, monday + 'T00:00');
            assert.equal(week.fromA, lastMonday + 'T00:00');
            assert.equal(week.toA, yesterday + 'T23:59');
        }
    } finally {
        if (previous === undefined) delete process.env.TZ;
        else process.env.TZ = previous;
    }
});

test('minute-by-minute error increases are not overwritten by rounded chart offsets', () => {
    const c = comparison();
    const start = '2026-03-01T00:00:00Z';
    const samples = [0, 1, 2].map(minute => ({
        timestamp: `2026-03-01T00:0${minute}:00Z`, uncorr_errors: minute * 10,
    }));
    const normalized = c._cmpNormalize(samples, start);
    const labels = c._cmpMergeHourLabels(normalized, []);
    assert.equal(labels.length, 3);
    assert.deepEqual(Array.from(c._cmpMapToLabels(normalized, labels), p => p.uncorr_errors), [0, 10, 20]);
});
