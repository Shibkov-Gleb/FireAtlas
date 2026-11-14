import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request, retryDelay, safeDownloadPath, safeSourceUrl } from './client';

afterEach(() => vi.unstubAllGlobals());
describe('API transport', () => {
  it('preserves backend diagnostic information', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'WORKSPACE_CONFLICT',
              message: 'Контекст изменился',
              retryable: false,
              details: [
                { field: 'workspace_revision', reason: 'stale_revision', current_revision: 4 },
              ],
            },
            meta: { request_id: 'req_test' },
          }),
          { status: 409 },
        ),
      ),
    );
    await expect(request('/workspaces/current')).rejects.toMatchObject({
      code: 'WORKSPACE_CONFLICT',
      requestId: 'req_test',
      details: [{ current_revision: 4, field: 'workspace_revision', reason: 'stale_revision' }],
    });
  });
  it('does not turn an aborted reading into a network error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url, options) =>
          new Promise((_resolve, reject) =>
            options.signal.addEventListener('abort', () => reject(options.signal.reason)),
          ),
      ),
    );
    const controller = new AbortController();
    const result = request('/search', { signal: controller.signal });
    controller.abort();
    await expect(result).rejects.toMatchObject({ name: 'AbortError' });
  });
  it('handles empty successful cancellation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    expect((await request<void>('/jobs/test', { method: 'DELETE' })).data).toBeUndefined();
  });
  it('reports malformed responses without leaking the body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>internal details</html>', { status: 502 })),
    );
    await expect(request('/config')).rejects.toBeInstanceOf(ApiError);
  });
  it('downloads PDF without expecting a JSON envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('%PDF-1.7 demo', { headers: { 'Content-Type': 'application/pdf' } }),
        ),
    );
    expect((await request<Blob>('/reports/rpt_1/download', {}, 15000, 'blob')).data.type).toBe(
      'application/pdf',
    );
  });
  it('keeps structured expiration errors on binary downloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'RESOURCE_EXPIRED',
              message: 'Срок истёк',
              retryable: false,
              details: [],
            },
            meta: { request_id: 'req_download' },
          }),
          { status: 410, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );
    await expect(request('/reports/rpt_1/download', {}, 15000, 'blob')).rejects.toMatchObject({
      code: 'RESOURCE_EXPIRED',
      status: 410,
      requestId: 'req_download',
    });
  });
});
it('supports seconds and HTTP dates for Retry-After', () => {
  expect(retryDelay('2')).toBe(2000);
  expect(retryDelay('Thu, 01 Jan 1970 00:00:03 GMT', 1000)).toBe(2000);
});
it('accepts only registered-source HTTPS links and internal report paths', () => {
  expect(safeSourceUrl('javascript:alert(1)')).toBeNull();
  expect(safeSourceUrl('https://ntrs.nasa.gov/citations/20160000593')).toContain('ntrs.nasa.gov');
  expect(safeDownloadPath('//evil.example/report')).toBeNull();
  expect(safeDownloadPath('/api/v1/reports/rpt_1/download')).toBe('/api/v1/reports/rpt_1/download');
});
