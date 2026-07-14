import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { OdooQueriesService, OdooQuery } from './odoo-queries';

describe('OdooQueriesService (query-categories additions)', () => {
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

  it('updateCategory() PATCHes /queries/{name} with category_id', () => {
    let got: OdooQuery | undefined;
    svc.updateCategory('daily_sales', 4).subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/queries/daily_sales');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ category_id: 4 });
    req.flush({
      id: 9,
      name: 'daily_sales',
      description: '',
      model: 'sale.order',
      method: 'search_read',
      limit_val: 100,
      active: true,
      created_at: '',
      category: { id: 4, name: 'Finance' },
    } satisfies OdooQuery);
    expect(got?.category?.name).toBe('Finance');
  });

  it('create() accepts an optional category_id in the payload', () => {
    svc
      .create({
        name: 'q1',
        description: '',
        model: 'res.partner',
        method: 'search_read',
        domain: [],
        fields: ['name'],
        limit_val: 100,
        category_id: 2,
      })
      .subscribe();
    const req = http.expectOne('http://localhost:8000/queries/');
    expect(req.request.body.category_id).toBe(2);
    req.flush({ registered: 'q1' });
  });
});
