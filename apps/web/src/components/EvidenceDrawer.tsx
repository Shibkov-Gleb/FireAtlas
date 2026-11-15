import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, FileText, Link2 } from 'lucide-react';
import { api, safeSourceUrl } from '../api/client';
import type { Source } from '../api/types';
import { Drawer } from './Drawer';
import { Badge, Loading, Notice } from './ui';
import { ErrorState } from './ErrorState';
import s from './EvidenceDrawer.module.css';

export function SourceCard({ source }: { source: Source }) {
  const url = safeSourceUrl(source.canonical_url);
  return (
    <article className={s.source}>
      <div className={s.sourceTop}>
        <FileText size={18} />
        <Badge tone={source.availability === 'unavailable' ? 'orange' : 'cyan'}>
          {source.availability === 'unavailable'
            ? 'File unavailable'
            : source.availability === 'metadata_only'
              ? 'Metadata only'
              : 'Source'}
        </Badge>
      </div>
      <h3>{source.title}</h3>
      <p className="tiny muted">
        {source.kind} · {source.data_revision}
      </p>
      {source.doi && <p className="tiny wordBreak">DOI: {source.doi}</p>}
      {source.local_asset_id && source.availability === 'available' && (
        <a className="textLink" href={api.sourceAssetUrl(source.id, source.data_revision)}>
          Download source file <FileText size={14} />
        </a>
      )}
      {source.availability === 'unavailable' && (
        <p className="tiny muted">
          The attachment is unavailable. Its metadata and landing page remain accessible.
        </p>
      )}
      {url ? (
        <a className="textLink" href={url} target="_blank" rel="noopener noreferrer">
          Open original source <ArrowUpRight size={14} />
          <span className="srOnly">in a new tab</span>
        </a>
      ) : (
        <Notice tone="warning">The source link is unavailable.</Notice>
      )}
    </article>
  );
}
export function EvidenceDrawer({
  id,
  revision,
  onClose,
}: {
  id: string | null;
  revision: string;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ['evidence', id, revision],
    queryFn: ({ signal }) => api.evidence(id!, revision, signal).then((r) => r.data),
    enabled: !!id,
    staleTime: Infinity,
  });
  const data = query.data;
  return (
    <Drawer
      open={!!id}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Supporting evidence"
      description="Check the source, exact location and original data."
    >
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        data && (
          <div className="stack">
            <div className="inline">
              <Badge tone={data.evidence.verified ? 'teal' : 'orange'}>
                {data.evidence.verified
                  ? 'Verified record'
                  : 'Not verified for the scientific release'}
              </Badge>
              <span className="tiny mono muted">{data.evidence.kind}</span>
            </div>
            {!data.evidence.verified && (
              <Notice tone="warning">
                Demo record. This evidence has not undergone scientific acceptance.
              </Notice>
            )}
            <div className={s.locator}>
              <Link2 size={15} />
              <span>
                {[
                  data.evidence.locator.page !== null ? `Page ${data.evidence.locator.page}` : null,
                  data.evidence.locator.section,
                  data.evidence.locator.row_key ? `Record ${data.evidence.locator.row_key}` : null,
                  data.evidence.locator.start_s !== null
                    ? `${data.evidence.locator.start_s}–${data.evidence.locator.end_s} s`
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ') || 'Location not reported'}
              </span>
            </div>
            {data.evidence.excerpt && (
              <blockquote className={s.excerpt}>{data.evidence.excerpt}</blockquote>
            )}
            {data.evidence.table_values.length > 0 && (
              <div
                className="tableScroll"
                tabIndex={0}
                role="region"
                aria-label="Original evidence row"
              >
                <table>
                  <caption className="srOnly">Original values and units</caption>
                  <thead>
                    <tr>
                      <th scope="col">Field</th>
                      <th scope="col">Value</th>
                      <th scope="col">Unit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.evidence.table_values.map((cell, index) => (
                      <tr key={index}>
                        <th scope="row">{cell.field}</th>
                        <td className="mono">{cell.raw_value}</td>
                        <td>{cell.raw_unit ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {data.evidence.verification_note && (
              <p className="tiny muted">{data.evidence.verification_note}</p>
            )}
            <SourceCard source={data.source} />
            <details className={s.raw}>
              <summary>Original API record</summary>
              <pre>{JSON.stringify(data.evidence, null, 2)}</pre>
            </details>
          </div>
        )
      )}
    </Drawer>
  );
}
