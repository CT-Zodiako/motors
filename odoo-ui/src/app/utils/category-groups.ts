export interface Categorized {
  name: string;
  category?: { id: number; name: string } | null;
}

export interface CategoryGroup<T extends Categorized> {
  label: string;
  items: T[];
}

const UNCATEGORIZED = 'Sin categoría';

/** Groups rows by category name; groups sorted alphabetically. Shared by list + runner. */
export function toCategoryGroups<T extends Categorized>(rows: T[]): CategoryGroup<T>[] {
  const map = new Map<string, T[]>();
  for (const row of rows) {
    const label = row.category?.name ?? UNCATEGORIZED;
    const bucket = map.get(label);
    if (bucket) bucket.push(row);
    else map.set(label, [row]);
  }
  return [...map.entries()]
    .map(([label, items]) => ({ label, items }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** Flat sort by category name, then by row name. Used by the grouped p-table. */
export function sortByCategoryThenName<T extends Categorized>(rows: T[]): T[] {
  return [...rows].sort((a, b) => {
    const byCat = (a.category?.name ?? UNCATEGORIZED).localeCompare(
      b.category?.name ?? UNCATEGORIZED,
    );
    return byCat !== 0 ? byCat : a.name.localeCompare(b.name);
  });
}
