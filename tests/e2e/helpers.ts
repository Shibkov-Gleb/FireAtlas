import { expect, type Page } from '@playwright/test';
export async function ready(page: Page, path = '/') {
  await page.goto(path);
  await expect(page.locator('#main')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForFunction(
    () =>
      !Array.from(document.querySelectorAll('[role=status]')).some((element) =>
        /Loading|Opening|Checking|Assessing|Restoring/.test(element.textContent ?? ''),
      ),
  );
  await englishUI(page);
}
export async function englishUI(page: Page) {
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  const copy = await page
    .locator('body')
    .evaluate((body) =>
      [
        body.innerText,
        ...Array.from(body.querySelectorAll('[aria-label], [title], [placeholder]')).flatMap(
          (element) =>
            ['aria-label', 'title', 'placeholder'].map(
              (attribute) => element.getAttribute(attribute) ?? '',
            ),
        ),
      ].join('\n'),
    );
  expect(copy, 'All visible system text and accessible labels must be English').not.toMatch(
    /[\u0400-\u04ff]/u,
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
  question = 'How does ventilation affect the combustion of solid materials?',
) {
  await page.getByRole('textbox', { name: 'Question for AI', exact: true }).fill(question);
  await page.getByRole('button', { name: 'Get answer', exact: true }).click();
  await expect(page).toHaveURL(/job=job_/);
  return new URL(page.url()).searchParams.get('job')!;
}
export async function jobData(page: Page, id: string) {
  return page.evaluate(async (id) => (await (await fetch(`/api/v1/jobs/${id}`)).json()).data, id);
}
