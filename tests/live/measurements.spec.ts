import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { ready } from '../e2e/helpers';

test('FLEX defaults to five controls and exposes the real corpus separately', async ({ page }) => {
  for (const width of [360, 768, 1280, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await ready(page, '/measurements');
    const table = page.getByRole('region', { name: 'FLEX measurements table', exact: true });
    await expect(table.locator('tbody tr')).toHaveCount(5);
    await expect(table.getByRole('button', { name: '30CAL03', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()).violations,
    ).toEqual([]);
    await page.screenshot({ path: `test-results/live/flex-control-${width}.png`, fullPage: true });
  }
  await page.getByRole('combobox', { name: 'Dataset', exact: true }).selectOption('all');
  const rows = page
    .getByRole('region', { name: 'FLEX measurements table', exact: true })
    .locator('tbody tr');
  await expect.poll(() => rows.count()).toBeGreaterThan(5);
  expect(new URL(page.url()).searchParams.get('series')).toBe('all');
  await page.getByRole('combobox', { name: 'Dataset', exact: true }).selectOption('control');
  await expect(rows).toHaveCount(5);
});
