import { describe, expect, it } from 'vitest';
import { toCategoryGroups, sortByCategoryThenName } from './category-groups';

interface Row {
  name: string;
  category?: { id: number; name: string } | null;
}

const rows: Row[] = [
  { name: 'zeta', category: { id: 2, name: 'Finance' } },
  { name: 'alpha', category: { id: 1, name: 'General' } },
  { name: 'beta', category: { id: 3, name: 'Audit' } },
  { name: 'gamma', category: { id: 2, name: 'Finance' } },
];

describe('toCategoryGroups', () => {
  it('groups by category name, groups sorted alphabetically', () => {
    const groups = toCategoryGroups(rows);
    expect(groups.map((g) => g.label)).toEqual(['Audit', 'Finance', 'General']);
  });

  it('keeps every row inside its category group', () => {
    const groups = toCategoryGroups(rows);
    const finance = groups.find((g) => g.label === 'Finance')!;
    expect(finance.items.map((r) => r.name).sort()).toEqual(['gamma', 'zeta']);
  });

  it('puts uncategorized rows under a fallback group', () => {
    const groups = toCategoryGroups([{ name: 'loose', category: null }]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe('Sin categoría');
    expect(groups[0].items[0].name).toBe('loose');
  });
});

describe('sortByCategoryThenName', () => {
  it('sorts by category name, then by query name', () => {
    const sorted = sortByCategoryThenName(rows);
    expect(sorted.map((r) => r.name)).toEqual(['beta', 'gamma', 'zeta', 'alpha']);
  });

  it('does not mutate the input array', () => {
    const input = [...rows];
    sortByCategoryThenName(input);
    expect(input.map((r) => r.name)).toEqual(['zeta', 'alpha', 'beta', 'gamma']);
  });
});
