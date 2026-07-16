import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { ScheduleManager } from './schedule-manager';
import { OdooQuery } from '../../services/odoo-queries';

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

const QUERIES: OdooQuery[] = [
  { id: 1, name: 'ventas', description: '', model: 'sale.order', method: 'search_read', domain: [], fields: [], limit_val: 100, active: true, created_at: '', category: { id: 1, name: 'Ventas' } },
];

const DATASETS = [{ id: 'ds1', project: 'p' }];
const TABLES = [{ id: 'tbl1', dataset_id: 'ds1', full_id: 'p.ds1.tbl1', rows: 0, bytes: 0, columns: [] }];

describe('ScheduleManager', () => {
  let http: HttpTestingController;
  let component: ScheduleManager;
  let fixture: ReturnType<typeof TestBed.createComponent<ScheduleManager>>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ScheduleManager],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
      ],
    });
    fixture = TestBed.createComponent(ScheduleManager);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('http://localhost:8000/schedules/').flush([]);
    http.expectOne('http://localhost:8000/queries/').flush(QUERIES);
    http.expectOne('http://localhost:8000/bigquery/datasets').flush({ datasets: DATASETS });
  });

  afterEach(() => http.verify());

  it('pre-fills dataset and table from query destination when query is selected', () => {
    component.openCreate();
    component.queryName = 'ventas';
    component.onQueryChange();

    http.expectOne('http://localhost:8000/queries/ventas/destination').flush({
      id: 1,
      query_name: 'ventas',
      dataset_id: 'ds1',
      table_id: 'tbl1',
      origin: 'manual',
      stale: false,
      last_error: null,
      last_sync_at: null,
      last_schema: null,
      created_at: '2026-01-01T00:00:00',
    });
    http.expectOne('http://localhost:8000/bigquery/tables/ds1').flush({ dataset_id: 'ds1', tables: TABLES });

    expect(component.datasetId).toBe('ds1');
    expect(component.tableId).toBe('tbl1');
  });

  it('leaves dataset and table empty when query has no destination', () => {
    component.openCreate();
    component.queryName = 'ventas';
    component.onQueryChange();

    http.expectOne('http://localhost:8000/queries/ventas/destination').flush(null, { status: 404, statusText: 'Not Found' });

    expect(component.datasetId).toBe('');
    expect(component.tableId).toBe('');
  });
});
