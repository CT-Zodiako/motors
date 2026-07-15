import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { QueryList } from './query-list';
import { OdooQuery } from '../../services/odoo-queries';
import { QueryEditStateService } from '../../services/query-edit-state';

const ROWS: OdooQuery[] = [
  { id: 1, name: 'zeta', description: '', model: 'res.partner', method: 'search_read', domain: [], fields: [], limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Finance' } },
];

const CATEGORIES = [
  { id: 2, name: 'Finance', description: null, created_at: '' },
];

describe('QueryList (editable-queries)', () => {
  let http: HttpTestingController;
  let component: QueryList;
  let editState: QueryEditStateService;
  let navigatedTo: string | null = null;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [QueryList],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
        QueryEditStateService,
      ],
    });
    const fixture = TestBed.createComponent(QueryList);
    component = fixture.componentInstance;
    editState = TestBed.inject(QueryEditStateService);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('http://localhost:8000/queries/').flush(ROWS);
    http.expectOne('http://localhost:8000/categories/').flush(CATEGORIES);
  });

  afterEach(() => http.verify());

  it('editQuery sets edit state and navigates via callback', () => {
    navigatedTo = null;
    component.onNavigateToTab = (tab) => { navigatedTo = tab; };
    const row = component.sortedQueries()[0];
    component.editQuery(row);
    expect(editState.state().query?.name).toBe('zeta');
    expect(navigatedTo).toBe('create');
  });

  it('editQuery without callback still sets state (no throw)', () => {
    component.onNavigateToTab = null;
    const row = component.sortedQueries()[0];
    expect(() => component.editQuery(row)).not.toThrow();
    expect(editState.state().query?.name).toBe('zeta');
  });
});
