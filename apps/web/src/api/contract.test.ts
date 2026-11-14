// @vitest-environment node
import { readFileSync } from 'node:fs';
import { parse } from 'yaml';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { describe, expect, it } from 'vitest';
import {
  claims,
  config,
  evidence,
  investigations,
  orbitalScenario,
  runs,
  sources,
} from '../mocks/fixtures';
import { makePreset, scenarioToDraft, draftToScenario } from '../lib/scenarios';

const spec = parse(readFileSync('packages/contracts/openapi.yaml', 'utf8'));
const schemas = JSON.parse(
  JSON.stringify(spec.components.schemas).replaceAll('#/components/schemas/', '#/$defs/'),
);
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema({ $id: 'https://fire-atlas.local/schemas', $defs: schemas });
function validator(name: string) {
  return ajv.compile({ $ref: `https://fire-atlas.local/schemas#/$defs/${name}` });
}
describe('the same contract governs API fixtures and generated client types', () => {
  for (const [name, items] of [
    ['Source', sources],
    ['Investigation', investigations],
    ['TestRun', runs],
    ['Evidence', evidence],
    ['Claim', claims],
    ['Scenario', [orbitalScenario, makePreset('lunar_base')]],
    ['Config', [config]],
  ] as const) {
    it(`${name} examples satisfy the public JSON schema`, () => {
      const validate = validator(name);
      for (const item of items) expect(validate(item), JSON.stringify(validate.errors)).toBe(true);
    });
  }
  it('rejects unknown fields and missing revision', () => {
    const validate = validator('Investigation');
    expect(validate({ ...investigations[0], unexpected: true })).toBe(false);
    const value = { ...investigations[0] };
    delete (value as Partial<typeof value>).data_revision;
    expect(validate(value)).toBe(false);
  });
  it('distinguishes scientific evidence from user assumptions', () => {
    const validate = validator('Quantity');
    expect(validate({ ...runs[0]!.conditions.oxygen_fraction, evidence_ids: [] })).toBe(false);
    expect(validate({ ...runs[0]!.conditions.oxygen_fraction, value: null })).toBe(false);
    const base = makePreset('lunar_base');
    const result = draftToScenario({ ...scenarioToDraft(base), oxygen: '21' }, base);
    expect(validator('Scenario')(result.scenario)).toBe(true);
  });
  it('rejects empty report contents', () => {
    expect(
      validator('ReportRequest')({
        workspace_revision: 1,
        title: 'Отчёт',
        answer_ids: [],
        investigation_ids: [],
        include_comparison: false,
        locale: 'ru',
      }),
    ).toBe(false);
  });
  it('validates all handoff examples, including their envelopes', () => {
    const examples = JSON.parse(readFileSync('packages/contracts/examples/p0.json', 'utf8'));
    expect(examples.fixture).toBe(true);
    for (const entry of examples.cases) {
      const validate = validator(entry.schema);
      const payload = entry.kind === 'response' ? entry.payload.data : entry.payload;
      expect(validate(payload), `${entry.name}: ${JSON.stringify(validate.errors)}`).toBe(true);
      if (entry.kind === 'response') {
        const validateMeta = validator('Meta');
        expect(validateMeta(entry.payload.meta)).toBe(true);
      }
    }
  });
});
