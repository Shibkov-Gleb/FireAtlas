// @vitest-environment node
import { expect, it } from 'vitest';
import { orbitalScenario, REVISION } from '../mocks/fixtures';
import { parseCatalog } from './catalogParams';
it('keeps canonical range units and explicit unknown policy in URLs', () => {
  const { request, error } = parseCatalog(
    new URLSearchParams('o2_min=0.18&o2_max=0.23&pressure_min=90000&unknown=true'),
    REVISION,
    orbitalScenario,
  );
  expect(error).toBeNull();
  expect(request.filters!.oxygen_range).toEqual({ min: 0.18, max: 0.23, unit: 'fraction' });
  expect(request.filters!.pressure_range?.min).toBe(90000);
  expect(request.filters!.include_unknown).toBe(true);
});
it('blocks inverted, nonfinite and out-of-range oxygen values', () => {
  for (const query of ['o2_min=0.5&o2_max=0.2', 'pressure_min=NaN', 'o2_max=1.1'])
    expect(parseCatalog(new URLSearchParams(query), REVISION, orbitalScenario).error).toBeTruthy();
});
