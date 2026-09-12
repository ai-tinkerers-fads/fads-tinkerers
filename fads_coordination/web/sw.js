/* Local reference transport: a live employee page forwards the SSE packages. */
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('message', event => {
  const item = event.data?.package;
  if (!item || !['assignment', 'reminder', 'conflict'].includes(item.type)) return;
  const actions = item.body.actions || [];
  const resolveUrl = actions.find(action => action.id === 'open')?.url ||
    '/web/employee.html?' + new URLSearchParams({employeeId: item.body.employeeId});
  const limit = Number.isInteger(Notification.maxActions) ? Notification.maxActions : 2;
  const visible = ['open', 'accept', 'snooze']
    .map(id => actions.find(action => action.id === id)).filter(Boolean).slice(0, limit);
  event.waitUntil(self.registration.showNotification(item.body.plainText || item.body.text || item.body.name, {
    tag: item.id,
    actions: visible.map(action => ({action: action.id, title: action.label})),
    data: {actions, resolveUrl}
  }));
});
async function openEmployee(path) {
  const url = new URL(path, self.location.origin);
  const windows = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
  for (const client of windows) {
    const current = new URL(client.url);
    if (current.pathname === url.pathname && current.searchParams.get('employeeId') === url.searchParams.get('employeeId')) {
      await client.navigate(url.href);
      return client.focus();
    }
  }
  return self.clients.openWindow(url.href);
}
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const {actions, resolveUrl} = event.notification.data;
  event.waitUntil((async () => {
    const action = actions.find(candidate => candidate.id === event.action);
    if (action?.kind === 'link') return openEmployee(action.url);
    if (!action || action.needs) return openEmployee(action?.resolveUrl || resolveUrl);
    try {
      const response = await fetch(action.url, {method: action.method, headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...action.body, sourceId: crypto.randomUUID()})});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Action failed');
    } catch (error) {
      const url = new URL(resolveUrl, self.location.origin);
      url.searchParams.set('error', error.message);
      await openEmployee(url.href);
    }
  })());
});
