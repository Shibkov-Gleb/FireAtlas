import dictionaries from '../../../../packages/contracts/dictionaries.ru.json';
import type { Investigation, Quantity, Scenario, Schema, Source, TestRun } from '../api/types';

export const REVISION = 'demo-20261104-r1';
export const FIXTURE_METADATA = {
  fixture: true,
  description:
    'Демонстрационный набор UI. Не является опубликованным научным корпусом. Пять FLEX-точек перенесены из приложения А ТЗ.',
};
export const orbitalScenario: Scenario = {
  scenario_id: 'orbital_custom',
  name: 'Орбитальная станция',
  environment: 'orbital_habitat',
  celestial_body: 'earth',
  safety_task: 'prevention',
  material_ids: [],
  geometry: null,
  oxygen_fraction: null,
  pressure: null,
  airflow_speed: null,
  gravity_regime: 'microgravity',
  assumptions: [],
};
export const materials: Schema['Material'][] = [
  { id: 'mat_solid', label: 'Твёрдые образцы', state: 'solid', composition: null, aliases: [] },
  {
    id: 'mat_methanol',
    label: 'Метанол',
    state: 'liquid',
    composition: 'CH₃OH',
    aliases: ['Methanol'],
  },
  { id: 'mat_smoke', label: 'Дымовые частицы', state: 'aerosol', composition: null, aliases: [] },
];
const makeSource = (
  id: string,
  title: string,
  url: string,
  kind: Source['kind'] = 'repository',
  availability: Source['availability'] = 'available',
): Source => ({
  id,
  data_revision: REVISION,
  title,
  canonical_url: url,
  kind,
  doi: null,
  publication_date: null,
  retrieved_at: '2026-11-04T00:00:00Z',
  license: null,
  availability,
  local_asset_id: null,
  sha256: null,
});
export const sources: Source[] = [
  makeSource(
    'src_psi25',
    'BASS-II · NASA PSI-25',
    'https://psi.nasa.gov/physci/repo/data/investigations/PSI-25',
  ),
  makeSource(
    'src_bass_report',
    'BASS-II · результаты исследований',
    'https://ntrs.nasa.gov/citations/20160000593',
    'report',
  ),
  makeSource(
    'src_psi69',
    'FLEX · Experimental Table, версия 5',
    'https://psi.nasa.gov/physci/repo/data/investigations/PSI-69',
    'experimental_table',
  ),
  makeSource(
    'src_psi101',
    'SAME-R · NASA PSI-101',
    'https://psi.nasa.gov/physci/repo/data/investigations/PSI-101',
  ),
  makeSource(
    'src_nasa_combustion',
    'NASA · горение и пожарная безопасность на МКС',
    'https://www.nasa.gov/missions/station/iss-research/studying-combustion-and-fire-safety/',
    'report',
  ),
  makeSource(
    'src_unavailable',
    'Пример недоступного вложения BASS-II',
    'https://psi.nasa.gov/physci/repo/data/investigations/PSI-25',
    'video',
    'unavailable',
  ),
];
const makeInvestigation = (
  id: string,
  psi: string,
  acronym: string,
  title: string,
  scope: Schema['Scope'],
  fuel: Schema['FuelState'],
  material: string,
  sourceIds: string[],
  objectives: string[],
  setup: string,
): Investigation => ({
  id,
  data_revision: REVISION,
  psi_id: psi,
  acronym,
  title,
  objectives,
  setup_summary: setup,
  scopes: [scope],
  fuel_states: [fuel],
  gravity_regimes: ['microgravity'],
  material_ids: [material],
  source_ids: sourceIds,
  claim_ids: [`clm_${id}`],
  conditions_coverage: [],
  available_assets: sourceIds,
});
export const investigations: Investigation[] = [
  makeInvestigation(
    'inv_psi25',
    'PSI-25',
    'BASS-II',
    'Горение твёрдых материалов в микрогравитации',
    'prevention',
    'solid',
    'mat_solid',
    ['src_psi25', 'src_bass_report', 'src_unavailable'],
    [
      'Изучить распространение и погасание пламени на твёрдых образцах.',
      'Сопоставить влияние потока воздуха, атмосферы и геометрии.',
    ],
    'Исследования твёрдых образцов в условиях микрогравитации. Детали установки и методики сверяются с первоисточником.',
  ),
  makeInvestigation(
    'inv_psi69',
    'PSI-69',
    'FLEX',
    'Горение и погасание капель жидкого топлива',
    'suppression',
    'liquid',
    'mat_methanol',
    ['src_psi69'],
    [
      'Изучить горение и погасание капель.',
      'Проверить измерения вместе с атмосферой, давлением и начальным размером.',
    ],
    'Капельные эксперименты. В демонстрации представлены пять контрольных записей метанола из ТЗ.',
  ),
  makeInvestigation(
    'inv_psi101',
    'PSI-101',
    'SAME-R',
    'Свойства дыма для обнаружения пожара',
    'detection',
    'aerosol',
    'mat_smoke',
    ['src_psi101'],
    ['Изучить характеристики частиц дыма.', 'Сопоставить условия образования и измерения дыма.'],
    'Измерения дымовых частиц. Записи дыма не трактуются как исходы испытаний пламени.',
  ),
];
export const extraInvestigation = makeInvestigation(
  'inv_demo04',
  'DEMO-04',
  'DEMO-04',
  'Тестовая карточка для проверки лимита сравнения',
  'prevention',
  'solid',
  'mat_solid',
  [],
  ['Синтетическая карточка интерфейса. Научных результатов нет.'],
  'Только тестовый сценарий comparison_limit.',
);
export function quantity<U extends Quantity['unit']>(
  value: number | null,
  unit: U,
  evidenceIds: string[] = [],
  rawValue: string | null = value === null ? null : String(value),
  rawUnit: string | null = unit,
): Quantity & { unit: U } {
  return {
    value,
    unit,
    status: value === null ? 'not_reported' : 'reported',
    qualifier: value === null ? null : 'eq',
    raw_value: rawValue,
    raw_unit: value === null ? null : rawUnit,
    uncertainty: null,
    evidence_ids: evidenceIds,
    derivation: null,
  };
}
export const notApplicable = <U extends Quantity['unit']>(unit: U): Quantity & { unit: U } => ({
  ...quantity(null, unit),
  status: 'not_applicable',
});
const controlRows = [
  ['20CAL08', 1.69, 4.3, 757.7, 'disruption', 'Disruption'],
  ['20CAL10', 1.86, 5, 762, 'extinction', 'Extinction'],
  ['20CAL12', 1.61, 3.2, 764.2, 'extinction', 'Extinction'],
  ['30CAL02', 2.06, 7.64, 760, 'extinction', 'Extinction'],
  ['30CAL03', 1.92, 6.34, 760, 'extinction', 'Extinction'],
] as const;
export const flexRuns: TestRun[] = controlRows.map(
  ([test, diameter, duration, pressure, category, rawLabel]) => {
    const ev = [`ev_psi69_${test.toLowerCase()}`];
    return {
      id: `run_psi69_${test.toLowerCase()}`,
      data_revision: REVISION,
      investigation_id: 'inv_psi69',
      source_test_id: test,
      material_id: 'mat_methanol',
      sample: {
        geometry: 'droplet',
        thickness: notApplicable('m'),
        initial_diameter: quantity(diameter / 1000, 'm', ev, String(diameter), 'mm'),
      },
      conditions: {
        gravity_regime: 'microgravity',
        gravity_level: quantity(null, 'g_fraction'),
        nitrogen_fraction: quantity(null, 'fraction'),
        co2_fraction: quantity(null, 'fraction'),
        helium_fraction: quantity(null, 'fraction'),
        oxygen_fraction: quantity(0.21, 'fraction', ev, '0.21', 'fraction'),
        pressure: quantity(pressure * 133.322387, 'Pa', ev, String(pressure), 'mmHg'),
        airflow_speed: quantity(null, 'm_s'),
        flow_configuration: 'unknown',
        ambient_temperature: quantity(null, 'K'),
      },
      metrics: [
        {
          metric_key: 'burn_duration',
          quantity: quantity(duration, 's', ev, String(duration), 's'),
        },
      ],
      terminal_outcome: {
        category,
        raw_label: rawLabel,
        interpretation_status: 'source_explicit',
        evidence_ids: ev,
      },
      regime_tags: [],
      evidence_ids: ev,
      quality_notes: [
        'Контрольная запись из приложения А ТЗ; демонстрационный набор не заменяет проверенный выпуск корпуса.',
      ],
    };
  },
);
export const demoRuns: TestRun[] = [
  {
    ...flexRuns[0]!,
    id: 'run_demo_bass',
    investigation_id: 'inv_psi25',
    source_test_id: 'DEMO-BASS-01',
    material_id: 'mat_solid',
    sample: {
      geometry: 'sheet',
      thickness: quantity(null, 'm'),
      initial_diameter: notApplicable('m'),
    },
    conditions: {
      ...flexRuns[0]!.conditions,
      nitrogen_fraction: quantity(null, 'fraction'),
      co2_fraction: quantity(null, 'fraction'),
      helium_fraction: quantity(null, 'fraction'),
      oxygen_fraction: quantity(null, 'fraction'),
      pressure: quantity(null, 'Pa'),
      airflow_speed: quantity(0, 'm_s', ['ev_demo_bass'], '0', 'm/s'),
      flow_configuration: 'quiescent',
    },
    metrics: [],
    terminal_outcome: {
      category: 'unknown',
      raw_label: 'Не сообщено',
      interpretation_status: 'unmapped',
      evidence_ids: [],
    },
    evidence_ids: ['ev_demo_bass'],
    quality_notes: [
      'Синтетическая запись UI для проверки нуля и неизвестных значений. Не результат NASA.',
    ],
  },
  {
    ...flexRuns[0]!,
    id: 'run_demo_smoke',
    investigation_id: 'inv_psi101',
    source_test_id: 'DEMO-SMOKE-01',
    material_id: 'mat_smoke',
    sample: {
      geometry: 'other',
      thickness: notApplicable('m'),
      initial_diameter: notApplicable('m'),
    },
    conditions: {
      ...flexRuns[0]!.conditions,
      nitrogen_fraction: quantity(null, 'fraction'),
      co2_fraction: quantity(null, 'fraction'),
      helium_fraction: quantity(null, 'fraction'),
      oxygen_fraction: quantity(null, 'fraction'),
      pressure: quantity(null, 'Pa'),
    },
    metrics: [
      {
        metric_key: 'particle_diameter',
        quantity: {
          ...quantity(null, 'm'),
          status: 'unusable',
          raw_value: 'unknown',
          raw_unit: 'неизвестно',
        },
      },
    ],
    terminal_outcome: {
      category: 'smoke_measurement',
      raw_label: 'Smoke measurement',
      interpretation_status: 'source_explicit',
      evidence_ids: ['ev_demo_smoke'],
    },
    evidence_ids: ['ev_demo_smoke'],
    quality_notes: ['Синтетическая запись UI. Единицы непригодны для графика. Не результат NASA.'],
  },
];
export const runs = [...flexRuns, ...demoRuns];
const locator = (row: string | null = null): Schema['Locator'] => ({
  page: null,
  section: row ? 'Experimental Table FLEX, v5' : 'Описание исследования',
  row_key: row,
  start_s: null,
  end_s: null,
});
export const evidence: Schema['Evidence'][] = [
  ...flexRuns.map((run) => ({
    id: run.evidence_ids[0]!,
    data_revision: REVISION,
    source_id: 'src_psi69',
    kind: 'table_row' as const,
    locator: locator(run.source_test_id),
    excerpt: null,
    table_values: [
      {
        field: 'Initial diameter',
        raw_value: run.sample.initial_diameter.raw_value!,
        raw_unit: 'mm',
      },
      { field: 'Burn duration', raw_value: run.metrics[0]!.quantity.raw_value!, raw_unit: 's' },
      { field: 'Pressure', raw_value: run.conditions.pressure.raw_value!, raw_unit: 'mmHg' },
      { field: 'Outcome', raw_value: run.terminal_outcome.raw_label, raw_unit: null },
    ],
    verified: true,
    verification_note:
      'Перенесено из контрольного примера предоставленного ТЗ. Перед научной публикацией требуется независимая проверка источника.',
  })),
  {
    id: 'ev_demo_bass',
    data_revision: REVISION,
    source_id: 'src_bass_report',
    kind: 'metadata',
    locator: locator(),
    excerpt:
      'Демонстрационная карточка доказательства. Исследование посвящено горению твёрдых образцов и влиянию условий. Точная строка и страница проверяются при подготовке корпуса.',
    table_values: [],
    verified: false,
    verification_note: 'UI fixture; не прошедшее научную проверку доказательство.',
  },
  {
    id: 'ev_demo_smoke',
    data_revision: REVISION,
    source_id: 'src_psi101',
    kind: 'metadata',
    locator: locator(),
    excerpt: 'Демонстрационная карточка метаданных SAME-R для просмотра измерений дыма.',
    table_values: [],
    verified: false,
    verification_note: 'UI fixture; не научный вывод.',
  },
];
export const claims: Schema['Claim'][] = [
  {
    id: 'clm_inv_psi25',
    data_revision: REVISION,
    investigation_ids: ['inv_psi25'],
    kind: 'synthesis',
    text: 'Влияние вентиляции следует изучать вместе с материалом, геометрией и атмосферой опыта.',
    supporting_evidence_ids: ['ev_demo_bass'],
    contradicting_evidence_ids: [],
    applicable_run_ids: [],
    limitations: [
      'Демонстрационная формулировка из продуктового сценария. Требуется проверенный пакет доказательств.',
    ],
    review_status: 'pending',
  },
  {
    id: 'clm_bass_hypothesis',
    data_revision: REVISION,
    investigation_ids: ['inv_psi25'],
    kind: 'hypothesis',
    text: 'Можно ли перенести наблюдения на условия конкретной лунной базы?',
    supporting_evidence_ids: [],
    contradicting_evidence_ids: [],
    applicable_run_ids: [],
    limitations: ['Это вопрос для проверки, а не установленный результат.'],
    review_status: 'pending',
  },
  {
    id: 'clm_inv_psi69',
    data_revision: REVISION,
    investigation_ids: ['inv_psi69'],
    kind: 'observation',
    text: 'В контрольной записи 30CAL03 время горения составляет 6,34 с при начальном диаметре 1,92 мм.',
    supporting_evidence_ids: ['ev_psi69_30cal03'],
    contradicting_evidence_ids: [],
    applicable_run_ids: ['run_psi69_30cal03'],
    limitations: ['Один опыт не устанавливает причинную зависимость. Контрольный пример из ТЗ.'],
    review_status: 'reviewed',
  },
  {
    id: 'clm_inv_psi101',
    data_revision: REVISION,
    investigation_ids: ['inv_psi101'],
    kind: 'synthesis',
    text: 'Данные о частицах дыма отвечают задаче обнаружения; они не являются испытаниями погасания пламени.',
    supporting_evidence_ids: ['ev_demo_smoke'],
    contradicting_evidence_ids: [],
    applicable_run_ids: [],
    limitations: ['Демонстрационное описание направления исследования.'],
    review_status: 'pending',
  },
];
export const config: Schema['Config'] = {
  contract_version: '1.2.0',
  active_data_revision: REVISION,
  feature_flags: { analysis: true, reports: true, semantic_search: false, video_preview: false },
  limits: {
    search_limit_max: 100,
    run_limit_max: 200,
    measurement_limit_max: 1000,
    question_chars_max: 2000,
    comparison_max: 3,
    analysis_deadline_s: 45,
    report_deadline_s: 30,
  },
  dictionaries: {
    ...dictionaries,
    scope: [
      { value: 'prevention', label: 'Предотвращение' },
      { value: 'detection', label: 'Обнаружение' },
      { value: 'suppression', label: 'Подавление' },
    ],
    fuel_state: [
      { value: 'solid', label: 'Твёрдое' },
      { value: 'liquid', label: 'Жидкое' },
      { value: 'gas', label: 'Газ' },
      { value: 'aerosol', label: 'Аэрозоль' },
    ],
    gravity_regime: [
      { value: 'microgravity', label: 'Микрогравитация' },
      { value: 'normal', label: 'Земная гравитация' },
      { value: 'partial', label: 'Частичная гравитация' },
      { value: 'simulated_partial', label: 'Имитация частичной' },
      { value: 'unknown', label: 'Неизвестно' },
    ],
    materials: materials.map((m) => ({ value: m.id, label: m.label })),
  },
  measurement_axes: [
    {
      x_key: 'sample.initial_diameter',
      y_key: 'metrics.burn_duration',
      investigation_ids: ['inv_psi69'],
    },
  ],
  retention: { workspace_days: 7, report_hours: 24 },
};
export function applicability(scenario: Scenario): Schema['ApplicabilityResult'] {
  const partial = ['partial', 'simulated_partial'].includes(scenario.gravity_regime);
  return {
    overall: partial ? 'related_evidence' : 'direct_evidence',
    factors: [
      {
        field: 'Гравитация',
        status: partial ? 'not_covered' : 'match',
        explanation: partial
          ? 'В демонстрационном наборе нет прямых опытов частичной гравитации. Перенос требует обоснования.'
          : 'Доступны исследования микрогравитации.',
        evidence_ids: [],
      },
      {
        field: 'Кислород и давление',
        status: 'unknown',
        explanation:
          'Проверяйте концентрацию кислорода и общее давление отдельно; отсутствие значения не означает совпадение.',
        evidence_ids: [],
      },
      {
        field: 'Материал и геометрия',
        status: 'unknown',
        explanation: 'Проверьте состав, толщину и геометрию конкретного образца.',
        evidence_ids: [],
      },
    ],
    gaps: partial
      ? [
          {
            field: 'gravity_regime',
            description: 'Нет прямых измерений для целевого режима.',
            suggested_next_step: 'Сохранить ограничение и уточнить необходимые испытания.',
          },
        ]
      : [],
    basis: { reviewed_rules_version: 'demo-ui-v1', data_revision: REVISION },
  };
}
