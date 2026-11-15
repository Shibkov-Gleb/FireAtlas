import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowRight, ChartScatter } from 'lucide-react';
import { api } from '../api/client';
import { type Schema } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, Button, EmptyState, Loading, Notice, PageHeader, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import { RunPanel } from '../components/RunPanel';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { outcomeLabels } from '../lib/format';
import s from './Measurements.module.css';

type Point = Schema['MeasurementResponse']['points'][number];
const number = (value: number) =>
  new Intl.NumberFormat('en-US', { maximumSignificantDigits: 6, useGrouping: false }).format(value);
export function Measurements() {
  const { workspace, config } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const axes = config.measurement_axes[0];
  const investigationId = axes?.investigation_ids[0] ?? 'inv_psi69';
  const allRuns = params.get('series') === 'all';
  const controlRunIds = ['20cal08', '20cal10', '20cal12', '30cal02', '30cal03'].map(
    (id) => `run_psi69_${id}`,
  );
  const query = useQuery({
    queryKey: [
      'measurements',
      investigationId,
      workspace.data_revision,
      allRuns,
      params.get('cursor'),
    ],
    queryFn: ({ signal }) =>
      api
        .measurements(
          {
            investigation_id: investigationId,
            data_revision: workspace.data_revision,
            run_ids: allRuns ? [] : controlRunIds,
            x_metric: axes!.x_key,
            y_metric: axes!.y_key,
            filters: { outcome_categories: [], material_ids: [] },
            cursor: params.get('cursor'),
            limit: 200,
          },
          signal,
        )
        .then((r) => r.data),
    enabled: !!axes,
  });
  const selected = params.get('run');
  const outcome = params.get('outcome') ?? '';
  const points = (query.data?.points ?? []).filter(
    (point) => !outcome || point.outcome === outcome,
  );
  function select(id: string | null) {
    const next = new URLSearchParams(params);
    if (id) next.set('run', id);
    else next.delete('run');
    setParams(next, { replace: true });
  }
  useEffect(() => {
    if (selected && query.data && !points.some((point) => point.run_id === selected)) select(null);
  }, [query.data, outcome, selected]);
  if (!axes)
    return (
      <>
        <PageHeader title="Measurements" />
        <EmptyState title="No supported charts in this revision" />
      </>
    );
  const correctUnits = query.data?.x_axis.unit === 'm' && query.data?.y_axis.unit === 's';
  function pointShape(raw: unknown) {
    const { cx, cy, payload } = raw as { cx: number; cy: number; payload: Point };
    const active = payload.run_id === selected;
    const testId = payload.run_id.split('_').at(-1)!.toUpperCase();
    return (
      <g
        role="button"
        tabIndex={0}
        aria-label={`Select point ${testId}`}
        aria-pressed={active}
        onClick={() => select(payload.run_id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            select(payload.run_id);
          }
        }}
        style={{ cursor: 'pointer' }}
      >
        <rect x={cx - 12} y={cy - 12} width={24} height={24} fill="transparent" />
        {active && <circle cx={cx} cy={cy} r={11} fill="#78d4fc14" stroke="#78d4fc66" />}
        {payload.outcome === 'disruption' ? (
          <path
            d={`M${cx - 5},${cy - 5} L${cx + 5},${cy + 5} M${cx - 5},${cy + 5} L${cx + 5},${cy - 5}`}
            stroke="#ff945a"
            strokeWidth={2}
          />
        ) : (
          <circle
            cx={cx}
            cy={cy}
            r={active ? 5.5 : 4.5}
            fill="#78d4fc"
            stroke={active ? '#c8f0ff' : '#101b2c'}
            strokeWidth={1.5}
          />
        )}
      </g>
    );
  }
  return (
    <>
      <PageHeader
        eyebrow="MEASUREMENTS / FLEX · PSI-69"
        title="From a point to a test run"
        description="Initial droplet diameter and burn duration. Each point opens its conditions, outcome and source."
        action={
          <Badge tone="cyan">
            <ChartScatter size={12} /> Scatter plot
          </Badge>
        }
      />
      <div className={s.conditions}>
        <div className="inline">
          <Badge>FLEX · liquid-fuel droplets</Badge>
          <Badge>Conditions vary by test run</Badge>
          <Badge tone="teal">
            {allRuns ? 'FLEX measurement corpus' : 'Five FLEX control records'}
          </Badge>
        </div>
        <label className={s.outcomeFilter}>
          Dataset
          <select
            value={allRuns ? 'all' : 'control'}
            onChange={(event) => {
              const next = new URLSearchParams(params);
              if (event.target.value === 'all') next.set('series', 'all');
              else next.delete('series');
              next.delete('cursor');
              next.delete('run');
              setParams(next);
            }}
          >
            <option value="control">Five control test runs</option>
            <option value="all">All FLEX test runs</option>
          </select>
        </label>
        <label className={s.outcomeFilter}>
          Outcome
          <select
            value={outcome}
            onChange={(event) => {
              const next = new URLSearchParams(params);
              if (event.target.value) next.set('outcome', event.target.value);
              else next.delete('outcome');
              setParams(next);
            }}
          >
            <option value="">All outcomes</option>
            <option value="extinction">Extinction</option>
            <option value="disruption">Droplet disruption</option>
            <option value="burn_to_completion">Burn to completion</option>
            <option value="no_ignition">No ignition</option>
            <option value="ongoing_at_stop">Burning at shutdown</option>
            <option value="unknown">Outcome not reported</option>
          </select>
        </label>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <>
          <div className={s.layout}>
            <div className="stack">
              <Panel className={s.chartPanel}>
                <div className="spaceBetween">
                  <h2>Observed measurements</h2>
                  <span className="tiny mono muted">{points.length} POINTS</span>
                </div>
                {!correctUnits ? (
                  <Notice tone="warning">
                    The axis units are incompatible with this chart. Measurements have not been
                    converted.
                  </Notice>
                ) : points.length ? (
                  <div className={s.chart}>
                    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                      <ScatterChart
                        margin={{ top: 20, right: 20, bottom: 29, left: 0 }}
                        accessibilityLayer
                      >
                        <CartesianGrid stroke="#ffffff09" vertical={false} />
                        <XAxis
                          type="number"
                          dataKey="x"
                          name="Diameter"
                          domain={['dataMin - 0.0001', 'dataMax + 0.0001']}
                          tickFormatter={(value) => number(Number(value) * 1000)}
                          tick={{ fill: '#8fa5c0', fontSize: 10 }}
                          axisLine={{ stroke: '#344157' }}
                          tickLine={false}
                          label={{
                            value: 'Initial droplet diameter, mm',
                            position: 'bottom',
                            offset: 10,
                            fill: '#9db0ca',
                            fontSize: 10,
                          }}
                        />
                        <YAxis
                          type="number"
                          dataKey="y"
                          name="Time"
                          domain={[0, 'auto']}
                          tick={{ fill: '#8fa5c0', fontSize: 10 }}
                          axisLine={false}
                          tickLine={false}
                          width={45}
                          label={{
                            value: 'Burn duration, s',
                            angle: -90,
                            position: 'insideLeft',
                            fill: '#9db0ca',
                            fontSize: 10,
                          }}
                        />
                        <Tooltip
                          cursor={{ stroke: '#78d4fc30', strokeDasharray: '3 3' }}
                          content={({ active, payload }) => {
                            const point = payload?.[0]?.payload as Point | undefined;
                            return active && point ? (
                              <div className={s.tooltip}>
                                <strong>{point.run_id.split('_').at(-1)!.toUpperCase()}</strong>
                                <p>Diameter: {number(point.x * 1000)} mm</p>
                                <p>Time: {number(point.y)} s</p>
                              </div>
                            ) : null;
                          }}
                        />
                        <Scatter
                          data={points}
                          fill="#78d4fc"
                          shape={pointShape}
                          isAnimationActive={false}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <EmptyState title="No measurements for this selection">
                    Change the outcome filter. Missing coordinates are not replaced with zeroes.
                  </EmptyState>
                )}
                <div className={s.legend}>
                  <span>
                    <i /> Extinction
                  </span>
                  <span>
                    <b>×</b> Disruption
                  </span>
                </div>
                <p className={s.chartNote}>
                  These points do not establish causality. No trend line or prediction is shown.
                </p>
              </Panel>
              {query.data.excluded_count > 0 && (
                <Notice tone="warning">
                  Excluded records: {query.data.excluded_count}.
                  <ul className="tiny">
                    {Object.entries(query.data.exclusions_by_reason)
                      .filter(([, count]) => count > 0)
                      .map(([reason, count]) => (
                        <li
                          key={
                            reason as keyof Schema['MeasurementResponse']['exclusions_by_reason']
                          }
                        >
                          {
                            (
                              {
                                missing_x: 'Missing X value',
                                missing_y: 'Missing Y value',
                                unusable_unit: 'Unusable unit',
                                unverified_record: 'Unverified record',
                                filtered_out: 'Excluded by filters',
                              } as const
                            )[reason as keyof Schema['MeasurementResponse']['exclusions_by_reason']]
                          }
                          : {count}
                        </li>
                      ))}
                  </ul>
                </Notice>
              )}
              {query.data.truncated && (
                <Notice tone="warning">
                  Only part of the dataset is shown. Load the next page for more measurements.
                  {query.data.next_cursor && (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const next = new URLSearchParams(params);
                        next.set('cursor', query.data.next_cursor!);
                        next.delete('run');
                        setParams(next);
                      }}
                    >
                      Next measurements <ArrowRight size={13} />
                    </Button>
                  )}
                </Notice>
              )}
              <section>
                <h2 className="sectionTitle">Data table</h2>
                <div
                  className="tableScroll"
                  role="region"
                  tabIndex={0}
                  aria-label="FLEX measurements table"
                >
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Test run</th>
                        <th scope="col">Diameter, mm</th>
                        <th scope="col">Time, s</th>
                        <th scope="col">Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {points.map((point) => (
                        <tr key={point.run_id} data-selected={selected === point.run_id}>
                          <th scope="row">
                            <button
                              className="textLink mono"
                              aria-pressed={selected === point.run_id}
                              onClick={() => select(point.run_id)}
                            >
                              {point.run_id.split('_').at(-1)!.toUpperCase()}
                            </button>
                          </th>
                          <td>{number(point.x * 1000)}</td>
                          <td>{number(point.y)}</td>
                          <td>
                            {outcomeLabels[point.outcome as keyof typeof outcomeLabels] ??
                              point.outcome}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <RunPanel
              runId={selected}
              revision={workspace.data_revision}
              onEvidence={setEvidenceId}
              onClose={() => select(null)}
              investigationId={investigationId}
            />
          </div>
        </>
      )}
      <EvidenceDrawer
        id={evidenceId}
        revision={workspace.data_revision}
        onClose={() => setEvidenceId(null)}
      />
    </>
  );
}
