import { IS_DEMO } from '../lib/env';
import type { Envelope, Schema } from './types';

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
    public requestId: string | null = null,
    public retryable = false,
    public details: Schema['ErrorDetail'][] = [],
    public retryAfterMs = 0,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
export function retryDelay(value: string | null, now = Date.now()) {
  if (!value) return 0;
  const seconds = Number(value);
  return Number.isFinite(seconds)
    ? Math.max(0, seconds * 1000)
    : Math.max(0, Date.parse(value) - now) || 0;
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 15000,
  responseType: 'json' | 'blob' = 'json',
): Promise<Envelope<T>> {
  const controller = new AbortController();
  const abort = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) abort();
  else options.signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(
    () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
    timeoutMs,
  );
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  if (options.body) headers.set('Content-Type', 'application/json');
  if (options.method && !['GET', 'HEAD'].includes(options.method)) {
    const token = document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrf_token='))
      ?.slice('csrf_token='.length);
    if (token) headers.set('X-CSRF-Token', decodeURIComponent(token));
  }
  if (IS_DEMO) {
    const mock =
      new URLSearchParams(window.location.search).get('mock') ||
      sessionStorage.getItem('fireatlas:mock-scenario');
    if (mock) headers.set('X-FireAtlas-Mock', mock);
  }
  try {
    const response = await fetch(baseUrl + path, {
      ...options,
      headers,
      credentials: 'include',
      signal: controller.signal,
    });
    if (response.status === 204)
      return {
        data: undefined as T,
        meta: {
          request_id: response.headers.get('X-Request-ID') || '',
          contract_version: '1.3.0',
          data_revision: null,
          warnings: [],
        },
      };
    if (response.ok && responseType === 'blob') {
      if (!response.headers.get('Content-Type')?.startsWith('application/pdf'))
        throw new ApiError('INVALID_RESPONSE', 'The server did not return a PDF.', response.status);
      return {
        data: (await response.blob()) as T,
        meta: {
          request_id: response.headers.get('X-Request-ID') || '',
          contract_version: '1.3.0',
          data_revision: null,
          warnings: [],
        },
      };
    }
    let body: Envelope<T> & Partial<Schema['ErrorResponse']>;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        'INVALID_RESPONSE',
        'The server returned an unrecognized response format.',
        response.status,
        response.headers.get('X-Request-ID'),
      );
    }
    if (!response.ok) {
      if (response.status === 401 && !['/workspaces/current', '/workspaces'].includes(path))
        window.dispatchEvent(new Event('fireatlas:session-required'));
      throw new ApiError(
        body.error?.code || 'HTTP_ERROR',
        body.error?.message || 'The request could not be completed.',
        response.status,
        body.meta?.request_id || null,
        body.error?.retryable || false,
        body.error?.details || [],
        retryDelay(response.headers.get('Retry-After')),
      );
    }
    if (!body.meta || !('data' in body))
      throw new ApiError(
        'INVALID_RESPONSE',
        'The response is missing data or metadata.',
        response.status,
      );
    for (const warning of body.meta.warnings)
      window.dispatchEvent(new CustomEvent('fireatlas:warning', { detail: warning.message }));
    return body;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted)
      throw options.signal.reason || new DOMException('Aborted', 'AbortError');
    if (controller.signal.aborted)
      throw new ApiError(
        'REQUEST_TIMEOUT',
        'The server did not respond in time. Your input has been preserved.',
        0,
        null,
        true,
      );
    throw new ApiError(
      'NETWORK_ERROR',
      'Unable to connect to the server. Check your connection and try again.',
      0,
      null,
      true,
    );
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
}
const json = (body: unknown) => JSON.stringify(body);
const revQuery = (revision: string) => `data_revision=${encodeURIComponent(revision)}`;
const entityPath = (collection: string, id: string, revision: string) =>
  `/${collection}/${encodeURIComponent(id)}?${revQuery(revision)}`;
export const api = {
  sourceAssetUrl: (id: string, revision: string) =>
    `${baseUrl}/sources/${encodeURIComponent(id)}/asset?${revQuery(revision)}`,
  config: (signal?: AbortSignal) => request<Schema['Config']>('/config', { signal }),
  workspace: (signal?: AbortSignal) =>
    request<Schema['Workspace']>('/workspaces/current', { signal }),
  createWorkspace: () =>
    request<Schema['Workspace']>('/workspaces', { method: 'POST', body: '{}' }),
  patchWorkspace: (patch: Schema['WorkspacePatch'], revision: number) =>
    request<Schema['Workspace']>('/workspaces/current', {
      method: 'PATCH',
      headers: { 'If-Match': `"${revision}"` },
      body: json(patch),
    }),
  search: (body: Schema['SearchRequest'], signal?: AbortSignal) =>
    request<Schema['SearchResult']>('/search', { method: 'POST', body: json(body), signal }),
  investigation: (id: string, revision: string, signal?: AbortSignal) =>
    request<Schema['InvestigationDetail']>(entityPath('investigations', id, revision), { signal }),
  runs: (id: string, revision: string, cursor: string | null = null, signal?: AbortSignal) =>
    request<Schema['RunPage']>(
      `/investigations/${encodeURIComponent(id)}/runs?${revQuery(revision)}&limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
      { signal },
    ),
  run: (id: string, revision: string, signal?: AbortSignal) =>
    request<Schema['TestRun']>(entityPath('runs', id, revision), { signal }),
  evidence: (id: string, revision: string, signal?: AbortSignal) =>
    request<Schema['EvidenceDetail']>(entityPath('evidence', id, revision), { signal }),
  source: (id: string, revision: string, signal?: AbortSignal) =>
    request<Schema['Source']>(entityPath('sources', id, revision), { signal }),
  measurements: (body: Schema['MeasurementRequest'], signal?: AbortSignal) =>
    request<Schema['MeasurementResponse']>('/measurements/query', {
      method: 'POST',
      body: json(body),
      signal,
    }),
  compare: (body: Schema['ComparisonRequest'], signal?: AbortSignal) =>
    request<Schema['ComparisonResponse']>('/comparisons', {
      method: 'POST',
      body: json(body),
      signal,
    }),
  applicability: (body: Schema['ApplicabilityRequest'], signal?: AbortSignal) =>
    request<Schema['ApplicabilityResult']>('/applicability', {
      method: 'POST',
      body: json(body),
      signal,
    }),
  analyse: (body: Schema['AnalysisRequest'], key: string) =>
    request<Schema['Job']>('/analyses', {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: json(body),
    }),
  job: (id: string, signal?: AbortSignal) =>
    request<Schema['Job']>(`/jobs/${encodeURIComponent(id)}`, { signal }),
  cancelJob: (id: string) => request<void>(`/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  answer: (id: string, signal?: AbortSignal) =>
    request<Schema['AnalysisResult']>(`/answers/${encodeURIComponent(id)}`, { signal }),
  createReport: (body: Schema['ReportRequest'], key: string) =>
    request<Schema['Job']>('/reports', {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: json(body),
    }),
  report: (id: string, signal?: AbortSignal) =>
    request<Schema['Report']>(`/reports/${encodeURIComponent(id)}`, { signal }),
  downloadReport: (path: string) => {
    if (!safeDownloadPath(path))
      return Promise.reject(new ApiError('INVALID_DOWNLOAD_PATH', 'The download link is invalid.'));
    return request<Blob>(
      path.slice('/api/v1'.length),
      { headers: { Accept: 'application/pdf' } },
      15000,
      'blob',
    );
  },
};
export function safeSourceUrl(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}
export function safeDownloadPath(path: string) {
  return /^\/api\/v1\/reports\/[A-Za-z0-9_-]+\/download$/.test(path) ? path : null;
}
