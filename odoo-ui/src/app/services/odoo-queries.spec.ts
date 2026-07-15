import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { OdooQueriesService, OdooQuery } from './odoo-queries';

describe('OdooQueriesService (editable-queries additions)', () => {
  let svc: OdooQueriesService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    svc = TestBed.inject(OdooQueriesService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('update() PATCHes /queries/{name} with payload and returns propagation', () => {
    let got: any;
    svc.update('sales', { fields: ['name'], limit_val: 10 }).subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/queries/sales');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ fields: ['name'], limit_val: 10 });
    req.flush({
      query: { id: 1, name: 'sales' } as OdooQuery,
      propagation: { total: 2, ok: 2, failed: 0, destinations: [] },
    });
    expect(got.propagation.total).toBe(2);
  });

  it('update() URL-encodes names with spaces', () => {
    svc.update('sales report', { fields: ['name'] }).subscribe();
    const req = http.expectOne('http://localhost:8000/queries/sales%20report');
    expect(req.request.method).toBe('PATCH');
    req.flush({ query: {} as OdooQuery, propagation: { total: 0, ok: 0, failed: 0, destinations: [] } });
  });
});
