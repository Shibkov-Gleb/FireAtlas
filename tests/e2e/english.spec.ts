import { test, expect } from '@playwright/test';
import { ready, englishUI } from './helpers';

test.use({ locale: 'ru-RU' });

test('system validation stays English even when the browser locale is Russian', async ({
  page,
}) => {
  await ready(page);
  await page.getByRole('button', { name: 'Explore', exact: true }).click();
  await expect(
    page.getByText('Enter a question of at least 3 characters or select a research area.', {
      exact: true,
    }),
  ).toBeVisible();
  await ready(page, '/ask');
  await page.getByRole('button', { name: 'Get answer', exact: true }).click();
  await expect(
    page.getByText('Enter a question with 3 to 2000 characters.', { exact: true }),
  ).toBeVisible();
  await ready(page, '/missions');
  await page.getByRole('textbox', { name: 'Mission name', exact: true }).fill('');
  await page.getByRole('button', { name: 'Apply conditions', exact: true }).click();
  await expect(
    page.getByText('The mission name must contain 3 to 100 characters.', { exact: true }),
  ).toBeVisible();
  await englishUI(page);
});
