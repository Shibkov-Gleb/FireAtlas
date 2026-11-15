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
import { emptyFilters, type Schema } from '../api/types';
import { useWorkspace } from '../state/WorkspaceProvider';
import { Badge, Button, EmptyState, Loading, Notice, PageHeader, Panel } from '../components/ui';
import { ErrorState } from '../components/ErrorState';
import { RunPanel } from '../components/RunPanel';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { outcomeLabels } from '../lib/format';
import s from './Measurements.module.css';

type Point = Schema['MeasurementResponse']['points'][number];
const number = (value: number) =>
  new Intl.NumberFormat('ru-RU', { maximumSignificantDigits: 6, useGrouping: false }).format(value);
export function Measurements() {
  const { workspace, config } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const axes = config.measurement_axes[0];
  const investigationId = axes?.investigation_ids[0] ?? 'inv_psi69';
  const query = useQuery({
    queryKey: ['measurements', investigationId, workspace.data_revision, params.get('cursor')],
    queryFn: ({ signal }) =>
      api
        .measurements(
          {
            investigation_id: investigationId,
            data_revision: workspace.data_revision,
            run_ids: [],
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
        <PageHeader title="Измерения" />
        <EmptyState title="В этой ревизии нет поддерживаемых графиков" />
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
        aria-label={`Выбрать точку ${testId}`}
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
        eyebrow="ИЗМЕРЕНИЯ / FLEX · PSI-69"
        title="От точки — к отдельному опыту"
        description="Начальный диаметр капли и время горения. Каждая точка открывает условия, исход и источник."
        action={
          <Badge tone="cyan">
            <ChartScatter size={12} /> Scatter plot
          </Badge>
        }
      />
      <div className={s.conditions}>
        <div className="inline">
          <Badge>Метанол</Badge>
          <Badge>Начальная доля O₂: 21 %</Badge>
          <Badge tone="teal">Контрольные записи FLEX</Badge>
        </div>
        <label className={s.outcomeFilter}>
          Исход
          <select
            value={outcome}
            onChange={(event) => {
              const next = new URLSearchParams(params);
              if (event.target.value) next.set('outcome', event.target.value);
              else next.delete('outcome');
              setParams(next);
            }}
          >
            <option value="">Все исходы</option>
            <option value="extinction">Погасание</option>
            <option value="disruption">Разрушение капли</option>
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
                  <h2>Наблюдаемые измерения</h2>
                  <span className="tiny mono muted">{points.length} ТОЧЕК</span>
                </div>
                {!correctUnits ? (
                  <Notice tone="warning">
                    Единицы осей несовместимы с этим графиком. Измерения не преобразованы.
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
                          name="Диаметр"
                          domain={['dataMin - 0.0001', 'dataMax + 0.0001']}
                          tickFormatter={(value) => number(Number(value) * 1000)}
                          tick={{ fill: '#8fa5c0', fontSize: 10 }}
                          axisLine={{ stroke: '#344157' }}
                          tickLine={false}
                          label={{
                            value: 'Начальный диаметр капли, мм',
                            position: 'bottom',
                            offset: 10,
                            fill: '#9db0ca',
                            fontSize: 10,
                          }}
                        />
                        <YAxis
                          type="number"
                          dataKey="y"
                          name="Время"
                          domain={[0, 'auto']}
                          tick={{ fill: '#8fa5c0', fontSize: 10 }}
                          axisLine={false}
                          tickLine={false}
                          width={45}
                          label={{
                            value: 'Время горения, с',
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
                                <p>Диаметр: {number(point.x * 1000)} мм</p>
                                <p>Время: {number(point.y)} с</p>
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
                  <EmptyState title="Нет измерений для этого выбора">
                    Измените фильтр исхода. Отсутствующие координаты не заменяются нулями.
                  </EmptyState>
                )}
                <div className={s.legend}>
                  <span>
                    <i /> Погасание · Extinction
                  </span>
                  <span>
                    <b>×</b> Разрушение · Disruption
                  </span>
                </div>
                <p className={s.chartNote}>
                  Точки не устанавливают причинную зависимость. Линия тренда и прогноз не строятся.
                </p>
              </Panel>
              {query.data.excluded_count > 0 && (
                <Notice tone="warning">
                  Исключено записей: {query.data.excluded_count}.
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
                                missing_x: 'Нет координаты X',
                                missing_y: 'Нет координаты Y',
                                unusable_unit: 'Непригодная единица',
                                unverified_record: 'Непроверенная запись',
                                filtered_out: 'Не проходит фильтр',
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
                  Показана часть набора. Загрузите следующую страницу для остальных измерений.
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
                      Следующие измерения <ArrowRight size={13} />
                    </Button>
                  )}
                </Notice>
              )}
              <section>
                <h2 className="sectionTitle">Табличный эквивалент</h2>
                <div
                  className="tableScroll"
                  role="region"
                  tabIndex={0}
                  aria-label="Таблица измерений FLEX"
                >
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Опыт</th>
                        <th scope="col">Диаметр, мм</th>
                        <th scope="col">Время, с</th>
                        <th scope="col">Исход</th>
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
