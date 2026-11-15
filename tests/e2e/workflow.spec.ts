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
    .getByRole('textbox', { name: 'Ваш вопрос об исследованиях' })
    .fill('Как вентиляция влияет на горение твёрдых материалов?');
  await page.getByRole('button', { name: 'Исследовать', exact: true }).click();
  await expect(page.getByRole('link', { name: 'BASS-II', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'BASS-II', exact: true }).click();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Сохранено', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'В сравнение', exact: true }).click();
  await expect(page.getByRole('button', { name: 'В сравнении', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Открыть основание 1', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(
    page.getByRole('dialog').getByRole('link', { name: /Открыть первоисточник/ }),
  ).toHaveAttribute('href', 'https://ntrs.nasa.gov/citations/20160000593');
  await page.getByRole('button', { name: 'Закрыть панель', exact: true }).click();
  await page.getByRole('navigation').getByRole('link', { name: 'Измерения', exact: true }).click();
  await page.getByRole('button', { name: 'Выбрать точку 30CAL03', exact: true }).click();
  await expect(page.getByTestId('selected-run-id')).toHaveText('30CAL03');
  await expect(page.getByRole('button', { name: '30CAL03', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByText('1,92 мм', { exact: true })).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Сравнение', exact: true }).click();
  await page.getByRole('button', { name: 'Добавить FLEX в сравнение', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Матрица сравнения исследований' })).toBeVisible();
  await expect(page.getByText(/общая шкала пожарной опасности не обоснована/)).toBeVisible();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Спросить AI AI', exact: true })
    .click();
  const job = await analyse(page);
  const originalUrl = page.url();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Сохранить ответ', exact: true })).toBeVisible();
  expect((await jobData(page, job)).state).toBe('succeeded');
  await page.getByRole('button', { name: 'Сохранить ответ', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ответ сохранён', exact: true })).toBeVisible();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Сценарии миссий', exact: true })
    .click();
  await page
    .getByRole('button', {
      name: 'Лунная база Поверхность Луны · частичная гравитация',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('Прямых данных частичной гравитации в PSI нет.', { exact: true }),
  ).toBeVisible();
  await page.goto(originalUrl);
  await expect(
    page.getByRole('heading', { name: 'Контекст ответа: Орбитальная станция', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Ответ получен на предыдущем снимке пространства/)).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Отчёты', exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Название отчёта', exact: true })
    .fill('Вентиляция: исследования и ограничения');
  await page.getByRole('button', { name: 'Подготовить PDF', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Скачать PDF', exact: true })).toBeEnabled();
  const first = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать PDF', exact: true }).click();
  const downloaded = await first;
  const bytes = await readFile((await downloaded.path())!);
  expect(bytes.subarray(0, 5).toString()).toBe('%PDF-');
  expect(bytes.length).toBeGreaterThan(1000);
  const second = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать PDF', exact: true }).click();
  await second;
  expect(posts.filter((post) => post.path.endsWith('/analyses'))).toHaveLength(1);
  expect(posts.filter((post) => post.path.endsWith('/reports'))).toHaveLength(1);
});

test('hard ranges remain hard when related work is requested', async ({ page }) => {
  await ready(page, '/investigations?o2_min=0.9&o2_max=1');
  await expect(
    page.getByRole('heading', { name: 'Нет исследований с такими условиями' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Показать связанные материалы', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Нет исследований с такими условиями' }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get('o2_min')).toBe('0.9');
});

test('provider failure leaves source access and catalog working', async ({ page }) => {
  await mode(page, 'provider_error');
  await ready(page, '/ask');
  await analyse(page);
  await expect(
    page.getByText('Внешняя модель недоступна. Найденные источники можно открыть.', {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Источник 1', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть панель', exact: true }).click();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Исследования', exact: true })
    .click();
  await expect(page.getByRole('link', { name: 'BASS-II', exact: true })).toBeVisible();
});

test('cancelled job cannot publish a late answer', async ({ page }) => {
  await ready(page, '/ask');
  const id = await analyse(page);
  await page.getByRole('button', { name: 'Отменить задачу', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Отменено', exact: true })).toBeVisible();
  await page.waitForTimeout(3800);
  const job = await jobData(page, id);
  expect(job.state).toBe('cancelled');
  expect(job.result_id).toBeNull();
  await expect(page.getByRole('button', { name: 'Сохранить ответ', exact: true })).toHaveCount(0);
});

test('server timeout ends waiting without starting another analysis', async ({ page }) => {
  await mode(page, 'timeout');
  let count = 0;
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/analyses')) count++;
  });
  await ready(page, '/ask');
  await analyse(page);
  await expect(page.getByRole('heading', { name: 'Истёк срок', exact: true })).toBeVisible();
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
    .getByRole('textbox', { name: 'Вопрос для AI', exact: true })
    .fill('Как влияет вентиляция на пламя?');
  await page.getByRole('button', { name: 'Получить ответ', exact: true }).click();
  await expect(
    page.getByText('Исход предыдущего запроса не подтверждён.', { exact: true }),
  ).toBeVisible();
  await page
    .getByRole('textbox', { name: 'Вопрос для AI', exact: true })
    .fill('Другой вопрос после потери ответа');
  await page.getByRole('button', { name: 'Повторить тот же запрос', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Сохранить ответ', exact: true })).toBeVisible();
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
    await page.getByRole('button', { name: `Добавить ${name} в сравнение`, exact: true }).click();
    await expect(
      page.getByRole('button', { name: `Убрать ${name} в сравнение`, exact: true }),
    ).toBeVisible();
  }
  await page.getByRole('button', { name: 'Добавить DEMO-04 в сравнение', exact: true }).click();
  await expect(page.getByText(/Можно сравнить не более трёх исследований/)).toBeVisible();
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
  await page.getByRole('button', { name: 'Добавить BASS-II в сравнение', exact: true }).click();
  await expect(page.getByText('Рабочий контекст изменился.', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Убрать FLEX в сравнение', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Оставить обновлённый контекст', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Добавить BASS-II в сравнение', exact: true }),
  ).toBeVisible();
});

test('mission presets require an explicit decision before transferring conditions', async ({
  page,
}) => {
  await ready(page, '/missions');
  await page.getByRole('spinbutton', { name: 'Кислород, %', exact: true }).fill('21');
  await page.getByRole('button', { name: 'Применить условия', exact: true }).click();
  await expect(page.getByText('Условия сценария сохранены.', { exact: true })).toBeVisible();
  await page
    .getByRole('button', {
      name: 'Лунная база Поверхность Луны · частичная гравитация',
      exact: true,
    })
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Начать без введённых условий', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: 'Кислород, %', exact: true })).toHaveValue('');
  await page
    .getByRole('button', { name: 'Орбитальная станция Орбита · микрогравитация', exact: true })
    .click();
  await expect(page.getByRole('textbox', { name: 'Название миссии', exact: true })).toHaveValue(
    'Орбитальная станция',
  );
  await expect(
    page.getByText('Прямых данных частичной гравитации в PSI нет.', { exact: true }),
  ).toHaveCount(0);
});

test('expired report offers a new export without hidden retries', async ({ page }) => {
  await mode(page, 'report_expired');
  await ready(page, '/reports');
  await page.getByText('Добавить исследования', { exact: true }).click();
  await page.getByRole('checkbox', { name: 'BASS-II', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'BASS-II', exact: true })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: /BASS-II Горение/ })).toBeChecked();
  await page.getByRole('button', { name: 'Подготовить PDF', exact: true }).click();
  await expect(
    page.getByText('Срок хранения отчёта истёк. Подготовьте новый.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Подготовить другой отчёт', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Скачать PDF', exact: true })).toHaveCount(0);
});

for (const [value, label] of [
  ['insufficient_evidence', 'Недостаточно доказательств'],
  ['conflicting_evidence', 'Есть противоречия'],
])
  test(`answer state ${value}`, async ({ page }) => {
    await mode(page, value!);
    await ready(page, '/ask');
    await analyse(page);
    await expect(page.getByText(label!, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Сохранить ответ', exact: true })).toBeVisible();
  });

test('unavailable attachment does not hide the remaining source metadata', async ({ page }) => {
  await ready(page, '/investigations/inv_psi25?tab=materials');
  await expect(page.getByText('Файл недоступен', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /Открыть первоисточник/ })).toHaveCount(2);
});

test('expired guest session has an explicit recovery path', async ({ page }) => {
  await mode(page, 'session_expired');
  await page.addInitScript(() => localStorage.setItem('fireatlas:has-workspace', '1'));
  await page.goto('/');
  await page.getByRole('button', { name: 'Создать гостевое пространство', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Понять огонь в невесомости.', exact: true }),
  ).toBeVisible();
});

test('a late search response cannot replace the newer question', async ({ page }) => {
  await mode(page, 'slow_search');
  await ready(page, '/investigations');
  const question = page.getByRole('textbox', { name: 'Поисковый вопрос', exact: true });
  await question.fill('вентиляция');
  await page.getByRole('button', { name: 'Найти', exact: true }).click();
  await question.fill('дым');
  await page.getByRole('button', { name: 'Найти', exact: true }).click();
  await expect(page.getByRole('link', { name: 'SAME-R', exact: true })).toBeVisible();
  await page.waitForTimeout(1100);
  await expect(page.getByRole('link', { name: 'BASS-II', exact: true })).toHaveCount(0);
  await expect(question).toHaveValue('дым');
});

test('evidence drawer restores keyboard focus to its source control', async ({ page }) => {
  await ready(page, '/investigations/inv_psi25');
  const trigger = page.getByRole('button', { name: 'Открыть основание 1', exact: true });
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
});
