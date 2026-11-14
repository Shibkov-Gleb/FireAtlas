import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiError } from './client';
import { isTerminal, type Job, type Schema } from './types';

export function pollInterval(
  job: Job | undefined,
  failures = 0,
  now = Date.now(),
  retryAfterMs = 0,
): number | false {
  if (job && (isTerminal(job.state) || now >= Date.parse(job.deadline_at))) return false;
  const interval = failures
    ? Math.min(5000, 1000 * 2 ** Math.min(failures, 3))
    : !job || now - Date.parse(job.created_at) < 10000
      ? 1000
      : 2000;
  // Explicit server rate limits take precedence over the network-error backoff cap.
  return Math.max(interval, retryAfterMs);
}
export function useJob(id: string | null) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: ({ signal }) => api.job(id!, signal),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.error instanceof ApiError && !query.state.error.retryable
        ? false
        : pollInterval(
            query.state.data?.data,
            query.state.fetchFailureCount,
            Date.now(),
            query.state.error instanceof ApiError ? query.state.error.retryAfterMs : 0,
          ),
    refetchOnMount: 'always',
  });
}
export type PendingAction<T> = { key: string; body: T; workspaceId: string; created: number };
function readPending<T>(key: string): PendingAction<T> | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null');
    return value &&
      typeof value.key === 'string' &&
      typeof value.created === 'number' &&
      typeof value.workspaceId === 'string' &&
      value.body
      ? value
      : null;
  } catch {
    return null;
  }
}
export function useJobSubmission<T extends Schema['AnalysisRequest'] | Schema['ReportRequest']>(
  type: 'analysis' | 'report',
  workspaceId: string,
) {
  const storageKey = `fireatlas:pending:${type}`;
  const [pending, setPending] = useState<PendingAction<T> | null>(() => readPending<T>(storageKey));
  const pendingRef = useRef(pending);
  const busyRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  function discard() {
    sessionStorage.removeItem(storageKey);
    pendingRef.current = null;
    setPending(null);
    setError(null);
  }
  async function execute(action: PendingAction<T>) {
    if (busyRef.current) return null;
    if (action.workspaceId !== workspaceId) {
      setError(
        new ApiError(
          'WORKSPACE_CHANGED',
          'Этот запрос относится к другому гостевому пространству. Начните новое действие.',
        ),
      );
      return null;
    }
    if (Date.now() - action.created >= 86400000) {
      setError(
        new ApiError(
          'IDEMPOTENCY_EXPIRED',
          'Срок ключа повтора истёк. Автоматически повторять запрос нельзя.',
        ),
      );
      return null;
    }
    busyRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const result =
        type === 'analysis'
          ? await api.analyse(action.body as Schema['AnalysisRequest'], action.key)
          : await api.createReport(action.body as Schema['ReportRequest'], action.key);
      discard();
      return result.data;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      busyRef.current = false;
      setSubmitting(false);
    }
  }
  async function start(body: T) {
    if (busyRef.current) return null;
    if (pendingRef.current) {
      setError(
        new ApiError(
          'PENDING_ACTION',
          'Сначала повторите незавершённый запрос или явно начните новое действие.',
        ),
      );
      return null;
    }
    const action = {
      key: crypto.randomUUID(),
      body: structuredClone(body),
      workspaceId,
      created: Date.now(),
    };
    sessionStorage.setItem(storageKey, JSON.stringify(action));
    pendingRef.current = action;
    setPending(action);
    return execute(action);
  }
  return {
    pending,
    submitting,
    error,
    start,
    retry: () => (pending ? execute(pending) : Promise.resolve(null)),
    discard,
  };
}
