import { useQuery } from '@tanstack/react-query';
import { X, ArrowUpRight } from 'lucide-react';
import { api } from '../api/client';
import type { Quantity } from '../api/types';
import { formatQuantity, geometryLabels, outcomeLabels, statusLabels } from '../lib/format';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, EmptyState, Loading, Notice, Panel } from './ui';
import { ErrorState } from './ErrorState';
import s from './RunPanel.module.css';

export function QuantityValue({
  quantity,
  expectedUnit,
  compact = false,
}: {
  quantity: Quantity;
  expectedUnit?: Quantity['unit'];
  compact?: boolean;
}) {
  const text = formatQuantity(quantity, expectedUnit);
  if (compact)
    return (
      <span
        title={
          quantity.raw_value === null
            ? statusLabels[quantity.status]
            : `Source: ${quantity.raw_value} ${quantity.raw_unit ?? ''}`
        }
      >
        {text}
      </span>
    );
  return (
    <div className={s.quantity}>
      <span className={quantity.value === null ? s.unknown : ''}>{text}</span>
      {quantity.status === 'derived' && <small>Derived · {quantity.derivation?.formula_id}</small>}
      {quantity.raw_value !== null && (
        <details>
          <summary>Original value</summary>
          <div>
            {quantity.raw_value} {quantity.raw_unit ?? ''}
            <br />
            <span>{statusLabels[quantity.status]}</span>
          </div>
        </details>
      )}
    </div>
  );
}
export function RunPanel({
  runId,
  revision,
  onEvidence,
  onClose,
  investigationId,
}: {
  runId: string | null;
  revision: string;
  onEvidence: (id: string) => void;
  onClose?: () => void;
  investigationId?: string;
}) {
  const { config } = useWorkspace();
  const query = useQuery({
    queryKey: ['run', runId, revision],
    queryFn: ({ signal }) => api.run(runId!, revision, signal).then((r) => r.data),
    enabled: !!runId,
    staleTime: Infinity,
  });
  if (!runId)
    return (
      <EmptyState title="Select a test run">
        Select a table row or chart point to view the conditions.
      </EmptyState>
    );
  if (query.isPending)
    return (
      <Panel>
        <Loading />
      </Panel>
    );
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const run = query.data;
  if (investigationId && run.investigation_id !== investigationId)
    return (
      <Notice tone="warning">The selected record belongs to a different investigation.</Notice>
    );
  const conditions = [
    ['Oxygen fraction', run.conditions.oxygen_fraction, 'fraction'],
    ['Nitrogen fraction', run.conditions.nitrogen_fraction, 'fraction'],
    ['CO₂ fraction', run.conditions.co2_fraction, 'fraction'],
    ['Helium fraction', run.conditions.helium_fraction, 'fraction'],
    ['Total pressure', run.conditions.pressure, 'Pa'],
    ['Calibrated airflow speed', run.conditions.airflow_speed, 'm_s'],
    ['Temperature', run.conditions.ambient_temperature, 'K'],
    ['Gravity level', run.conditions.gravity_level, 'g_fraction'],
  ] as const;
  return (
    <Panel className={s.panel}>
      <div className="spaceBetween">
        <span className={s.label}>SELECTED TEST RUN</span>
        {onClose && (
          <button className="iconButton" onClick={onClose} aria-label="Clear selected test run">
            <X size={16} />
          </button>
        )}
      </div>
      <h2 data-testid="selected-run-id">{run.source_test_id}</h2>
      <div className="inline">
        <Badge tone={run.terminal_outcome.category === 'disruption' ? 'orange' : 'cyan'}>
          {outcomeLabels[run.terminal_outcome.category]}
        </Badge>
      </div>
      <p className={s.rawOutcome}>
        Original outcome: <span>{run.terminal_outcome.raw_label}</span>
      </p>
      <div className={s.section}>
        <h3>Sample</h3>
        <dl>
          <div>
            <dt>Material</dt>
            <dd>
              {config.dictionaries.materials.find((m) => m.value === run.material_id)?.label ??
                'Not reported'}
            </dd>
          </div>
          <div>
            <dt>Geometry</dt>
            <dd>{geometryLabels[run.sample.geometry]}</dd>
          </div>
          <div>
            <dt>Initial diameter</dt>
            <dd>
              <QuantityValue quantity={run.sample.initial_diameter} expectedUnit="m" />
            </dd>
          </div>
          <div>
            <dt>Thickness</dt>
            <dd>
              <QuantityValue quantity={run.sample.thickness} expectedUnit="m" />
            </dd>
          </div>
        </dl>
      </div>
      <div className={s.section}>
        <h3>Conditions</h3>
        <dl>
          <div>
            <dt>Regime</dt>
            <dd>
              {config.dictionaries.gravity_regime.find(
                (g) => g.value === run.conditions.gravity_regime,
              )?.label ?? run.conditions.gravity_regime}
            </dd>
          </div>
          {conditions.map(([label, value, unit]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <QuantityValue quantity={value} expectedUnit={unit} />
              </dd>
            </div>
          ))}
          <div>
            <dt>Flow configuration</dt>
            <dd>
              {
                {
                  concurrent: 'Concurrent flow',
                  opposed: 'Opposed flow',
                  quiescent: 'Quiescent',
                  other: 'Other',
                  unknown: 'Not reported',
                }[run.conditions.flow_configuration]
              }
            </dd>
          </div>
        </dl>
      </div>
      <div className={s.section}>
        <h3>Measurements</h3>
        {run.metrics.length ? (
          <dl>
            {run.metrics.map((metric) => (
              <div key={metric.metric_key}>
                <dt>
                  {
                    {
                      burn_duration: 'Burn duration',
                      visible_extinction_diameter: 'Visible extinction diameter',
                      flame_spread_rate: 'Spread rate',
                      particle_diameter: 'Particle diameter',
                    }[metric.metric_key]
                  }
                </dt>
                <dd>
                  <QuantityValue
                    quantity={metric.quantity}
                    expectedUnit={
                      metric.metric_key === 'burn_duration'
                        ? 's'
                        : metric.metric_key === 'flame_spread_rate'
                          ? 'm_s'
                          : 'm'
                    }
                  />
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="tiny muted">No measurements have been added.</p>
        )}
      </div>
      {run.quality_notes.map((note) => (
        <p className={s.qualityNote} key={note}>
          {note}
        </p>
      ))}
      <div className={s.evidenceButtons}>
        {run.evidence_ids.map((id, index) => (
          <button className="textLink" key={id} onClick={() => onEvidence(id)}>
            Evidence {index + 1} <ArrowUpRight size={13} />
          </button>
        ))}
      </div>
    </Panel>
  );
}
