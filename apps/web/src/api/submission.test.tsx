import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useJobSubmission } from './jobs';
import type { Schema } from './types';
const body = (): Schema['AnalysisRequest'] => ({
  question: 'Влияние вентиляции на горение',
  locale: 'ru',
  workspace_revision: 3,
  data_revision: 'test-r1',
  selected_investigation_ids: [],
  mode: 'evidence_answer',
});
const response = () =>
  new Response(
    JSON.stringify({
      data: { id: 'job_same' },
      meta: {
        request_id: 'req_test',
        contract_version: '1.0.0',
        data_revision: 'test-r1',
        warnings: [],
      },
    }),
    { status: 202 },
  );
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});
it('blocks two submissions in the same render before the button can update', async () => {
  let complete!: (value: Response) => void;
  const fetch = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        complete = resolve;
      }),
  );
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(() =>
    useJobSubmission<Schema['AnalysisRequest']>('analysis', 'ws_1'),
  );
  await act(async () => {
    const first = result.current.start(body());
    const second = result.current.start(body());
    complete(response());
    await Promise.all([first, second]);
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(result.current.pending).toBeNull();
});
it('replays the original key and body after a lost response', async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new TypeError('Lost response'))
    .mockResolvedValueOnce(response());
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(() =>
    useJobSubmission<Schema['AnalysisRequest']>('analysis', 'ws_1'),
  );
  const original = body();
  await act(async () => {
    await result.current.start(original);
  });
  original.question = 'Другой вопрос после ошибки';
  await act(async () => {
    await result.current.retry();
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  const first = fetch.mock.calls[0]![1],
    second = fetch.mock.calls[1]![1];
  expect(first.headers.get('Idempotency-Key')).toBe(second.headers.get('Idempotency-Key'));
  expect(first.body).toBe(second.body);
  expect(JSON.parse(second.body).question).toBe('Влияние вентиляции на горение');
});
