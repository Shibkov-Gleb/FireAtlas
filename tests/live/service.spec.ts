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
  await expect(page.getByText('ДЕМО', { exact: true })).toHaveCount(0);
  await page
    .getByRole('textbox', { name: 'Ваш вопрос об исследованиях' })
    .fill('Как вентиляция влияет на горение твердых материалов?');
  await page.getByRole('button', { name: 'Исследовать', exact: true }).click();
  await page.getByRole('link', { name: 'BASS-II', exact: true }).click();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Сохранено', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'В сравнение', exact: true }).click();
  await expect(page.getByRole('button', { name: 'В сравнении', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Открыть основание 1', exact: true }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(
    page.getByRole('dialog').getByRole('link', { name: /Открыть первоисточник/ }),
  ).toHaveAttribute('href', /^https:\/\//);
  await page.getByRole('button', { name: 'Закрыть панель', exact: true }).click();
  await ready(page, '/measurements');
  const tablePoint = page.getByRole('button', { name: '30CAL03', exact: true });
  await tablePoint.click();
  await expect(page.getByTestId('selected-run-id')).toHaveText('30CAL03');
  await expect(page.getByText('1,92 мм', { exact: true })).toBeVisible();
  await expect(page.getByText('6,34 с', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Основание 1', exact: true }).click();
  const sourceDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: /Скачать файл источника/ }).click();
  const sourceFile = await sourceDownload;
  expect((await readFile((await sourceFile.path())!)).byteLength).toBeGreaterThan(100);
  await page.getByRole('button', { name: 'Закрыть панель', exact: true }).click();
  await ready(page, '/compare');
  await page.getByRole('button', { name: 'Добавить FLEX в сравнение', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Матрица сравнения исследований' })).toBeVisible();
  await ready(page, '/ask');
  await analyse(page);
  const original = page.url();
  await page.reload();
  await page.getByRole('button', { name: 'Сохранить ответ', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ответ сохранён', exact: true })).toBeVisible();
  await ready(page, '/missions');
  await page
    .getByRole('button', {
      name: 'Лунная база Поверхность Луны · частичная гравитация',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('Прямых данных частичной гравитации в PSI нет.', { exact: true }),
  ).toBeVisible();
  await page.goto(original);
  await expect(
    page.getByRole('heading', { name: 'Контекст ответа: Орбитальная станция', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Ответ получен на предыдущем снимке пространства/)).toBeVisible();
  await ready(page, '/reports');
  await page
    .getByRole('textbox', { name: 'Название отчёта', exact: true })
    .fill('Интеграционная проверка NASA');
  await page.getByRole('button', { name: /Подготовить PDF/ }).click();
  const pdfDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: /Скачать PDF/ }).click();
  const pdf = await readFile((await (await pdfDownload).path())!);
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
  expect(pdf.length).toBeGreaterThan(20000);
  await page.reload();
  await expect(page.getByRole('button', { name: /Скачать PDF/ })).toBeVisible();
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
  await page.getByRole('button', { name: 'Сохранить BASS-II', exact: true }).click();
  await expect(page.getByText('Рабочий контекст изменился.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Применить мой выбор', exact: true }).click();
  await expect(page.getByText('Рабочий контекст изменился.', { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('button', { name: /Убрать из сохранённых BASS-II/ })).toBeVisible();
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
  await expect(page.getByText('Без сценария', { exact: true }).first()).toBeVisible();
  await ready(page, '/missions');
  await expect(
    page.getByText('Выберите пресет миссии для оценки применимости.', { exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', {
      name: 'Лунная база Поверхность Луны · частичная гравитация',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('Прямых данных частичной гравитации в PSI нет.', { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
