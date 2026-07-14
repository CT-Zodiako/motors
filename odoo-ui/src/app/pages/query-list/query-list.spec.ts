import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { QueryList } from './query-list';
import { OdooQuery } from '../../services/odoo-queries';

const ROWS: OdooQuery[] = [
  { id: 1, name: 'zeta', description: '', model: 'res.partner', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Finance' } },
  { id: 2, name: 'alpha', description: '', model: 'res.partner', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 1, name: 'General' } },
  { id: 3, name: 'beta', description: '', model: 'res.partner', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 3, name: 'Audit' } },
  { id: 4, name: 'gamma', description: '', model: 'res.partner', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Finance' } },
];

const CATEGORIES = [
  { id: 1, name: 'General', description: null, created_at: '' },
  { id: 2, name: 'Finance', description: null, created_at: '' },
  { id: 3, name: 'Audit', description: null, created_at: '' },
];

describe('QueryList (query-categories)', () => {
  let http: HttpTestingController;
  let component: QueryList;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [QueryList],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
      ],
    });
    const fixture = TestBed.createComponent(QueryList);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges(); // ngOnInit load
    http.expectOne('http://localhost:8000/queries/').flush(ROWS);
    http.expectOne('http://localhost:8000/categories/').flush(CATEGORIES);
  });

  afterEach(() => http.verify());

  it('rows are grouped by category: alphabetical group order, then name', () => {
    const sorted = component.sortedQueries();
    expect(sorted.map((q) => q.category?.name)).toEqual(['Audit', 'Finance', 'Finance', 'General']);
    expect(sorted.map((q) => q.name)).toEqual(['beta', 'gamma', 'zeta', 'alpha']);
  });

  it('recategorize PATCHes and moves the row to the new group', () => {
    const row = component.sortedQueries().find((q) => q.name === 'alpha')!;
    component.onCategoryChange(row, 3);
    const req = http.expectOne('http://localhost:8000/queries/alpha');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ category_id: 3 });
    req.flush({ ...row, category: { id: 3, name: 'Audit' } });
    const updated = component.sortedQueries().find((q) => q.name === 'alpha')!;
    expect(updated.category?.name).toBe('Audit');
    // group order after moving: Audit now has beta + alpha first
    expect(component.sortedQueries().map((q) => q.name)).toEqual(['alpha', 'beta', 'gamma', 'zeta']);
  });

  it('recategorize error keeps the row in its original group', () => {
    const row = component.sortedQueries().find((q) => q.name === 'alpha')!;
    component.onCategoryChange(row, 3);
    http
      .expectOne('http://localhost:8000/queries/alpha')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    const still = component.sortedQueries().find((q) => q.name === 'alpha')!;
    expect(still.category?.name).toBe('General');
  });
});
