import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import {
  DashboardsService,
  Dashboard,
  DashboardData,
  DashboardDefinition,
} from './dashboards';

describe('DashboardsService', () => {
  let svc: DashboardsService;
  let http: HttpTestingController;

  const definition: DashboardDefinition = {
    model: 'sale.order',
    fields: ['amount_total'],
    group_by: ['user_id'],
    domain: [],
    aggregations: { amount_total: 'sum' },
  };

  const nativeDashboard: Dashboard = {
    menu_key: 'ventas-por-vendedor',
    name: 'Ventas por vendedor',
    embed_url: null,
    definition,
    active: true,
  };

  const data: DashboardData = {
    menu_key: 'ventas-por-vendedor',
    name: 'Ventas por vendedor',
    model: 'sale.order',
    columns: [
      { key: 'user_id', label: 'Salesperson', kind: 'group' },
      { key: 'amount_total', label: 'Total (sum)', kind: 'aggregate', function: 'sum' },
    ],
    rows: [{ user_id: [7, 'J. Perez'], amount_total: 152340.5, __count: 42 }],
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    svc = TestBed.inject(DashboardsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('getByMenuKey() GETs /dashboards/{menuKey} with widened nullable shape', () => {
    let got: unknown;
    svc.getByMenuKey('dashboards').subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/dashboards');
    expect(req.request.method).toBe('GET');
    req.flush({ name: 'Dashboards', embed_url: 'https://bi.example/x', definition: null });
    expect(got).toEqual({ name: 'Dashboards', embed_url: 'https://bi.example/x', definition: null });
  });

  it('getByMenuKey() accepts a native dashboard response (embed_url null, definition set)', () => {
    let got: unknown;
    svc.getByMenuKey('ventas-por-vendedor').subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor');
    req.flush({ name: 'Ventas por vendedor', embed_url: null, definition });
    expect(got).toEqual({ name: 'Ventas por vendedor', embed_url: null, definition });
  });

  it('list() GETs /dashboards/', () => {
    const mock: Dashboard[] = [nativeDashboard];
    let got: Dashboard[] | undefined;
    svc.list().subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/');
    expect(req.request.method).toBe('GET');
    req.flush(mock);
    expect(got).toEqual(mock);
  });

  it('create() POSTs the dashboard body to /dashboards/', () => {
    const body = {
      menu_key: 'ventas-por-vendedor',
      name: 'Ventas por vendedor',
      definition,
      active: false,
    };
    let got: Dashboard | undefined;
    svc.create(body).subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);
    req.flush(nativeDashboard);
    expect(got).toEqual(nativeDashboard);
  });

  it('update() PATCHes /dashboards/{menuKey} with the patch body', () => {
    const patch = { name: 'Renombrado', active: true };
    let got: Dashboard | undefined;
    svc.update('ventas-por-vendedor', patch).subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual(patch);
    req.flush({ ...nativeDashboard, ...patch });
    expect(got?.name).toBe('Renombrado');
  });

  it('delete() DELETEs /dashboards/{menuKey}', () => {
    let done = false;
    svc.delete('ventas-por-vendedor').subscribe(() => (done = true));
    const req = http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor');
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: 'No Content' });
    expect(done).toBe(true);
  });

  it('getData() GETs /dashboards/{menuKey}/data', () => {
    let got: DashboardData | undefined;
    svc.getData('ventas-por-vendedor').subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor/data');
    expect(req.request.method).toBe('GET');
    req.flush(data);
    expect(got).toEqual(data);
  });

  it('preview() POSTs the definition to /dashboards/preview', () => {
    let got: DashboardData | undefined;
    svc.preview(definition).subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/dashboards/preview');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(definition);
    req.flush(data);
    expect(got).toEqual(data);
  });
});
