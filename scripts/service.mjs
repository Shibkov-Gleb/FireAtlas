import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cwd = fileURLToPath(new URL('..', import.meta.url));
process.chdir(cwd);
const action = process.argv[2] ?? 'start';
const readSetting = (text, key) =>
  text
    .match(new RegExp(`^${key}=(.*)$`, 'm'))?.[1]
    .replace(/\s+#.*$/, '')
    .trim()
    .replace(/^['"]|['"]$/g, '') ?? '';
if (['start', 'setup'].includes(action)) {
  const current = existsSync('.env') ? readFileSync('.env', 'utf8') : '';
  if (!readSetting(current, 'FA_CURSOR_SECRET')) {
    const provider = process.env.OPENAI_API_KEY
      ? 'openai'
      : process.env.GEMINI_API_KEY
        ? 'gemini'
        : 'offline';
    const providerLine = readSetting(current, 'FA_LLM_PROVIDER')
      ? ''
      : `FA_LLM_PROVIDER=${provider}\n`;
    writeFileSync(
      '.env',
      `${current.replace(/^FA_CURSOR_SECRET=.*\r?\n?/m, '').trimEnd()}\nFA_CURSOR_SECRET=${randomBytes(32).toString('hex')}\n${providerLine}`,
      { mode: 0o600 },
    );
    console.log('Local .env configuration is ready; the secret is excluded from Git.');
  }
}
if (action === 'setup') process.exit(0);
const args = {
  start: ['up', '--build', '-d', '--wait', '--wait-timeout', '180'],
  stop: ['down'],
  logs: ['logs', '--tail', '100', '-f'],
  status: ['ps'],
}[action];
if (!args) throw new Error('Available commands: start, stop, logs, status, setup');
const child = spawnSync('docker', ['compose', ...args], { stdio: 'inherit', cwd });
if (child.error) {
  console.error('Start Docker Desktop and run the command again.');
  process.exit(1);
}
if (child.status) process.exit(child.status);
if (action === 'start')
  console.log(
    'Fire Atlas: http://127.0.0.1:8080 · pnpm stop shuts down the service while preserving its data.',
  );
