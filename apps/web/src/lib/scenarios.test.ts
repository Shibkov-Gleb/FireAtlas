// @vitest-environment node
import { expect, it } from 'vitest';
import { draftToScenario, makePreset, scenarioToDraft } from './scenarios';
it('does not invent atmosphere or carry conditions into another preset', () => {
  const moon = makePreset('lunar_base');
  expect(moon.gravity_regime).toBe('partial');
  expect(moon.oxygen_fraction).toBeNull();
  expect(moon.pressure).toBeNull();
  expect(makePreset('orbital_custom').airflow_speed).toBeNull();
});
it('converts user conditions and records their origin separately', () => {
  const base = makePreset('orbital_custom');
  const { scenario, error } = draftToScenario(
    { ...scenarioToDraft(base), oxygen: '21', pressure: '101.3', airflow: '0' },
    base,
  );
  expect(error).toBeNull();
  expect(scenario.oxygen_fraction?.value).toBe(0.21);
  expect(scenario.pressure?.value).toBe(101300);
  expect(scenario.airflow_speed?.value).toBe(0);
  expect(scenario.assumptions.every((a) => a.origin === 'user')).toBe(true);
});
it('rejects impossible oxygen and nonfinite inputs', () => {
  const base = makePreset('lunar_base');
  expect(draftToScenario({ ...scenarioToDraft(base), oxygen: '110' }, base).error).toBeTruthy();
  expect(
    draftToScenario({ ...scenarioToDraft(base), pressure: 'Infinity' }, base).error,
  ).toBeTruthy();
});
