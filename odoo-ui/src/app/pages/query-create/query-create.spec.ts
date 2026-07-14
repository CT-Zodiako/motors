import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { QueryCreate } from './query-create';

const CATEGORIES = [
  { id: 1, name: 'General', description: 'Default category', created_at: '' },
  { id: 2, name: 'Finance', description: null, created_at: '' },
];

function setup() {
  TestBed.configureTestingModule({
    imports: [QueryCreate],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      MessageService,
    ],
  });
  const fixture = TestBed.createComponent(QueryCreate);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges(); // ngOnInit: loads models + categories
  http.expectOne((r) => r.url.includes('/explore/models')).flush({ total: 0, models: [] });
  http.expectOne('http://localhost:8000/categories/').flush(CATEGORIES);
  return { fixture, component, http };
}

describe('QueryCreate (query-categories)', () => {
  let http: HttpTestingController;
  let component: QueryCreate;

  beforeEach(() => {
    const s = setup();
    http = s.http;
    component = s.component;
  });

  afterEach(() => http.verify());

  it('preselects "General" once categories load', () => {
    expect(component.selectedCategoryId()).toBe(1);
  });

  it('save() sends limit_val 100 and the selected category by default', () => {
    component.selectedModel.set({ label: 'Clientes', model: 'res.partner', description: '', icon: '' });
    component.queryName.set('t_wiz_1');
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/');
    expect(req.request.body.limit_val).toBe(100);
    expect(req.request.body.category_id).toBe(1);
    req.flush({ registered: 't_wiz_1' });
  });

  it('save() preserves an explicit limit', () => {
    component.selectedModel.set({ label: 'Clientes', model: 'res.partner', description: '', icon: '' });
    component.queryName.set('t_wiz_2');
    component.limitVal.set(250);
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/');
    expect(req.request.body.limit_val).toBe(250);
    req.flush({ registered: 't_wiz_2' });
  });

  it('inline create posts the category and preselects it', () => {
    component.newCategoryName.set('Audit');
    component.confirmNewCategory();
    const req = http.expectOne('http://localhost:8000/categories/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.name).toBe('Audit');
    req.flush({ id: 3, name: 'Audit', description: null, created_at: '' });
    expect(component.selectedCategoryId()).toBe(3);
    expect(component.categories().some((c) => c.name === 'Audit')).toBe(true);
  });

  it('inline create duplicate (409) shows feedback and keeps wizard state', () => {
    const msg = TestBed.inject(MessageService);
    let errorShown = false;
    (msg as any).add = (m: any) => {
      if (m.severity === 'error') errorShown = true;
    };
    component.selectedCategoryId.set(2);
    component.queryName.set('mi_query');
    component.newCategoryName.set('Finance');
    component.confirmNewCategory();
    http
      .expectOne('http://localhost:8000/categories/')
      .flush({ detail: 'Category name already exists' }, { status: 409, statusText: 'Conflict' });
    expect(errorShown).toBe(true);
    expect(component.selectedCategoryId()).toBe(2); // unchanged
    expect(component.queryName()).toBe('mi_query'); // wizard state intact
  });
});
