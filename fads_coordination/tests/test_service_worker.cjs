const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../web/sw.js'), 'utf8');
const destination = 'http://127.0.0.1:8787/web/employee.html?employeeId=sam&package=fixture';
async function check(action, failDelivery = false) {
  const handlers = {}; let pending, opened, focused, options, receipt;
  const client = {focus: async () => { focused = true; return client; }};
  const self = {location: {origin: 'http://127.0.0.1:8787'}, addEventListener: (n, f) => { handlers[n] = f; },
    registration: {showNotification: async (_, o) => { options = o; if (failDelivery) throw Error('Browser refused notification'); }},
    clients: {openWindow: async url => { opened = url; return client; }}};
  const context = {self, URL, URLSearchParams, Notification: {maxActions: 2}};
  vm.createContext(context); vm.runInContext(source, context);
  handlers.message({data: {renotify: true, package: {type: 'assignment', id: 'fixture', body: {employeeId: 'sam', plainText: 'Assigned: Transport', actions: [
    {id: 'open', label: 'Open web', kind: 'link', url: destination}, {id: 'accept', label: 'Accept'}, {id: 'snooze', label: 'Snooze 5 min'}]}}},
    ports: [{postMessage: value => { receipt = value; }}], waitUntil: p => { pending = p; }});
  await pending;
  if (failDelivery) { assert.equal(receipt.error, 'Browser refused notification'); console.log('PASS delivery error reaches caller'); return; }
  assert.equal(receipt.shown, true); assert.equal(options.renotify, true);
  assert.deepEqual(Array.from(options.actions, a => a.action), ['open', 'accept']);
  handlers.notificationclick({action, notification: {data: options.data, close() {}}, waitUntil: p => { pending = p; }});
  await pending;
  assert.equal(opened, destination); assert.equal(focused, true);
  console.log('PASS direct delivery, renotify and visible new tab: ' + (action || 'body click'));
}
(async () => { await check('open'); await check(''); await check('open', true); })().catch(error => { console.error(error); process.exitCode = 1; });
