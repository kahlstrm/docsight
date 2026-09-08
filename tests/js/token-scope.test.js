'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

for (const scope of ['metrics', 'api']) {
    test(`token creation sends the selected ${scope} scope`, () => {
        const fields = {'api-token-name': {value: 'prometheus'}, 'api-token-scope': {value: scope}};
        const requests = [];
        const context = vm.createContext({
            DOCSightSettings: {}, T: {}, docsightUrl: path => path,
            document: {getElementById: id => fields[id]},
            fetch: (path, options) => {
                requests.push({path, options});
                return new Promise(() => {});
            },
        });
        vm.runInContext(fs.readFileSync('app/static/js/settings/tokens.js', 'utf8'), context);
        context.DOCSightSettings.tokens({showToast() {}}).createApiToken();
        assert.equal(requests[0].path, '/api/tokens');
        assert.deepEqual(JSON.parse(requests[0].options.body), {name: 'prometheus', scope});
    });
}
