import { expect, type Page } from '@playwright/test';
export async function ready(page: Page, path = '/') {
  await page.goto(path);
  await expect(page.locator('#main')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForFunction(
    () =>
      !Array.from(document.querySelectorAll('[role=status]')).some((element) =>
        /Загружаем|Открываем|Проверяем|Восстанавливаем/.test(element.textContent ?? ''),
      ),
  );
}
export async function mode(page: Page, value: string) {
  await page.addInitScript(
    (value) => sessionStorage.setItem('fireatlas:mock-scenario', value),
    value,
  );
}
export async function analyse(
  page: Page,
  question = 'Как вентиляция влияет на горение твёрдых материалов?',
) {
  await page.getByRole('textbox', { name: 'Вопрос для AI', exact: true }).fill(question);
  await page.getByRole('button', { name: 'Получить ответ', exact: true }).click();
  await expect(page).toHaveURL(/job=job_/);
  return new URL(page.url()).searchParams.get('job')!;
}
export async function jobData(page: Page, id: string) {
  return page.evaluate(async (id) => (await (await fetch(`/api/v1/jobs/${id}`)).json()).data, id);
}
