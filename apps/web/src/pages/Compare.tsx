import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Check, GitCompareArrows, X } from 'lucide-react';
import { api } from '../api/client';
import { useInvestigationOptions } from '../api/hooks';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, Button, EmptyState, Loading, Notice, PageHeader, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { ApplicabilityView } from '../components/ApplicabilityView';
import s from './Compare.module.css';

export function Compare() {
  const { workspace, toggleComparison, pending } = useWorkspace();
  const options = useInvestigationOptions();
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const ids = workspace.selected_investigation_ids;
  const query = useQuery({
    queryKey: ['comparison', ids, workspace.data_revision, workspace.scenario],
    queryFn: ({ signal }) =>
      api
        .compare(
          {
            investigation_ids: ids,
            data_revision: workspace.data_revision,
            scenario: workspace.scenario,
          },
          signal,
        )
        .then((r) => r.data),
    enabled: ids.length >= 2,
  });
  const data = query.data;
  return (
    <>
      <PageHeader
        eyebrow="COMPARISON / METHODS AND CONDITIONS"
        title="Compare investigations"
        description="Start with goals and methods. Numerical results can only be combined when metric definitions are compatible."
        action={
          <Badge tone="cyan">
            <GitCompareArrows size={12} /> {ids.length}/3 selected
          </Badge>
        }
      />
      <Panel className={s.selection}>
        <div className="spaceBetween">
          <h2>Select two or three investigations</h2>
          <span className="tiny muted">Your selection is saved in the workspace</span>
        </div>
        {options.isPending ? (
          <Loading />
        ) : options.isError ? (
          <ErrorState error={options.error} onRetry={() => void options.refetch()} />
        ) : (
          <div className={s.options}>
            {options.data.map((inv) => (
              <button
                key={inv.id}
                className={`${s.option} ${ids.includes(inv.id) ? s.selected : ''}`}
                aria-pressed={ids.includes(inv.id)}
                aria-label={`${ids.includes(inv.id) ? 'Remove' : 'Add'} ${inv.acronym} to comparison`}
                disabled={pending}
                onClick={() => void toggleComparison(inv.id)}
              >
                <span>
                  <strong>{inv.acronym}</strong>
                  <small>{inv.psi_id}</small>
                </span>
                {ids.includes(inv.id) ? <Check size={16} /> : <span className={s.plus}>+</span>}
              </button>
            ))}
          </div>
        )}
      </Panel>
      {ids.length < 2 ? (
        <EmptyState
          title="At least two investigations are required"
          action={
            <Link className="textLink" to="/investigations">
              Open catalog <ArrowRight size={13} />
            </Link>
          }
        >
          Select cards above or add investigations from the catalog.
        </EmptyState>
      ) : query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        data && (
          <div className="stack">
            <div className="inline">
              {data.investigations.map((inv) => (
                <Badge key={inv.id} tone="cyan">
                  {inv.acronym}
                  <button
                    className="iconButton"
                    aria-label={`Remove ${inv.acronym}`}
                    onClick={() => void toggleComparison(inv.id)}
                  >
                    <X size={12} />
                  </button>
                </Badge>
              ))}
            </div>
            <div
              className={`${s.matrix} tableScroll`}
              tabIndex={0}
              role="region"
              aria-label="Investigation comparison matrix"
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">Attribute</th>
                    {data.investigations.map((inv) => (
                      <th scope="col" key={inv.id}>
                        <Link to={`/investigations/${inv.id}`}>{inv.acronym}</Link>
                        <small>{inv.psi_id}</small>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.field}>
                      <th scope="row">{row.label}</th>
                      {data.investigations.map((inv) => {
                        const cell = row.cells.find((c) => c.investigation_id === inv.id);
                        return (
                          <td key={inv.id}>
                            <p>
                              {!cell
                                ? 'Not reported'
                                : cell.status === 'not_applicable'
                                  ? 'Not applicable'
                                  : cell.status === 'not_reported'
                                    ? 'Not reported'
                                    : cell.value_text}
                            </p>
                            {cell?.evidence_ids.map((id, index) => (
                              <button
                                key={id}
                                className="textLink"
                                onClick={() => setEvidenceId(id)}
                              >
                                Evidence {index + 1}
                              </button>
                            ))}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.comparability.reasons.map((reason) => (
              <Notice key={`${reason.code}:${reason.field}`} tone="warning">
                {reason.text}
              </Notice>
            ))}
            {data.limitations.map((text) => (
              <p className="tiny muted" key={text}>
                {text}
              </p>
            ))}
            <ApplicabilityView
              result={data.applicability}
              partial={['partial', 'simulated_partial'].includes(
                workspace.scenario?.gravity_regime ?? '',
              )}
              onEvidence={setEvidenceId}
            />
            <div className="spaceBetween">
              <span className="tiny muted">
                Relevance ranking is not an assessment of fire hazard.
              </span>
              <Link className="textLink" to="/ask">
                Ask about the selected studies <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        )
      )}
      <EvidenceDrawer
        id={evidenceId}
        revision={workspace.data_revision}
        onClose={() => setEvidenceId(null)}
      />
    </>
  );
}
