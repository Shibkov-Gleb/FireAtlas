import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';

const base = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080';
const origin = new URL(base).origin;
let cookie = '';
async function call(path, init = {}) {
  const response = await fetch(`${base}/api/v1${path}`, {
    ...init,
    headers: {
      Origin: origin,
      Cookie: cookie,
      'Content-Type': 'application/json',
      ...init.headers,
    },
    signal: AbortSignal.timeout(5000),
  });
  const session = response.headers.getSetCookie().find((value) => value.startsWith('fa_session='));
  if (session) cookie = session.split(';')[0];
  assert.equal(response.ok, true, `${path}: HTTP ${response.status}`);
  return (await response.json()).data;
}
const workspace = await call('/workspaces', { method: 'POST', body: '{}' });
const expected = await call('/workspaces/current', {
  method: 'PATCH',
  headers: { 'If-Match': `"${workspace.revision}"` },
  body: JSON.stringify({
    saved_investigation_ids: ['inv_psi25_bass2'],
    selected_investigation_ids: ['inv_psi25_bass2', 'inv_psi69_flex'],
  }),
});
const restart = spawnSync('docker', ['compose', 'restart', 'api'], { stdio: 'inherit' });
if (restart.error || restart.status) throw new Error('Не удалось перезапустить API.');
const deadline = Date.now() + 60000;
let actual;
while (Date.now() < deadline) {
  try {
    actual = await call('/workspaces/current');
    break;
  } catch {
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
assert.ok(actual, 'API не восстановился после перезапуска');
for (const key of [
  'id',
  'revision',
  'data_revision',
  'saved_investigation_ids',
  'selected_investigation_ids',
  'scenario',
])
  assert.deepEqual(actual[key], expected[key], `После перезапуска изменилось поле ${key}`);
console.log(
  'Проверено: API перезапущен, cookie-пространство, ревизия, миссия, сохранённое и сравнение восстановлены.',
);
