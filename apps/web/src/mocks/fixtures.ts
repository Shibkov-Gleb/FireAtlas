import dictionaries from '../../../../packages/contracts/dictionaries.en.json';
import type { Investigation, Quantity, Scenario, Schema, Source, TestRun } from '../api/types';

export const REVISION = 'demo-20261104-r1';
export const FIXTURE_METADATA = {
  fixture: true,
  description:
    'Demo UI dataset. Not a published scientific corpus. Five FLEX points come from the specification control records.',
};
export const orbitalScenario: Scenario = {
  scenario_id: 'orbital_custom',
  name: 'Orbital station',
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
  { id: 'mat_solid', label: 'Solid samples', state: 'solid', composition: null, aliases: [] },
  {
    id: 'mat_methanol',
    label: 'Methanol',
    state: 'liquid',
    composition: 'CH₃OH',
    aliases: ['Methanol'],
  },
  { id: 'mat_smoke', label: 'Smoke particles', state: 'aerosol', composition: null, aliases: [] },
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
    'BASS-II · research findings',
    'https://ntrs.nasa.gov/citations/20160000593',
    'report',
  ),
  makeSource(
    'src_psi69',
    'FLEX · Experimental Table, version 5',
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
    'NASA · combustion and fire safety on the ISS',
    'https://www.nasa.gov/missions/station/iss-research/studying-combustion-and-fire-safety/',
    'report',
  ),
  makeSource(
    'src_unavailable',
    'Example unavailable BASS-II attachment',
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
    'Solid-material combustion in microgravity',
    'prevention',
    'solid',
    'mat_solid',
    ['src_psi25', 'src_bass_report', 'src_unavailable'],
    [
      'Study flame spread and extinction on solid samples.',
      'Compare the effects of airflow, atmosphere and geometry.',
    ],
    'Research on solid samples in microgravity. Check setup and methods against the original source.',
  ),
  makeInvestigation(
    'inv_psi69',
    'PSI-69',
    'FLEX',
    'Liquid-fuel droplet combustion and extinction',
    'suppression',
    'liquid',
    'mat_methanol',
    ['src_psi69'],
    [
      'Study droplet combustion and extinction.',
      'Review measurements alongside atmosphere, pressure and initial size.',
    ],
    'Droplet experiments. This demo contains five methanol control records from the specification.',
  ),
  makeInvestigation(
    'inv_psi101',
    'PSI-101',
    'SAME-R',
    'Smoke properties for fire detection',
    'detection',
    'aerosol',
    'mat_smoke',
    ['src_psi101'],
    [
      'Study smoke particle characteristics.',
      'Compare smoke generation and measurement conditions.',
    ],
    'Smoke particle measurements. Smoke records are not interpreted as flame test outcomes.',
  ),
];
export const extraInvestigation = makeInvestigation(
  'inv_demo04',
  'DEMO-04',
  'DEMO-04',
  'Test card for the comparison limit',
  'prevention',
  'solid',
  'mat_solid',
  [],
  ['Synthetic interface card. Contains no scientific findings.'],
  'Only used in the comparison_limit test scenario.',
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
        'Control record from Appendix A; the demo dataset does not replace a verified corpus release.',
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
      raw_label: 'Not reported',
      interpretation_status: 'unmapped',
      evidence_ids: [],
    },
    evidence_ids: ['ev_demo_bass'],
    quality_notes: ['Synthetic UI record for zero and unknown values. Not a NASA result.'],
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
          raw_unit: 'unknown',
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
    quality_notes: ['Synthetic UI record. Units are unusable for this chart. Not a NASA result.'],
  },
];
export const runs = [...flexRuns, ...demoRuns];
const locator = (row: string | null = null): Schema['Locator'] => ({
  page: null,
  section: row ? 'Experimental Table FLEX, v5' : 'Investigation description',
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
      'Copied from a specification control record. Independent source verification is required before scientific publication.',
  })),
  {
    id: 'ev_demo_bass',
    data_revision: REVISION,
    source_id: 'src_bass_report',
    kind: 'metadata',
    locator: locator(),
    excerpt:
      'Demo evidence record. This investigation studies solid-sample combustion and the effects of conditions. Exact rows and pages are verified during corpus preparation.',
    table_values: [],
    verified: false,
    verification_note: 'UI fixture; not scientifically verified evidence.',
  },
  {
    id: 'ev_demo_smoke',
    data_revision: REVISION,
    source_id: 'src_psi101',
    kind: 'metadata',
    locator: locator(),
    excerpt: 'Demo SAME-R metadata record for exploring smoke measurements.',
    table_values: [],
    verified: false,
    verification_note: 'UI fixture; not a scientific finding.',
  },
];
export const claims: Schema['Claim'][] = [
  {
    id: 'clm_inv_psi25',
    data_revision: REVISION,
    investigation_ids: ['inv_psi25'],
    kind: 'synthesis',
    text: 'Ventilation effects must be considered alongside material, geometry and test atmosphere.',
    supporting_evidence_ids: ['ev_demo_bass'],
    contradicting_evidence_ids: [],
    applicable_run_ids: [],
    limitations: [
      'Demo wording from the product scenario. A verified evidence bundle is required.',
    ],
    review_status: 'pending',
  },
  {
    id: 'clm_bass_hypothesis',
    data_revision: REVISION,
    investigation_ids: ['inv_psi25'],
    kind: 'hypothesis',
    text: 'Can these observations be transferred to the conditions of a specific lunar base?',
    supporting_evidence_ids: [],
    contradicting_evidence_ids: [],
    applicable_run_ids: [],
    limitations: ['This is a question to investigate, not an established finding.'],
    review_status: 'pending',
  },
  {
    id: 'clm_inv_psi69',
    data_revision: REVISION,
    investigation_ids: ['inv_psi69'],
    kind: 'observation',
    text: 'Control record 30CAL03 reports a burn duration of 6.34 s at an initial diameter of 1.92 mm.',
    supporting_evidence_ids: ['ev_psi69_30cal03'],
    contradicting_evidence_ids: [],
    applicable_run_ids: ['run_psi69_30cal03'],
    limitations: [
      'One test run does not establish causality. Control example from the specification.',
    ],
    review_status: 'reviewed',
  },
  {
    id: 'clm_inv_psi101',
    data_revision: REVISION,
    investigation_ids: ['inv_psi101'],
    kind: 'synthesis',
    text: 'Smoke particle data address detection; they are not flame extinction tests.',
    supporting_evidence_ids: ['ev_demo_smoke'],
    contradicting_evidence_ids: [],
    applicable_run_ids: [],
    limitations: ['Demo description of a research area.'],
    review_status: 'pending',
  },
];
export const config: Schema['Config'] = {
  contract_version: '1.3.0',
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
      { value: 'prevention', label: 'Prevention' },
      { value: 'detection', label: 'Detection' },
      { value: 'suppression', label: 'Suppression' },
    ],
    fuel_state: [
      { value: 'solid', label: 'Solid' },
      { value: 'liquid', label: 'Liquid' },
      { value: 'gas', label: 'Gas' },
      { value: 'aerosol', label: 'Aerosol' },
    ],
    gravity_regime: [
      { value: 'microgravity', label: 'Microgravity' },
      { value: 'normal', label: 'Earth gravity' },
      { value: 'partial', label: 'Partial gravity' },
      { value: 'simulated_partial', label: 'Simulated partial gravity' },
      { value: 'unknown', label: 'Unknown' },
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
        field: 'Gravity',
        status: partial ? 'not_covered' : 'match',
        explanation: partial
          ? 'The demo dataset has no direct partial-gravity tests. Transfer requires justification.'
          : 'Microgravity investigations are available.',
        evidence_ids: [],
      },
      {
        field: 'Oxygen and pressure',
        status: 'unknown',
        explanation:
          'Check oxygen concentration and total pressure separately; a missing value does not imply a match.',
        evidence_ids: [],
      },
      {
        field: 'Material and geometry',
        status: 'unknown',
        explanation: 'Check the composition, thickness and geometry of the specific sample.',
        evidence_ids: [],
      },
    ],
    gaps: partial
      ? [
          {
            field: 'gravity_regime',
            description: 'No direct measurements for the target regime.',
            suggested_next_step: 'Keep this limitation and clarify the required tests.',
          },
        ]
      : [],
    basis: { reviewed_rules_version: 'demo-ui-v1', data_revision: REVISION },
  };
}
