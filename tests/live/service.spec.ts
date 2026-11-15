import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { analyse, ready } from '../e2e/helpers';

test('NASA corpus → evidence → measurements → comparison → answer → Moon → real PDF', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await ready(page);
  await expect(page.getByText('DEMO', { exact: true })).toHaveCount(0);
  await page
    .getByRole('textbox', { name: 'Your research question' })
    .fill('How does ventilation affect the combustion of solid materials?');
  await page.getByRole('button', { name: 'Explore', exact: true }).click();
  await page.getByRole('link', { name: 'BASS-II', exact: true }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add to comparison', exact: true }).click();
  await expect(page.getByRole('button', { name: 'In comparison', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Open evidence 1', exact: true }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(
    page.getByRole('dialog').getByRole('link', { name: /Open original source/ }),
  ).toHaveAttribute('href', /^https:\/\//);
  await page.getByRole('button', { name: 'Close panel', exact: true }).click();
  await ready(page, '/measurements');
  const tablePoint = page.getByRole('button', { name: '30CAL03', exact: true });
  await tablePoint.click();
  await expect(page.getByTestId('selected-run-id')).toHaveText('30CAL03');
  await expect(page.getByText('1.92 mm', { exact: true })).toBeVisible();
  await expect(page.getByText('6.34 s', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Evidence 1', exact: true }).click();
  const sourceDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: /Download source file/ }).click();
  const sourceFile = await sourceDownload;
  expect((await readFile((await sourceFile.path())!)).byteLength).toBeGreaterThan(100);
  await page.getByRole('button', { name: 'Close panel', exact: true }).click();
  await ready(page, '/compare');
  await page.getByRole('button', { name: 'Add FLEX to comparison', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Investigation comparison matrix' })).toBeVisible();
  await ready(page, '/ask');
  await analyse(page);
  const original = page.url();
  await page.reload();
  await page.getByRole('button', { name: 'Save answer', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Answer saved', exact: true })).toBeVisible();
  await ready(page, '/missions');
  await page
    .getByRole('button', {
      name: 'Lunar base Lunar surface · partial gravity',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('PSI contains no direct partial-gravity measurements.', { exact: true }),
  ).toBeVisible();
  await page.goto(original);
  await expect(
    page.getByRole('heading', { name: 'Answer context: Orbital station', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/This answer uses an earlier workspace snapshot/)).toBeVisible();
  await ready(page, '/reports');
  await page
    .getByRole('textbox', { name: 'Report title', exact: true })
    .fill('NASA integration verification');
  await page.getByRole('button', { name: /Prepare PDF/ }).click();
  const pdfDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: /Download PDF/ }).click();
  const downloaded = await pdfDownload;
  await downloaded.saveAs('test-results/live/fire-atlas-english-report.pdf');
  const pdf = await readFile((await downloaded.path())!);
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
  expect(pdf.length).toBeGreaterThan(20000);
  await page.reload();
  await expect(page.getByRole('button', { name: /Download PDF/ })).toBeVisible();
  expect(errors).toEqual([]);
});

for (const width of [360, 768, 1280, 1920]) {
  test(`real API screens and accessibility at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    for (const path of [
      '/',
      '/investigations',
      '/investigations/inv_psi25_bass2',
      '/measurements',
      '/compare',
      '/missions',
      '/ask',
      '/reports',
    ]) {
      await ready(page, path);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      expect(
        result.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
      ).toEqual([]);
      await page.screenshot({
        path: `test-results/live/${path.replaceAll('/', '_') || 'overview'}-${width}.png`,
        fullPage: true,
      });
    }
    expect(errors).toEqual([]);
    await page.screenshot({ path: `test-results/live/service-${width}.png`, fullPage: true });
  });
}

test('workspace conflict refreshes context and preserves the pending edit', async ({ page }) => {
  await ready(page, '/investigations');
  await page.evaluate(async () => {
    const workspace = (await (await fetch('/api/v1/workspaces/current')).json()).data;
    const response = await fetch('/api/v1/workspaces/current', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'If-Match': `"${workspace.revision}"` },
      body: JSON.stringify({ saved_investigation_ids: ['inv_psi69_flex'] }),
    });
    if (!response.ok) throw new Error(`Workspace update failed: ${response.status}`);
  });
  await page.getByRole('button', { name: 'Save BASS-II', exact: true }).click();
  await expect(page.getByText('The workspace context has changed.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Apply my selection', exact: true }).click();
  await expect(page.getByText('The workspace context has changed.', { exact: true })).toHaveCount(
    0,
  );
  await page.reload();
  await expect(page.getByRole('button', { name: /Remove from saved BASS-II/ })).toBeVisible();
});

test('a cleared scenario remains usable and can be replaced with a mission preset', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await ready(page, '/ask');
  await page.evaluate(async () => {
    const workspace = (await (await fetch('/api/v1/workspaces/current')).json()).data;
    const response = await fetch('/api/v1/workspaces/current', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'If-Match': `"${workspace.revision}"` },
      body: JSON.stringify({ scenario: null }),
    });
    if (!response.ok) throw new Error(`Clear scenario: ${response.status}`);
  });
  await page.reload();
  await expect(page.getByText('No scenario', { exact: true }).first()).toBeVisible();
  await ready(page, '/missions');
  await expect(
    page.getByText('Choose a mission preset to assess applicability.', { exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', {
      name: 'Lunar base Lunar surface · partial gravity',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('PSI contains no direct partial-gravity measurements.', { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
