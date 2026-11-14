import type { Quantity, Scenario, Schema } from '../api/types';

export type MissionDraft = {
  name: string;
  safety_task: Schema['Scope'];
  oxygen: string;
  pressure: string;
  airflow: string;
  geometry: Schema['Geometry'] | '';
  material_ids: string[];
  gravity_regime: Schema['Gravity'];
};
export const presetDefinitions = [
  {
    id: 'orbital_custom',
    name: 'Орбитальная станция',
    description: 'Орбита · микрогравитация',
    environment: 'orbital_habitat',
    celestial_body: 'earth',
    gravity_regime: 'microgravity',
  },
  {
    id: 'lunar_base',
    name: 'Лунная база',
    description: 'Поверхность Луны · частичная гравитация',
    environment: 'surface_habitat',
    celestial_body: 'moon',
    gravity_regime: 'partial',
  },
  {
    id: 'mars_rover',
    name: 'Герметичный ровер',
    description: 'Поверхность Марса · частичная гравитация',
    environment: 'pressurized_rover',
    celestial_body: 'mars',
    gravity_regime: 'partial',
  },
] as const;
export function makePreset(id: string): Scenario {
  const preset = presetDefinitions.find((p) => p.id === id) ?? presetDefinitions[0]!;
  return {
    scenario_id: preset.id,
    name: preset.name,
    environment: preset.environment,
    celestial_body: preset.celestial_body,
    safety_task: 'prevention',
    material_ids: [],
    geometry: null,
    oxygen_fraction: null,
    pressure: null,
    airflow_speed: null,
    gravity_regime: preset.gravity_regime,
    assumptions: [],
  };
}
export function scenarioToDraft(scenario: Scenario): MissionDraft {
  return {
    name: scenario.name,
    safety_task: scenario.safety_task,
    oxygen:
      scenario.oxygen_fraction?.value == null ? '' : String(scenario.oxygen_fraction.value * 100),
    pressure: scenario.pressure?.value == null ? '' : String(scenario.pressure.value / 1000),
    airflow:
      scenario.airflow_speed?.value == null ? '' : String(scenario.airflow_speed.value * 100),
    geometry: scenario.geometry ?? '',
    material_ids: scenario.material_ids,
    gravity_regime: scenario.gravity_regime,
  };
}
function inputQuantity(
  raw: string,
  unit: Quantity['unit'],
  factor: number,
  rawUnit: string,
): Quantity | null {
  return raw.trim() === ''
    ? null
    : {
        value: Number(raw) * factor,
        unit,
        status: 'reported',
        qualifier: 'eq',
        raw_value: raw,
        raw_unit: rawUnit,
        uncertainty: null,
        evidence_ids: [],
        derivation: null,
      };
}
export function draftToScenario(
  draft: MissionDraft,
  base: Scenario,
): { scenario: Scenario; error: string | null } {
  let error: string | null = null;
  for (const [label, value, max] of [
    ['Кислород', draft.oxygen, 100],
    ['Давление', draft.pressure, Infinity],
    ['Скорость воздуха', draft.airflow, Infinity],
  ] as const)
    if (
      value.trim() !== '' &&
      (!Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > max)
    )
      error = `${label}: укажите допустимое конечное значение.`;
  if (draft.name.trim().length < 3 || draft.name.length > 100)
    error = 'Название миссии должно содержать от 3 до 100 символов.';
  const scenario: Scenario = {
    ...base,
    name: draft.name.trim(),
    safety_task: draft.safety_task,
    geometry: draft.geometry || null,
    material_ids: draft.material_ids,
    gravity_regime: draft.gravity_regime,
    oxygen_fraction: inputQuantity(draft.oxygen, 'fraction', 0.01, '%'),
    pressure: inputQuantity(draft.pressure, 'Pa', 1000, 'kPa'),
    airflow_speed: inputQuantity(draft.airflow, 'm_s', 0.01, 'cm/s'),
    assumptions: [],
  };
  for (const [field, value] of [
    ['oxygen_fraction', draft.oxygen],
    ['pressure', draft.pressure],
    ['airflow_speed', draft.airflow],
  ] as const)
    if (value.trim() !== '')
      scenario.assumptions.push({
        field,
        text: `Значение введено пользователем: ${value}. Это условие сценария, а не измерение NASA.`,
        origin: 'user',
        source_ids: [],
      });
  return { scenario, error };
}
