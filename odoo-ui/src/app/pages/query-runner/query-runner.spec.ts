import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import type { Table } from 'primeng/table';
import { QueryRunner } from './query-runner';
import { OdooQuery } from '../../services/odoo-queries';

// jsdom lacks these browser APIs used by PrimeNG internals.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const ROWS: OdooQuery[] = [
  { id: 1, name: 'ventas_hoy', description: '', model: 'sale.order', method: 'search_read', domain: [], fields: [], limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Ventas' } },
  { id: 2, name: 'clientes', description: '', model: 'res.partner', method: 'search_read', domain: [], fields: [], limit_val: 100, active: true, created_at: '', category: { id: 1, name: 'Clientes' } },
  { id: 3, name: 'facturas', description: '', model: 'account.move', method: 'search_read', domain: [], fields: [], limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Ventas' } },
  { id: 4, name: 'inactivo', description: '', model: 'res.partner', method: 'search_read', domain: [], fields: [], limit_val: 100, active: false, created_at: '', category: { id: 1, name: 'Clientes' } },
];

describe('QueryRunner (query-categories)', () => {
  let http: HttpTestingController;
  let component: QueryRunner;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [QueryRunner],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
      ],
    });
    const fixture = TestBed.createComponent(QueryRunner);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('http://localhost:8000/queries/').flush(ROWS);
  });

  afterEach(() => http.verify());

  it('groups selector options by category, alphabetical, active only', () => {
    const groups = component.groupedQueries();
    expect(groups.map((g) => g.label)).toEqual(['Clientes', 'Ventas']);
    const ventas = groups.find((g) => g.label === 'Ventas')!;
    expect(ventas.items.map((q) => q.name).sort()).toEqual(['facturas', 'ventas_hoy']);
    // inactive queries are excluded from grouping
    expect(groups.flatMap((g) => g.items.map((q) => q.name))).not.toContain('inactivo');
  });
});

const RUN_RESULT = {
  query: 'ventas_hoy',
  total: 3,
  data: [
    { id: 1, name: 'Ana', city: 'Montevideo' },
    { id: 2, name: 'Bruno', city: 'Buenos Aires' },
    { id: 3, name: 'Carla', city: 'Montevideo' },
  ],
};

const fakeTable = () =>
  ({ filter: vi.fn(), clear: vi.fn() }) as unknown as Table;

describe('QueryRunner (visual column filters)', () => {
  let http: HttpTestingController;
  let component: QueryRunner;
  let fixture: ReturnType<typeof TestBed.createComponent<QueryRunner>>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [QueryRunner],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
      ],
    });
    fixture = TestBed.createComponent(QueryRunner);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('http://localhost:8000/queries/').flush(ROWS);
  });

  afterEach(() => http.verify());

  function runQuery() {
    component.selected.set(ROWS[0]);
    component.run();
    http.expectOne('http://localhost:8000/run/ventas_hoy').flush(RUN_RESULT);
    fixture.detectChanges();
  }

  const filterInputs = (): HTMLInputElement[] =>
    Array.from(fixture.nativeElement.querySelectorAll('input.col-filter-input'));

  const bodyRows = (): HTMLElement[] =>
    Array.from(fixture.nativeElement.querySelectorAll('.p-datatable-tbody > tr'));

  // PrimeNG Table.filter() is debounced (filterDelay = 300ms) via setTimeout.
  const waitFilterDebounce = async () => {
    await new Promise((r) => setTimeout(r, 350));
    fixture.detectChanges();
    await fixture.whenStable();
  };

  it('stores each column filter and applies a contains filter to the table', () => {
    const dt = fakeTable();
    component.onColumnFilter(dt, 'name', 'an');
    component.onColumnFilter(dt, 'city', 'monte');
    expect(component.columnFilters()).toEqual({ name: 'an', city: 'monte' });
    expect(dt.filter).toHaveBeenCalledWith('an', 'name', 'contains');
    expect(dt.filter).toHaveBeenCalledWith('monte', 'city', 'contains');
  });

  it('clearColumnFilters empties the filter state and clears the table', () => {
    const dt = fakeTable();
    component.columnFilters.set({ name: 'x' });
    component.clearColumnFilters(dt);
    expect(component.columnFilters()).toEqual({});
    expect(dt.clear).toHaveBeenCalled();
  });

  it('resets column filters when a query is executed again', () => {
    component.columnFilters.set({ name: 'x' });
    runQuery();
    expect(component.columnFilters()).toEqual({});
  });

  it('renders one visual filter input per visible column', () => {
    runQuery();
    expect(filterInputs().length).toBe(3);
  });

  it('typing in a column filter narrows the visible rows without touching result data', async () => {
    runQuery();
    const input = filterInputs()[1]; // name column
    input.value = 'ana';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await waitFilterDebounce();

    expect(component.columnFilters()).toEqual({ name: 'ana' });
    expect(bodyRows().length).toBe(1);
    // The underlying result set is untouched: filters are visual-only.
    expect(component.result()!.data.length).toBe(3);
  });

  it('hiding a column clears its visual filter so rows are not silently filtered', async () => {
    runQuery();
    const input = filterInputs()[1]; // name column
    input.value = 'ana';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await waitFilterDebounce();
    expect(bodyRows().length).toBe(1);

    component.toggleColumn('name');
    fixture.detectChanges();
    await waitFilterDebounce();

    expect(component.isChecked('name')).toBe(false);
    expect(component.columnFilters()).toEqual({});
    expect(filterInputs().length).toBe(2);
    expect(bodyRows().length).toBe(3);
  });

  it('clear button removes all column filters and restores every row', async () => {
    runQuery();
    const input = filterInputs()[2]; // city column
    input.value = 'montevideo';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await waitFilterDebounce();
    expect(bodyRows().length).toBe(2);

    const clearBtn: HTMLButtonElement = fixture.nativeElement.querySelector('.table-toolbar button');
    expect(clearBtn).toBeTruthy();
    clearBtn.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(component.columnFilters()).toEqual({});
    expect(bodyRows().length).toBe(3);
    // Button disappears once no filter is active.
    expect(fixture.nativeElement.querySelector('.table-toolbar button')).toBeNull();
  });

  it('BigQuery upload always sends the full result set, ignoring visual filters', () => {
    runQuery();
    // A filter that matches nothing must not shrink the upload payload.
    component.columnFilters.set({ name: 'zzz-no-match' });
    component.selectedBigQueryDataset = { id: 'ds', project: 'p' };
    component.selectedBigQueryTableId = 'tbl';
    component.bigQueryActionMode = 'now';

    component.confirmBigQueryUpload();

    const req = http.expectOne((r) =>
      r.url.startsWith('http://localhost:8000/bigquery/upload/ds/tbl')
    );
    expect((req.request.body as { rows: unknown[] }).rows).toEqual(RUN_RESULT.data);
    req.flush({ dataset_id: 'ds', table_id: 'tbl', rows_loaded: 3 });
  });
});
