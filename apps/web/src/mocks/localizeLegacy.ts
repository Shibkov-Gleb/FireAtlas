import messages from '../../../../packages/contracts/english-messages.json';

const catalogue: Record<string, string> = messages;
const keys = Object.keys(catalogue)
  .filter((key) => key.trim().length > 2)
  .sort((a, b) => b.length - a.length);
const pattern = new RegExp(
  keys.map((key) => key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'),
  'g',
);

export function englishDemoPayload<T>(value: T): T {
  if (typeof value === 'string') {
    if (!/[\u0400-\u04ff]/u.test(value)) return value;
    return (catalogue[value] ?? value.replace(pattern, (match) => catalogue[match]!)) as T;
  }
  if (Array.isArray(value)) return value.map(englishDemoPayload) as T;
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, englishDemoPayload(item)]),
    ) as T;
  return value;
}
