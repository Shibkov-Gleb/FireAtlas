// @vitest-environment node
import { expect, it } from 'vitest';
import { quantity } from '../mocks/fixtures';
import { formatQuantity } from './format';
it('distinguishes zero, null, not applicable and unusable values', () => {
  expect(formatQuantity(quantity(0, 'm_s', ['ev_0'], '0', 'm/s'))).toBe('0 cm/s');
  expect(formatQuantity(quantity(null, 'Pa'))).toBe('Not reported by the source');
  expect(formatQuantity({ ...quantity(null, 'm'), status: 'not_applicable' })).toBe(
    'Not applicable',
  );
  expect(formatQuantity({ ...quantity(null, 'm'), status: 'unusable' })).toBe(
    'Value or unit is unusable',
  );
});
it('converts canonical lengths without adding significant digits', () => {
  expect(formatQuantity(quantity(0.00192, 'm', ['ev_1'], '1.92', 'mm'), 'm')).toBe('1.92 mm');
  expect(formatQuantity(quantity(6.34, 's', ['ev_1'], '6.34', 's'), 's')).toBe('6.34 s');
  expect(formatQuantity(quantity(0.21, 'fraction', ['ev_1'], '0.21', 'fraction'))).toBe('21 %');
});
it('does not present mismatched units as a valid parameter', () => {
  expect(formatQuantity(quantity(1, 's', ['ev_1']), 'm')).toBe(
    'Unit is incompatible with this parameter',
  );
});
