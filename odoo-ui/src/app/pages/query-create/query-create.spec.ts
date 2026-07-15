import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { QueryCreate } from './query-create';
import { QueryEditStateService } from '../../services/query-edit-state';
import { OdooQuery } from '../../services/odoo-queries';

const CATEGORIES = [
  { id: 1, name: 'General', description: 'Default category', created_at: '' },
  { id: 2, name: 'Finance', description: null, created_at: '' },
];

const mockQuery: OdooQuery = {
  id: 1, name: 'sales', description: 'Sales report', model: 'sale.order',
  method: 'search_read', domain: [['name', 'ilike', 'Acme']], fields: ['name', 'amount'], limit_val: 50,
  active: true, created_at: '', category: { id: 2, name: 'Finance' },
};

function setup() {
  TestBed.configureTestingModule({
    imports: [QueryCreate],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      MessageService,
      QueryEditStateService,
    ],
  });
  const fixture = TestBed.createComponent(QueryCreate);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();
  http.expectOne((r) => r.url.includes('/explore/models')).flush({ total: 0, models: [] });
  http.expectOne('http://localhost:8000/categories/').flush(CATEGORIES);
  return { fixture, component, http };
}

describe('QueryCreate (editable-queries edit mode)', () => {
  let http: HttpTestingController;
  let component: QueryCreate;
  let editState: QueryEditStateService;
  let fixture: ComponentFixture<QueryCreate>;

  beforeEach(() => {
    const s = setup();
    http = s.http;
    component = s.component;
    fixture = s.fixture;
    editState = TestBed.inject(QueryEditStateService);
  });

  afterEach(() => {
    // flush any unhandled requests with valid dummy responses so verify() passes
    http.match(() => true).forEach((r) => {
      if (r.request.url.includes('/explore/models')) r.flush({ total: 0, models: [] });
      else if (r.request.url.includes('/categories/')) r.flush([]);
      else if (r.request.url.includes('/explore/fields/')) r.flush({ fields: {} });
      else r.flush({});
    });
    http.verify();
    TestBed.resetTestingModule();
  });

  it('edit mode pre-fills name, limit, category, fields, and filters from the query', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    expect(component.isEditMode()).toBe(true);
    expect(component.queryName()).toBe('sales');
    expect(component.limitVal()).toBe(50);
    expect(component.selectedCategoryId()).toBe(2);
    expect(component.originalFields()).toEqual(['name', 'amount']);
    // fields prefill is async (getFields); simulate response
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: {
        name: { string: 'Nombre', type: 'char' },
        amount: { string: 'Monto', type: 'float' },
        date: { string: 'Fecha', type: 'date' },
      },
    });
    expect(component.checkedFields().has('name')).toBe(true);
    expect(component.checkedFields().has('amount')).toBe(true);
    expect(component.filters().length).toBe(1);
    expect(component.filters()[0]).toEqual({ field: 'name', operator: 'ilike', value: 'Acme' });
  });

  it('save in edit mode calls update() not create()', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.fields).toEqual(['amount', 'name']);
    req.flush({
      query: mockQuery,
      propagation: { total: 1, ok: 1, failed: 0, destinations: [{ dataset_id: 'd', table_id: 't', status: 'ok' }] },
    });
    expect(component.showPropagationDialog()).toBe(true);
  });

  it('removing fields shows destructive confirmation and does NOT send PATCH until confirmed', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    // uncheck 'amount' — now removed vs original
    component.toggleField('amount');
    component.save();
    expect(component.showDestructiveConfirm()).toBe(true);
    expect(component.removedFields()).toEqual(['amount']);
    // no PATCH request yet
    http.expectNone('http://localhost:8000/queries/sales');
  });

  it('confirmDestructiveSave proceeds with the update', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    component.toggleField('amount');
    component.save(); // triggers confirm
    component.confirmDestructiveSave();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.fields).toEqual(['name']);
    req.flush({ query: mockQuery, propagation: { total: 0, ok: 0, failed: 0, destinations: [] } });
    expect(component.showDestructiveConfirm()).toBe(false);
  });

  it('no removed fields → no confirm, direct save', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    // keep both fields checked (same as original)
    component.save();
    expect(component.showDestructiveConfirm()).toBe(false);
    const req = http.expectOne('http://localhost:8000/queries/sales');
    expect(req.request.method).toBe('PATCH');
    req.flush({ query: mockQuery, propagation: { total: 0, ok: 0, failed: 0, destinations: [] } });
  });

  it('preserves original description in PATCH payload', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    expect(req.request.body.description).toBe('Sales report');
    req.flush({ query: mockQuery, propagation: { total: 0, ok: 0, failed: 0, destinations: [] } });
  });

  it('in edit mode name input is readonly, model cards are non-interactive, and method is shown read-only', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    fixture.detectChanges();
    // name input is readonly/disabled
    const nameInput = fixture.nativeElement.querySelector('input.input-name');
    expect(nameInput).toBeTruthy();
    expect(nameInput.readOnly || nameInput.disabled).toBe(true);
    // model cards are not clickable (no pointer-events or disabled attribute)
    const modelCard = fixture.nativeElement.querySelector('.model-card');
    expect(modelCard).toBeTruthy();
    expect(modelCard.disabled || getComputedStyle(modelCard).pointerEvents === 'none').toBe(true);
    // method shown as read-only text
    const methodEl = fixture.nativeElement.querySelector('.method-readonly');
    expect(methodEl).toBeTruthy();
    expect(methodEl.textContent).toContain('search_read');
  });

  it('selectModel is a no-op when in edit mode', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    const prevModel = component.selectedModel();
    expect(prevModel).toBeTruthy();
    // try to select a different model
    component.selectModel({ label: 'Other', model: 'other.model', description: 'Other', icon: 'X' });
    expect(component.selectedModel()).toBe(prevModel); // unchanged
  });

  it('propagation summary includes pre-v1 self-register note', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    req.flush({ query: mockQuery, propagation: { total: 0, ok: 0, failed: 0, destinations: [] } });
    fixture.detectChanges();
    const dialog = fixture.nativeElement.querySelector('.propagation-summary');
    expect(dialog).toBeTruthy();
    expect(dialog.textContent).toContain('re-register');
  });

  it('400 error keeps edit mode and input state intact', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    req.flush({ detail: 'Invalid domain' }, { status: 400, statusText: 'Bad Request' });
    expect(component.isEditMode()).toBe(true);
    expect(component.editingQuery()).toBeTruthy();
    expect(component.queryName()).toBe('sales');
    expect(component.checkedFields().has('name')).toBe(true);
    expect(component.showPropagationDialog()).toBe(false);
  });
});
