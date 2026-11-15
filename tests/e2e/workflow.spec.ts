import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';
import { analyse, jobData, mode, ready } from './helpers';

test('complete research path, original context, reload and repeatable PDF download', async ({
  page,
}) => {
  const posts: { path: string; key: string | undefined; body: string | null }[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && /\/api\/v1\/(analyses|reports)$/.test(request.url()))
      posts.push({
        path: new URL(request.url()).pathname,
        key: request.headers()['idempotency-key'],
        body: request.postData(),
      });
  });
  await ready(page);
  await page
    .getByRole('textbox', { name: 'Your research question' })
    .fill('How does ventilation affect the combustion of solid materials?');
  await page.getByRole('button', { name: 'Explore', exact: true }).click();
  await expect(page.getByRole('link', { name: 'BASS-II', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'BASS-II', exact: true }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add to comparison', exact: true }).click();
  await expect(page.getByRole('button', { name: 'In comparison', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Open evidence 1', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(
    page.getByRole('dialog').getByRole('link', { name: /Open original source/ }),
  ).toHaveAttribute('href', 'https://ntrs.nasa.gov/citations/20160000593');
  await page.getByRole('button', { name: 'Close panel', exact: true }).click();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Measurements', exact: true })
    .click();
  await page.getByRole('button', { name: 'Select point 30CAL03', exact: true }).click();
  await expect(page.getByTestId('selected-run-id')).toHaveText('30CAL03');
  await expect(page.getByRole('button', { name: '30CAL03', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByText('1.92 mm', { exact: true })).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Comparison', exact: true }).click();
  await page.getByRole('button', { name: 'Add FLEX to comparison', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Investigation comparison matrix' })).toBeVisible();
  await expect(page.getByText(/a common fire-hazard scale is not justified/)).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Ask AI AI', exact: true }).click();
  const job = await analyse(page);
  const originalUrl = page.url();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Save answer', exact: true })).toBeVisible();
  expect((await jobData(page, job)).state).toBe('succeeded');
  await page.getByRole('button', { name: 'Save answer', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Answer saved', exact: true })).toBeVisible();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Mission scenarios', exact: true })
    .click();
  await page
    .getByRole('button', {
      name: 'Lunar base Lunar surface · partial gravity',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('PSI contains no direct partial-gravity measurements.', { exact: true }),
  ).toBeVisible();
  await page.goto(originalUrl);
  await expect(
    page.getByRole('heading', { name: 'Answer context: Orbital station', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/This answer uses an earlier workspace snapshot/)).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Reports', exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Report title', exact: true })
    .fill('Ventilation: research and limitations');
  await page.getByRole('button', { name: 'Prepare PDF', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Download PDF', exact: true })).toBeEnabled();
  const first = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF', exact: true }).click();
  const downloaded = await first;
  const bytes = await readFile((await downloaded.path())!);
  expect(bytes.subarray(0, 5).toString()).toBe('%PDF-');
  expect(bytes.length).toBeGreaterThan(1000);
  const second = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF', exact: true }).click();
  await second;
  expect(posts.filter((post) => post.path.endsWith('/analyses'))).toHaveLength(1);
  expect(posts.filter((post) => post.path.endsWith('/reports'))).toHaveLength(1);
});

test('hard ranges remain hard when related work is requested', async ({ page }) => {
  await ready(page, '/investigations?o2_min=0.9&o2_max=1');
  await expect(
    page.getByRole('heading', { name: 'No investigations match these conditions' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Show related materials', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'No investigations match these conditions' }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get('o2_min')).toBe('0.9');
});

test('provider failure leaves source access and catalog working', async ({ page }) => {
  await mode(page, 'provider_error');
  await ready(page, '/ask');
  await analyse(page);
  await expect(
    page.getByText('The model provider is unavailable. Retrieved sources can still be opened.', {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Source 1', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Close panel', exact: true }).click();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Investigations', exact: true })
    .click();
  await expect(page.getByRole('link', { name: 'BASS-II', exact: true })).toBeVisible();
});

test('cancelled job cannot publish a late answer', async ({ page }) => {
  await ready(page, '/ask');
  const id = await analyse(page);
  await page.getByRole('button', { name: 'Cancel job', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Cancelled', exact: true })).toBeVisible();
  await page.waitForTimeout(3800);
  const job = await jobData(page, id);
  expect(job.state).toBe('cancelled');
  expect(job.result_id).toBeNull();
  await expect(page.getByRole('button', { name: 'Save answer', exact: true })).toHaveCount(0);
});

test('server timeout ends waiting without starting another analysis', async ({ page }) => {
  await mode(page, 'timeout');
  let count = 0;
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/analyses')) count++;
  });
  await ready(page, '/ask');
  await analyse(page);
  await expect(page.getByRole('heading', { name: 'Expired', exact: true })).toBeVisible();
  expect(count).toBe(1);
});

test('lost POST response reuses the same key and original body', async ({ page }) => {
  await mode(page, 'lost_response');
  const requests: { key: string | undefined; body: string | null }[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/analyses'))
      requests.push({ key: r.headers()['idempotency-key'], body: r.postData() });
  });
  await ready(page, '/ask');
  await page
    .getByRole('textbox', { name: 'Question for AI', exact: true })
    .fill('How does ventilation affect flames?');
  await page.getByRole('button', { name: 'Get answer', exact: true }).click();
  await expect(
    page.getByText('The outcome of the previous request is unconfirmed.', { exact: true }),
  ).toBeVisible();
  await page
    .getByRole('textbox', { name: 'Question for AI', exact: true })
    .fill('Another question after a lost response');
  await page.getByRole('button', { name: 'Retry the same request', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save answer', exact: true })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
  const count = await page.evaluate(
    () =>
      new Promise<number>((resolve, reject) => {
        const open = indexedDB.open('fireatlas-demo-v1');
        open.onerror = () => reject(open.error);
        open.onsuccess = () => {
          const db = open.result;
          const read = db.transaction('state').objectStore('state').get('snapshot');
          read.onsuccess = () => {
            resolve(Object.keys(read.result.jobs).length);
            db.close();
          };
        };
      }),
  );
  expect(count).toBe(1);
});

test('fourth selection preserves the three existing investigations', async ({ page }) => {
  await mode(page, 'comparison_limit');
  await ready(page, '/compare');
  for (const name of ['BASS-II', 'FLEX', 'SAME-R']) {
    await page.getByRole('button', { name: `Add ${name} to comparison`, exact: true }).click();
    await expect(
      page.getByRole('button', { name: `Remove ${name} to comparison`, exact: true }),
    ).toBeVisible();
  }
  await page.getByRole('button', { name: 'Add DEMO-04 to comparison', exact: true }).click();
  await expect(page.getByText(/You can compare up to three investigations/)).toBeVisible();
  const selected = await page.evaluate(
    async () =>
      (await (await fetch('/api/v1/workspaces/current')).json()).data.selected_investigation_ids,
  );
  expect(selected).toEqual(['inv_psi25', 'inv_psi69', 'inv_psi101']);
});

test('stale workspace is refreshed without automatically overwriting the newer selection', async ({
  page,
}) => {
  await ready(page, '/compare');
  await page.evaluate(async () => {
    const { data } = await (await fetch('/api/v1/workspaces/current')).json();
    await fetch('/api/v1/workspaces/current', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'If-Match': `"${data.revision}"` },
      body: JSON.stringify({ selected_investigation_ids: ['inv_psi69'] }),
    });
  });
  await page.getByRole('button', { name: 'Add BASS-II to comparison', exact: true }).click();
  await expect(page.getByText('The workspace context has changed.', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Remove FLEX to comparison', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Keep the updated context', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Add BASS-II to comparison', exact: true }),
  ).toBeVisible();
});

test('mission presets require an explicit decision before transferring conditions', async ({
  page,
}) => {
  await ready(page, '/missions');
  await page.getByRole('spinbutton', { name: 'Oxygen, %', exact: true }).fill('21');
  await page.getByRole('button', { name: 'Apply conditions', exact: true }).click();
  await expect(page.getByText('Scenario conditions saved.', { exact: true })).toBeVisible();
  await page
    .getByRole('button', {
      name: 'Lunar base Lunar surface · partial gravity',
      exact: true,
    })
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Start without entered conditions', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: 'Oxygen, %', exact: true })).toHaveValue('');
  await page
    .getByRole('button', { name: 'Orbital station Orbit · microgravity', exact: true })
    .click();
  await expect(page.getByRole('textbox', { name: 'Mission name', exact: true })).toHaveValue(
    'Orbital station',
  );
  await expect(
    page.getByText('PSI contains no direct partial-gravity measurements.', { exact: true }),
  ).toHaveCount(0);
});

test('expired report offers a new export without hidden retries', async ({ page }) => {
  await mode(page, 'report_expired');
  await ready(page, '/reports');
  await page.getByText('Add investigations', { exact: true }).click();
  await page.getByRole('checkbox', { name: 'BASS-II', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'BASS-II', exact: true })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: /BASS-II Solid-material/ })).toBeChecked();
  await page.getByRole('button', { name: 'Prepare PDF', exact: true }).click();
  await expect(
    page.getByText('The report retention period has expired. Prepare a new report.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Prepare another report', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download PDF', exact: true })).toHaveCount(0);
});

for (const [value, label] of [
  ['insufficient_evidence', 'Insufficient evidence'],
  ['conflicting_evidence', 'Conflicting evidence'],
])
  test(`answer state ${value}`, async ({ page }) => {
    await mode(page, value!);
    await ready(page, '/ask');
    await analyse(page);
    await expect(page.getByText(label!, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save answer', exact: true })).toBeVisible();
  });

test('unavailable attachment does not hide the remaining source metadata', async ({ page }) => {
  await ready(page, '/investigations/inv_psi25?tab=materials');
  await expect(page.getByText('File unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /Open original source/ })).toHaveCount(2);
});

test('expired guest session has an explicit recovery path', async ({ page }) => {
  await mode(page, 'session_expired');
  await page.addInitScript(() => localStorage.setItem('fireatlas:has-workspace', '1'));
  await page.goto('/');
  await page.getByRole('button', { name: 'Create guest workspace', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Understand fire in microgravity.', exact: true }),
  ).toBeVisible();
});

test('a late search response cannot replace the newer question', async ({ page }) => {
  await mode(page, 'slow_search');
  await ready(page, '/investigations');
  const question = page.getByRole('textbox', { name: 'Research query', exact: true });
  await question.fill('ventilation');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await question.fill('smoke');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('link', { name: 'SAME-R', exact: true })).toBeVisible();
  await page.waitForTimeout(1100);
  await expect(page.getByRole('link', { name: 'BASS-II', exact: true })).toHaveCount(0);
  await expect(question).toHaveValue('smoke');
});

test('evidence drawer restores keyboard focus to its source control', async ({ page }) => {
  await ready(page, '/investigations/inv_psi25');
  const trigger = page.getByRole('button', { name: 'Open evidence 1', exact: true });
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
});
