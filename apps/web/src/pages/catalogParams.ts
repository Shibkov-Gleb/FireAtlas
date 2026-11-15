import { emptyFilters, type Filters, type Schema } from '../api/types';

export const rangeKeys = [
  {
    name: 'Кислород',
    prefix: 'o2',
    field: 'oxygen_range',
    unit: 'fraction',
    factor: 100,
    label: '%',
    max: 100,
  },
  {
    name: 'Давление',
    prefix: 'pressure',
    field: 'pressure_range',
    unit: 'Pa',
    factor: 0.001,
    label: 'кПа',
    max: undefined,
  },
  {
    name: 'Скорость воздуха',
    prefix: 'airflow',
    field: 'airflow_range',
    unit: 'm_s',
    factor: 100,
    label: 'см/с',
    max: undefined,
  },
] as const;
export function parseCatalog(
  params: URLSearchParams,
  revision: string,
  scenario: Schema['Scenario'],
): { request: Schema['SearchRequest']; error: string | null } {
  const filters: Filters = {
    ...emptyFilters(),
    scopes: params
      .getAll('scope')
      .filter((v): v is Schema['Scope'] => ['prevention', 'detection', 'suppression'].includes(v)),
    investigation_ids: params.getAll('investigation'),
    material_ids: params.getAll('material'),
    fuel_states: params
      .getAll('fuel')
      .filter((v): v is Schema['FuelState'] => ['solid', 'liquid', 'gas', 'aerosol'].includes(v)),
    gravity_regimes: params
      .getAll('gravity')
      .filter((v): v is Schema['Gravity'] =>
        ['normal', 'microgravity', 'partial', 'simulated_partial', 'unknown'].includes(v),
      ),
    include_unknown: params.get('unknown') === 'true',
    has_measurements:
      params.get('measurements') === 'true'
        ? true
        : params.get('measurements') === 'false'
          ? false
          : null,
  };
  let error: string | null = null;
  for (const { name, prefix, field, unit } of rangeKeys) {
    const rawMin = params.get(`${prefix}_min`);
    const rawMax = params.get(`${prefix}_max`);
    if (rawMin !== null || rawMax !== null) {
      const min = rawMin === null ? null : Number(rawMin),
        max = rawMax === null ? null : Number(rawMax);
      if (
        (min !== null && (!Number.isFinite(min) || min < 0)) ||
        (max !== null && (!Number.isFinite(max) || max < 0)) ||
        (min !== null && max !== null && min > max) ||
        (unit === 'fraction' && ((min !== null && min > 1) || (max !== null && max > 1)))
      )
        error = `${name}: проверьте границы диапазона.`;
      filters[field] = { min, max, unit };
    }
  }
  const query = params.get('q') ?? '';
  if (
    !query &&
    !filters.scopes.length &&
    !filters.investigation_ids.length &&
    !filters.material_ids.length &&
    !filters.fuel_states.length &&
    !filters.gravity_regimes.length &&
    !filters.oxygen_range &&
    !filters.pressure_range &&
    !filters.airflow_range &&
    filters.has_measurements === null
  )
    filters.scopes = ['prevention', 'detection', 'suppression'];
  if (query.length > 2000) error = 'Вопрос должен содержать не более 2000 символов.';
  return {
    request: {
      query,
      locale: 'ru',
      data_revision: revision,
      filters,
      scenario,
      include_related: params.get('related') === 'true',
      cursor: params.get('cursor'),
      limit: 20,
      sort: params.get('sort') === 'title' ? 'title' : 'relevance',
    },
    error,
  };
}
