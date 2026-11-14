import type { components } from './schema';
export type Schema = components['schemas'];
export type Quantity = Schema['Quantity'];
export type Investigation = Schema['Investigation'];
export type TestRun = Schema['TestRun'];
export type Workspace = Schema['Workspace'];
export type Scenario = Schema['Scenario'];
export type Filters = Schema['Filters'];
export type Source = Schema['Source'];
export type Evidence = Schema['Evidence'];
export type Job = Schema['Job'];
export type AnalysisResult = Schema['AnalysisResult'];
export type Report = Schema['Report'];
export type Envelope<T> = { data: T; meta: Schema['Meta'] };
export const emptyFilters = (): Filters => ({
  scopes: [],
  investigation_ids: [],
  material_ids: [],
  fuel_states: [],
  gravity_regimes: [],
  oxygen_range: null,
  pressure_range: null,
  airflow_range: null,
  has_measurements: null,
  include_unknown: false,
});
export const isTerminal = (state: Job['state']) =>
  ['succeeded', 'failed', 'cancelled', 'expired'].includes(state);
