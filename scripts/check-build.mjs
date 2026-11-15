import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
const mode = process.argv[2];
if (!['production', 'demo'].includes(mode)) throw new Error('Use production or demo.');
const dist = resolve('apps/web/dist');
if (!existsSync(resolve(dist, 'index.html'))) throw new Error('Build is missing.');
for (const file of ['mockServiceWorker.js', 'demo-report.pdf']) {
  const present = existsSync(resolve(dist, file));
  if (present !== (mode === 'demo')) throw new Error(`Unexpected ${file} state for ${mode}.`);
}
for (const file of readdirSync(resolve(dist, 'assets')).filter((file) => file.endsWith('.css'))) {
  if (/fonts\.googleapis\.com/.test(readFileSync(resolve(dist, 'assets', file), 'utf8')))
    throw new Error('Fonts must be bundled locally.');
}
if (mode === 'production') {
  for (const file of readdirSync(resolve(dist, 'assets')).filter((file) => file.endsWith('.js'))) {
    if (readFileSync(resolve(dist, 'assets', file), 'utf8').includes('fireatlas-demo-v1')) {
      throw new Error('Production includes the mock database module.');
    }
  }
}
if (
  mode === 'demo' &&
  readFileSync(resolve(dist, 'demo-report.pdf')).subarray(0, 5).toString() !== '%PDF-'
)
  throw new Error('Demo PDF is invalid.');
console.log(`${mode} artifact verified: local fonts and expected API mode.`);
