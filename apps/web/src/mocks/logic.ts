import type { Filters, Investigation, Schema, TestRun } from '../api/types';
import { emptyFilters } from '../api/types';
import { evidence, extraInvestigation, investigations, runs } from './fixtures';

export function fingerprint(value: unknown): string {
  const text = JSON.stringify(value);
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  return (hash >>> 0).toString(36);
}
const overlaps = (filter: string[], values: string[]) =>
  !filter.length || filter.some((value) => values.includes(value));
export function matchesRun(run: TestRun, filters: Filters): boolean {
  if (
    filters.material_ids.length &&
    (!run.material_id || !filters.material_ids.includes(run.material_id))
  )
    return false;
  if (
    filters.gravity_regimes.length &&
    !filters.gravity_regimes.includes(run.conditions.gravity_regime)
  )
    return false;
  const fields = [
    [filters.oxygen_range, run.conditions.oxygen_fraction],
    [filters.pressure_range, run.conditions.pressure],
    [filters.airflow_range, run.conditions.airflow_speed],
  ] as const;
  return fields.every(
    ([range, quantity]) =>
      !range ||
      (quantity.value === null
        ? filters.include_unknown
        : (range.min == null || quantity.value >= range.min) &&
          (range.max == null || quantity.value <= range.max)),
  );
}
export function searchFixture(
  body: Schema['SearchRequest'],
  includeExtra = false,
): Schema['SearchResult'] {
  const corpus = includeExtra ? [...investigations, extraInvestigation] : investigations;
  const q = body.query.trim().toLocaleLowerCase('ru');
  const keywords: Record<string, string[]> = {
    inv_psi25: [
      'ventilat',
      'airflow',
      'solid',
      'material',
      'bass',
      'вентиля',
      'воздух',
      'твёрд',
      'тверд',
      'материал',
    ],
    inv_psi69: [
      'droplet',
      'liquid',
      'methanol',
      'extinct',
      'flex',
      'капл',
      'жидк',
      'метанол',
      'погасан',
    ],
    inv_psi101: ['smoke', 'particle', 'detect', 'same', 'дым', 'частиц', 'обнаруж'],
  };
  const items: Schema['SearchItem'][] = [];
  for (const investigation of corpus) {
    const f = body.filters ?? emptyFilters();
    const entityPass =
      overlaps(f.scopes, investigation.scopes) &&
      overlaps(f.investigation_ids, [investigation.id]) &&
      overlaps(f.fuel_states, investigation.fuel_states) &&
      overlaps(f.gravity_regimes, investigation.gravity_regimes) &&
      overlaps(f.material_ids, investigation.material_ids);
    const selectedRuns = runs.filter(
      (run) => run.investigation_id === investigation.id && matchesRun(run, f),
    );
    const constrained = !!(f.oxygen_range || f.pressure_range || f.airflow_range);
    const hasMeasurements = runs.some(
      (run) =>
        run.investigation_id === investigation.id &&
        run.metrics.some((metric) => metric.quantity.value !== null),
    );
    const hardPass =
      entityPass &&
      (!constrained || selectedRuns.length > 0) &&
      (f.has_measurements === null || hasMeasurements === f.has_measurements);
    const queryPass =
      !q ||
      ['combustion', 'горение'].includes(q) ||
      investigation.id === 'inv_demo04' ||
      (keywords[investigation.id] ?? []).some((term) => q.includes(term)) ||
      [investigation.title, investigation.acronym, ...investigation.objectives]
        .join(' ')
        .toLocaleLowerCase('ru')
        .includes(q);
    if (!hardPass || (!queryPass && !body.include_related)) continue;
    items.push({
      investigation,
      relevance_category: queryPass ? 'direct' : 'related',
      match_reasons: queryPass
        ? [
            {
              code: 'scope_match',
              text: 'The research question and investigation scope match.',
              field: null,
              evidence_ids: [],
            },
          ]
        : [
            {
              code: 'related',
              text: 'A related research area for exploring other mechanisms.',
              field: null,
              evidence_ids: [],
            },
          ],
      differences: queryPass
        ? []
        : [
            {
              code: 'different_object',
              text: 'Different subject or method; this is not an exact match for the question.',
              field: null,
              evidence_ids: [],
            },
          ],
      missing_fields:
        investigation.id === 'inv_psi25' ? ['Pressure is not reported in this test record.'] : [],
      matching_run_ids: selectedRuns.map((r) => r.id),
      related: !queryPass,
      evidence_ids: evidence
        .filter((e) => investigation.source_ids.includes(e.source_id))
        .map((e) => e.id),
    });
  }
  items.sort((a, b) =>
    body.sort === 'acronym'
      ? a.investigation.acronym.localeCompare(b.investigation.acronym) ||
        a.investigation.id.localeCompare(b.investigation.id)
      : Number(a.related) - Number(b.related) ||
        corpus.indexOf(a.investigation) - corpus.indexOf(b.investigation),
  );
  const signature = fingerprint({ ...body, cursor: null });
  let offset = 0;
  if (body.cursor) {
    const [raw, hash] = body.cursor.split('.');
    offset = Number(raw);
    if (hash !== signature || !Number.isInteger(offset) || offset < 0)
      throw new Error('INVALID_CURSOR');
  }
  return {
    items: items.slice(offset, offset + body.limit),
    next_cursor: offset + body.limit < items.length ? `${offset + body.limit}.${signature}` : null,
    total: items.length,
    retrieval_mode: 'lexical',
    applied_filters: body.filters ?? emptyFilters(),
  };
}
export function measurementFixture(
  body: Schema['MeasurementRequest'],
): Schema['MeasurementResponse'] {
  const candidates = runs.filter(
    (run) =>
      run.investigation_id === body.investigation_id &&
      (!body.run_ids.length || body.run_ids.includes(run.id)),
  );
  const exclusions = new Map<string, number>();
  const points: Schema['MeasurementResponse']['points'] = [];
  for (const run of candidates) {
    const x = run.sample.initial_diameter;
    const y = run.metrics.find((m) => m.metric_key === 'burn_duration')?.quantity;
    let reason: string | null = null;
    if (
      !matchesRun(run, { ...emptyFilters(), ...body.filters }) ||
      (body.filters?.outcome_categories.length &&
        !body.filters.outcome_categories.includes(run.terminal_outcome.category))
    )
      reason = 'filtered_out';
    else if (x.status === 'unusable' || y?.status === 'unusable') reason = 'unusable_unit';
    else if (x.value === null) reason = 'missing_x';
    else if (y?.value == null) reason = 'missing_y';
    if (reason) {
      exclusions.set(reason, (exclusions.get(reason) ?? 0) + 1);
      continue;
    }
    points.push({
      run_id: run.id,
      x: x.value!,
      y: y!.value!,
      outcome: run.terminal_outcome.category,
      evidence_ids: run.evidence_ids,
    });
  }
  return {
    x_axis: { key: 'sample.initial_diameter', label: 'Initial droplet diameter', unit: 'm' },
    y_axis: { key: 'metrics.burn_duration', label: 'Burn duration', unit: 's' },
    points: points.slice(0, body.limit),
    excluded_count: [...exclusions.values()].reduce((a, b) => a + b, 0),
    exclusions_by_reason: {
      missing_x: 0,
      missing_y: 0,
      unusable_unit: 0,
      unverified_record: 0,
      filtered_out: 0,
      ...Object.fromEntries(exclusions),
    },
    truncated: points.length > body.limit,
    next_cursor: null,
  };
}
export function defaultSearch(revision: string): Schema['SearchRequest'] {
  return {
    query: '',
    locale: 'en',
    data_revision: revision,
    filters: { ...emptyFilters(), scopes: ['prevention', 'detection', 'suppression'] },
    scenario: null,
    include_related: false,
    cursor: null,
    limit: 20,
    sort: 'relevance',
  };
}
export function comparisonFixture(
  selected: Investigation[],
  scenario: Schema['Scenario'],
): Schema['ComparisonResponse'] {
  const valueById: Record<string, string[]> = {
    inv_psi25: [
      'Solid samples',
      'Flame spread and extinction',
      'Airflow, oxygen, geometry',
      'Prevention',
    ],
    inv_psi69: [
      'Liquid-fuel droplets',
      'Droplet combustion and extinction',
      'Atmosphere, pressure, diameter',
      'Suppression',
    ],
    inv_psi101: [
      'Smoke particles',
      'Smoke generation and characteristics',
      'Material, heating, transport',
      'Detection',
    ],
  };
  return {
    investigations: selected,
    rows: ['Research subject', 'Key question', 'Controlled conditions', 'Research area'].map(
      (label, index) => ({
        field: `field_${index}`,
        label,
        cells: selected.map((inv) => ({
          investigation_id: inv.id,
          value_text: valueById[inv.id]?.[index] ?? 'Not reported',
          status: valueById[inv.id] ? 'known' : 'not_reported',
          evidence_ids: evidence
            .filter((e) => inv.source_ids.includes(e.source_id))
            .map((e) => e.id),
        })),
      }),
    ),
    comparability: {
      status: 'partially_compatible',
      reasons: [
        {
          code: 'different_method',
          text: 'Different subjects and methods: a common fire-hazard scale is not justified.',
          field: null,
          evidence_ids: [],
        },
      ],
    },
    applicability: {
      overall: 'related_evidence',
      factors: [],
      gaps: [],
      basis: {
        reviewed_rules_version: 'demo-ui-v1',
        data_revision: scenario.scenario_id ? (selected[0]?.data_revision ?? '') : ' ',
      },
    },
    limitations: [
      'Demo comparison of investigation descriptions; numerical series are not combined.',
    ],
  };
}
