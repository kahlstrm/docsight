'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

for (const [measurement, expected] of [
    [{}, '—'], [{ping_ms: null}, '—'],
    [{ping_ms: 0}, '0 ms'], [{ping_ms: 12.5}, '12.5 ms'],
]) {
    test(`speedtest completion displays ${JSON.stringify(measurement)} as ${expected}`, async () => {
        const requests = [], toasts = [], intervals = new Map();
        let startPolling;
        const element = () => ({setAttribute() {}, appendChild() {}});
        const button = element();
        const context = {
            T: {}, docsightUrl: url => url, addEventListener() {},
            document: {
                getElementById: id => id === 'speedtest-run-btn' ? button : null,
                querySelectorAll: () => [], createElement: element,
                createTextNode: text => ({textContent: text}),
            },
            fetch: url => new Promise(resolve => requests.push({url, resolve})),
            showToast: (message, level) => toasts.push({message, level}),
            setTimeout: callback => { startPolling = callback; },
            setInterval: (callback, delay) => { intervals.set(delay, callback); return delay; },
            clearInterval: id => intervals.delete(id),
        };
        context.window = context;
        vm.runInNewContext(fs.readFileSync(path.join(__dirname,
            '../../app/modules/speedtest/static/main.js'), 'utf8'), context);
        async function reply(index, data) {
            requests[index].resolve({ok: true, json: async () => data});
            await new Promise(resolve => setImmediate(resolve));
        }

        context.runSpeedtest();
        await reply(0, [{id: 1}]);
        assert.equal(requests[1].url, '/api/speedtest/run');
        await reply(1, {});
        startPolling();
        intervals.get(5000)();
        await reply(2, [{id: 2, download_mbps: 250, upload_mbps: 25, ...measurement}]);

        assert.deepEqual(toasts, [{
            message: `Speedtest complete: 250 / 25 Mbps, ${expected}`, level: 'success',
        }]);
        assert.equal(button.disabled, false);
        assert.equal(intervals.size, 0);
    });
}
