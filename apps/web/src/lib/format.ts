import type { Quantity, Schema } from '../api/types';
export const statusLabels: Record<Quantity['status'], string> = {
  measured: 'Measured',
  reported: 'Reported by the source',
  derived: 'Derived',
  not_reported: 'Not reported by the source',
  not_applicable: 'Not applicable',
  unusable: 'Value or unit is unusable',
};
const units: Record<Quantity['unit'], { factor: number; label: string }> = {
  Pa: { factor: 0.001, label: 'kPa' },
  m_s: { factor: 100, label: 'cm/s' },
  m: { factor: 1000, label: 'mm' },
  s: { factor: 1, label: 's' },
  K: { factor: 1, label: 'K' },
  fraction: { factor: 100, label: '%' },
  g_fraction: { factor: 1, label: 'g' },
  count: { factor: 1, label: 'count' },
  dimensionless: { factor: 1, label: '' },
};
export function significantDigits(raw: string | null) {
  if (!raw) return 6;
  const match = raw.replace(',', '.').match(/[-+]?(?:\d*\.)?\d+(?:e[-+]?\d+)?/i);
  if (!match) return 6;
  const mantissa = match[0].split(/e/i)[0]!.replace(/[-+.]/g, '').replace(/^0+/, '');
  return Math.max(1, Math.min(12, mantissa.length));
}
export function formatQuantity(quantity: Quantity, expectedUnit?: Quantity['unit']): string {
  if (quantity.value === null) return statusLabels[quantity.status];
  if (!Number.isFinite(quantity.value) || (expectedUnit && quantity.unit !== expectedUnit))
    return 'Unit is incompatible with this parameter';
  const unit = units[quantity.unit];
  if (!unit) return 'Unknown unit';
  const prefix: Record<string, string> = { lt: '< ', lte: '≤ ', gt: '> ', gte: '≥ ', eq: '' };
  const value = new Intl.NumberFormat('en-US', {
    maximumSignificantDigits: significantDigits(quantity.raw_value),
    useGrouping: false,
  }).format(quantity.value * unit.factor);
  return `${quantity.qualifier ? (prefix[quantity.qualifier] ?? '') : ''}${value}${unit.label ? ` ${unit.label}` : ''}`;
}
export const formatDate = (date: string) => {
  const value = new Date(date);
  return Number.isNaN(value.getTime())
    ? 'Date not reported'
    : new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(value);
};
export const outcomeLabels: Record<Schema['TestRun']['terminal_outcome']['category'], string> = {
  no_ignition: 'No ignition',
  extinction: 'Extinction',
  burn_to_completion: 'Burn to completion',
  disruption: 'Droplet disruption',
  ongoing_at_stop: 'Burning at shutdown',
  smoke_measurement: 'Smoke measurement',
  unknown: 'Unknown',
};
export const geometryLabels: Record<Schema['Geometry'], string> = {
  film: 'Film',
  sheet: 'Sheet',
  slab: 'Slab',
  rod: 'Rod',
  sphere: 'Sphere',
  droplet: 'Droplet',
  fabric: 'Fabric',
  other: 'Other',
  unknown: 'Unknown',
};
