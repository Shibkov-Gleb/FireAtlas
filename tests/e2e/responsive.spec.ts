import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { ready } from './helpers';
const routes = [
  ['overview', '/'],
  ['catalog', '/investigations'],
  ['investigation', '/investigations/inv_psi25'],
  ['measurements', '/measurements'],
  ['compare', '/compare'],
  ['ask', '/ask'],
  ['missions', '/missions'],
  ['reports', '/reports'],
] as const;
for (const width of [360, 768, 1280, 1920])
  test(`all eight screens at ${width}px`, async ({ page }, testInfo) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width, height: 900 });
    for (const [name, path] of routes) {
      await ready(page, path);
      if (name === 'measurements') {
        await page.getByRole('button', { name: 'Выбрать точку 30CAL03', exact: true }).click();
        await expect(page.getByTestId('selected-run-id')).toHaveText('30CAL03');
      }
      if (name === 'compare') {
        for (const inv of ['BASS-II', 'FLEX']) {
          await page
            .getByRole('button', { name: `Добавить ${inv} в сравнение`, exact: true })
            .click();
          await expect(
            page.getByRole('button', { name: `Убрать ${inv} в сравнение`, exact: true }),
          ).toBeVisible();
        }
        await expect(
          page.getByRole('region', { name: 'Матрица сравнения исследований' }),
        ).toBeVisible();
      }
      await page.evaluate(() => document.fonts.ready.then(() => undefined));
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow, `${name} page overflow at ${width}px`).toBeLessThanOrEqual(1);
      if (width === 360 || width === 1280) {
        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
          .analyze();
        expect(
          results.violations,
          JSON.stringify(
            results.violations.map((v) => ({
              id: v.id,
              nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })),
            })),
            null,
            2,
          ),
        ).toEqual([]);
      }
      await page.screenshot({ path: testInfo.outputPath(`${name}-${width}.png`), fullPage: true });
    }
  });
test('mobile menu traps focus, closes with Escape and restores its trigger', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await ready(page);
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'Перейти к содержимому', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();
  const menu = page.getByRole('button', { name: 'Открыть меню', exact: true });
  await menu.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab');
    expect(
      await page
        .getByRole('dialog')
        .evaluate((element) => element.contains(document.activeElement)),
    ).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
