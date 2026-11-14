import type { Quantity, Schema } from '../api/types';
export const statusLabels: Record<Quantity['status'], string> = {
  measured: 'Измерено',
  reported: 'Сообщено в источнике',
  derived: 'Вычислено',
  not_reported: 'Не сообщено в источнике',
  not_applicable: 'Неприменимо',
  unusable: 'Значение или единица непригодны',
};
const units: Record<Quantity['unit'], { factor: number; label: string }> = {
  Pa: { factor: 0.001, label: 'кПа' },
  m_s: { factor: 100, label: 'см/с' },
  m: { factor: 1000, label: 'мм' },
  s: { factor: 1, label: 'с' },
  K: { factor: 1, label: 'K' },
  fraction: { factor: 100, label: '%' },
  g_fraction: { factor: 1, label: 'g' },
  count: { factor: 1, label: 'шт.' },
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
    return 'Единица несовместима с параметром';
  const unit = units[quantity.unit];
  if (!unit) return 'Неизвестная единица';
  const prefix: Record<string, string> = { lt: '< ', lte: '≤ ', gt: '> ', gte: '≥ ', eq: '' };
  const value = new Intl.NumberFormat('ru-RU', {
    maximumSignificantDigits: significantDigits(quantity.raw_value),
    useGrouping: false,
  }).format(quantity.value * unit.factor);
  return `${quantity.qualifier ? (prefix[quantity.qualifier] ?? '') : ''}${value}${unit.label ? ` ${unit.label}` : ''}`;
}
export const formatDate = (date: string) => {
  const value = new Date(date);
  return Number.isNaN(value.getTime())
    ? 'Дата не сообщена'
    : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(value);
};
export const outcomeLabels: Record<Schema['TestRun']['terminal_outcome']['category'], string> = {
  no_ignition: 'Воспламенения нет',
  extinction: 'Погасание',
  burn_to_completion: 'Полное выгорание',
  disruption: 'Разрушение капли',
  ongoing_at_stop: 'Горение при остановке',
  smoke_measurement: 'Измерение дыма',
  unknown: 'Неизвестно',
};
export const geometryLabels: Record<Schema['Geometry'], string> = {
  film: 'Плёнка',
  sheet: 'Лист',
  slab: 'Пластина',
  rod: 'Стержень',
  sphere: 'Сфера',
  droplet: 'Капля',
  fabric: 'Ткань',
  other: 'Другое',
  unknown: 'Неизвестно',
};
