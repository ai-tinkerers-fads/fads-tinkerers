/* Explicit demo notification trigger; no permission request on page load. */
async function sendDemoNotification(employeeId) {
  if (!('Notification' in window) || Notification.permission !== 'granted') {
    throw Error('Enable notifications on the employee page first.');
  }
  const registration = await navigator.serviceWorker.register('/web/sw.js');
  await registration.update();
  const worker = registration.installing || registration.waiting;
  if (worker && worker.state !== 'activated') {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Notification worker is not ready; retry.')), 10000);
      worker.addEventListener('statechange', () => {
        if (worker.state === 'activated' || worker.state === 'redundant') {
          clearTimeout(timer);
          resolve();
        }
      });
    });
  }
  if (!registration.active) throw Error('Notification worker is not active; retry.');
  const response = await fetch('/hooks/outbox?' + new URLSearchParams({callerId: employeeId, employeeId, types: 'assignment,reminder,conflict'}));
  if (!response.ok) throw Error('Could not read employee notifications.');
  const page = await response.json();
  const item = page.items.find(item => item.type === 'assignment' && item.body.kind !== 'removed') || page.items[0];
  if (!item) throw Error('No notification for this employee. Load the fixture first.');
  await new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timer = setTimeout(() => { channel.port1.close(); reject(Error('The notification worker did not respond. Refresh and retry.')); }, 10000);
    channel.port1.onmessage = event => {
      clearTimeout(timer);
      channel.port1.close();
      if (event.data.error) reject(Error(event.data.error)); else resolve();
    };
    registration.active.postMessage({package: item, renotify: true}, [channel.port2]);
  });
}
