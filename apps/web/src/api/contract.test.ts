// @vitest-environment node
import { readFileSync, readdirSync } from 'node:fs';
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
    expect(validate(runs[0]!.conditions.oxygen_fraction)).toBe(true);
    expect(
      validator('QuantityFraction')({ ...runs[0]!.conditions.oxygen_fraction, unit: 'Pa' }),
    ).toBe(false);
    const base = makePreset('lunar_base');
    const result = draftToScenario({ ...scenarioToDraft(base), oxygen: '21' }, base);
    expect(validator('Scenario')(result.scenario)).toBe(true);
  });
  it('rejects empty report contents', () => {
    expect(
      validator('ReportRequest')({
        workspace_revision: 1,
        title: 'Report',
        answer_ids: [],
        investigation_ids: [],
        include_comparison: false,
        locale: 'en',
      }),
    ).toBe(false);
  });
  it('validates all handoff examples, including their envelopes', () => {
    const base = 'packages/contracts/examples';
    for (const directory of readdirSync(base, { withFileTypes: true }).filter((d) =>
      d.isDirectory(),
    )) {
      for (const file of readdirSync(`${base}/${directory.name}`).filter((f) =>
        f.endsWith('.json'),
      )) {
        const example = JSON.parse(readFileSync(`${base}/${directory.name}/${file}`, 'utf8'));
        const operation = Object.values(spec.paths)
          .flatMap((path: any) => Object.values(path))
          .find((op: any) => op.operationId === example.operation_id) as any;
        const response = operation.responses[String(example.response.status)];
        const ref = response.content?.['application/json']?.schema?.$ref;
        if (ref) {
          const validate = validator(ref.split('/').at(-1));
          expect(
            validate(example.response.body),
            `${file}: ${JSON.stringify(validate.errors)}`,
          ).toBe(true);
        }
      }
    }
  });
});
