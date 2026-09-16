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

  it('opens a blank Create after leaving an unsaved edit', () => {
    fixture.destroy();
    editState.beginEdit(mockQuery);
    fixture = TestBed.createComponent(QueryCreate);
    fixture.detectChanges();
    component = fixture.componentInstance;
    http.expectOne((r) => r.url.includes('/explore/models')).flush({ total: 0, models: [] });
    http.expectOne('http://localhost:8000/categories/').flush(CATEGORIES);
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Name', type: 'char' }, amount: { string: 'Amount', type: 'float' } },
    });
    expect(component.isEditMode()).toBe(true);
    expect(component.queryName()).toBe('sales');
    expect(editState.state().query).toEqual(mockQuery);

    fixture.destroy();
    fixture = TestBed.createComponent(QueryCreate);
    fixture.detectChanges();
    component = fixture.componentInstance;
    http.expectOne((r) => r.url.includes('/explore/models')).flush({ total: 0, models: [] });
    http.expectOne('http://localhost:8000/categories/').flush(CATEGORIES);

    expect(component.isEditMode()).toBe(false);
    expect(editState.state().query).toBeNull();
    expect(component.editingQuery()).toBeNull();
    expect(component.queryName()).toBe('');
    expect(component.selectedModel()).toBeNull();
    expect(component.checkedFields().size).toBe(0);
    expect(component.buildDomain()).toEqual([]);
    expect(component.activeStep()).toBe(0);
    http.expectNone((r) => r.url.includes('/explore/fields/'));
    http.verify();
  });

  it('edit mode treats stored limit_val 0 as blank (all records)', () => {
    const noLimitQuery = { ...mockQuery, limit_val: 0 };
    editState.beginEdit(noLimitQuery);
    component.ngOnInit();
    expect(component.limitVal()).toBeNull();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: {
        name: { string: 'Nombre', type: 'char' },
        amount: { string: 'Monto', type: 'float' },
      },
    });
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    expect(req.request.body.limit_val).toBe(0);
    req.flush({
      query: noLimitQuery,
      propagation: { total: 0, ok: 0, failed: 0, destinations: [] },
    });
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

      it('in edit mode wizard lands on fields step, name is readonly, and method is shown read-only', () => {
        editState.beginEdit(mockQuery);
        component.ngOnInit();
        http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
          fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
        });
        fixture.detectChanges();
        // wizard skips model selection and starts directly on fields
        expect(component.activeStep()).toBe(1);
        // model cards are not rendered in the active step
        const modelCard = fixture.nativeElement.querySelector('.model-card');
        expect(modelCard).toBeNull();
        // name input is readonly/disabled
        const nameInput = fixture.nativeElement.querySelector('input.input-name');
        expect(nameInput).toBeTruthy();
        expect(nameInput.readOnly || nameInput.disabled).toBe(true);
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

  it('propagation summary shows retry note for failed destinations', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: { name: { string: 'Nombre', type: 'char' }, amount: { string: 'Monto', type: 'float' } },
    });
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/sales');
    req.flush({
      query: mockQuery,
      propagation: { total: 1, ok: 0, failed: 1, destinations: [{ dataset_id: 'analytics', table_id: 'sales_daily', status: 'failed', error: 'BQ not found' }] },
    });
    fixture.detectChanges();
    const note = fixture.nativeElement.querySelector('.retry-note');
    expect(note).toBeTruthy();
    expect(note.textContent).toContain('reintent');
  });

});

const RICH_FIELDS_RESPONSE = {
  fields: {
    id: { string: 'ID', type: 'integer', required: false, readonly: true },
    name: { string: 'Nombre', type: 'char', required: true, readonly: false, help: 'Nombre visible del registro' },
    partner_id: { string: 'Cliente', type: 'many2one', required: true, readonly: false, relation: 'res.partner', help: 'Cliente asociado a la venta' },
    amount: { string: 'Monto', type: 'float', required: false, readonly: true },
  },
};

describe('QueryCreate (field card metadata)', () => {
  let http: HttpTestingController;
  let component: QueryCreate;
  let fixture: ComponentFixture<QueryCreate>;

  beforeEach(() => {
    const s = setup();
    http = s.http;
    component = s.component;
    fixture = s.fixture;
  });

  afterEach(() => {
    http.match(() => true).forEach((r) => {
      if (r.request.url.includes('/explore/models')) r.flush({ total: 0, models: [] });
      else if (r.request.url.includes('/categories/')) r.flush([]);
      else if (r.request.url.includes('/explore/fields/')) r.flush({ fields: {} });
      else r.flush({});
    });
    http.verify();
    TestBed.resetTestingModule();
  });

  function selectModelAndFlushFields() {
    component.selectModel({ name: 'Sale Order', model: 'sale.order' });
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush(RICH_FIELDS_RESPONSE);
    fixture.detectChanges();
  }

  const cards = (): HTMLElement[] =>
    Array.from(fixture.nativeElement.querySelectorAll('.field-card'));

  const cardFor = (key: string): HTMLElement | undefined =>
    cards().find((el) => el.querySelector('.field-key')?.textContent?.trim() === key);

  it('keeps required, readonly, relation and help metadata on availableFields', () => {
    selectModelAndFlushFields();
    const fields = component.availableFields();
    expect(fields.map((f) => f.key)).toEqual(['partner_id', 'amount', 'name']); // id filtered, sorted by string label
    const partner = fields.find((f) => f.key === 'partner_id')!;
    expect(partner.relation).toBe('res.partner');
    expect(partner.required).toBe(true);
    expect(partner.help).toBe('Cliente asociado a la venta');
  });

  it('renders technical key, relation, required badge and help tooltip on each card', () => {
    selectModelAndFlushFields();

    const partner = cardFor('partner_id')!;
    expect(partner).toBeTruthy();
    expect(partner.querySelector('.field-label')!.textContent).toContain('Cliente');
    expect(partner.querySelector('.field-relation')!.textContent).toContain('res.partner');
    expect(partner.querySelector('.field-required-badge')).toBeTruthy();
    expect(partner.getAttribute('title')).toBe('Cliente asociado a la venta');

    const amount = cardFor('amount')!;
    expect(amount.querySelector('.field-required-badge')).toBeNull();
    expect(amount.querySelector('.field-relation')).toBeNull();
    expect(amount.getAttribute('title')).toBeNull();
  });

  it('toggleAllFields selects all available fields and deselects them when clicked again', () => {
    selectModelAndFlushFields();
    expect(component.checkedFields().size).toBe(0);

    component.toggleAllFields();
    expect(component.checkedFields().size).toBe(component.availableFields().length);
    expect(component.allFieldsChecked()).toBe(true);

    component.toggleAllFields();
    expect(component.checkedFields().size).toBe(0);
    expect(component.allFieldsChecked()).toBe(false);
  });

  it('renders selected fields with remove controls and clearly describes an empty selection', () => {
    selectModelAndFlushFields();

    let section = fixture.nativeElement.querySelector('.selected-fields-section') as HTMLElement;
    expect(section).toBeTruthy();
    expect(section.querySelector('.selected-fields-empty')?.textContent).toContain('No hay campos seleccionados');

    component.toggleField('name');
    fixture.detectChanges();
    section = fixture.nativeElement.querySelector('.selected-fields-section') as HTMLElement;
    expect(section.querySelector('.selected-field-label')?.textContent).toContain('Nombre');
    const removeButton = section.querySelector('.selected-field-remove') as HTMLButtonElement;
    expect(removeButton).toBeTruthy();
    expect(removeButton.getAttribute('aria-label')).toContain('Nombre');

    removeButton.click();
    fixture.detectChanges();
    expect(component.checkedFields().has('name')).toBe(false);
    expect(section.querySelector('.selected-fields-empty')?.textContent).toContain('No hay campos seleccionados');
  });

  it('selected fields remain the fields sent when saving after removing one', () => {
    selectModelAndFlushFields();
    component.queryName.set('test_query');
    component.toggleField('name');
    component.toggleField('amount');
    component.toggleField('name');
    component.save();

    const req = http.expectOne('http://localhost:8000/queries/');
    expect(req.request.body.fields).toEqual(['amount']);
    req.flush({ registered: 'test_query' });
  });

  it('toggleAllFields ignores the field search filter and always toggles all model fields', () => {
    selectModelAndFlushFields();
    component.fieldSearch.set('Cliente');
    fixture.detectChanges();
    expect(component.filteredFields().length).toBe(1);

    component.toggleAllFields();
    expect(component.checkedFields().size).toBe(component.availableFields().length);
    expect(component.checkedFields().has('partner_id')).toBe(true);
    expect(component.checkedFields().has('amount')).toBe(true);
    expect(component.checkedFields().has('name')).toBe(true);
  });
});

describe('QueryCreate (selected model context banner)', () => {
  let http: HttpTestingController;
  let component: QueryCreate;
  let fixture: ComponentFixture<QueryCreate>;
  let editState: QueryEditStateService;

  beforeEach(() => {
    const s = setup();
    http = s.http;
    component = s.component;
    fixture = s.fixture;
    editState = TestBed.inject(QueryEditStateService);
  });

  afterEach(() => {
    http.match(() => true).forEach((r) => {
      if (r.request.url.includes('/explore/models')) r.flush({ total: 0, models: [] });
      else if (r.request.url.includes('/categories/')) r.flush([]);
      else if (r.request.url.includes('/explore/fields/')) r.flush({ fields: {} });
      else r.flush({});
    });
    http.verify();
    TestBed.resetTestingModule();
  });

  const banner = (): HTMLElement | null =>
    fixture.nativeElement.querySelector('.model-context-banner');

  it('is hidden until a model is selected', () => {
    expect(component.selectedModel()).toBeNull();
    expect(banner()).toBeNull();
  });

  it('shows the selected model label and technical name, and stays visible across steps', () => {
    component.selectModel({ name: 'Sale Order', model: 'sale.order' });
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush(RICH_FIELDS_RESPONSE);
    fixture.detectChanges();

    expect(banner()).toBeTruthy();
    expect(banner()!.querySelector('.model-context-label')!.textContent).toContain('Sale Order');
    expect(banner()!.querySelector('.model-context-code')!.textContent).toContain('sale.order');

    component.goTo(2);
    fixture.detectChanges();
    expect(banner()).toBeTruthy();

    component.goTo(3);
    fixture.detectChanges();
    expect(banner()).toBeTruthy();
  });

  it('shows the model being edited in edit mode', () => {
    editState.beginEdit(mockQuery);
    component.ngOnInit();
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({ fields: {} });
    fixture.detectChanges();

    expect(banner()).toBeTruthy();
    expect(banner()!.querySelector('.model-context-code')!.textContent).toContain('sale.order');
  });
});
describe('QueryCreate domain codec', () => {
  let http: HttpTestingController;
  let component: QueryCreate;
  beforeEach(() => { const s = setup(); http = s.http; component = s.component; component.availableFields.set([
    { key: 'name', string: 'Name', type: 'char' }, { key: 'amount', string: 'Amount', type: 'integer' }, { key: 'when', string: 'When', type: 'datetime' },
  ]); component.checkedFields.set(new Set(['name', 'amount', 'when'])); });
  afterEach(() => { http.match(() => true).forEach((r) => { if (r.request.url.includes('/explore/models')) r.flush({ total: 0, models: [] }); else if (r.request.url.includes('/categories/')) r.flush([]); else r.flush({}); }); http.verify(); TestBed.resetTestingModule(); });
        it('uses selected fields for filter options and defaults new conditions to the first selected field', () => {
        component.checkedFields.set(new Set(['amount']));
        component.addCondition();
        expect((component.filterTree().children[0] as any).field).toBe('amount');
      });
      it('does not add a condition when no fields are selected', () => {
        component.checkedFields.set(new Set());
        component.addCondition();
        expect(component.filterTree().children).toEqual([]);
      });
      it('warns without changing a stored filter that uses an unselected field', () => {
        component.checkedFields.set(new Set(['name']));
        component.filters.set([{ field: 'amount', operator: '>=', value: 10 }]);
        expect(component.isUnselectedFilterField(component.filters()[0].field)).toBe(true);
        expect(component.filters()[0]).toEqual({ field: 'amount', operator: '>=', value: 10 });
      });
it('exposes every supported operator, including =like and =ilike', () => expect(component.operators.map((op) => op.value)).toEqual(['=', '!=', '=?', '=like', 'like', 'not like', '=ilike', 'ilike', 'not ilike', '>', '>=', '<', '<=', 'in', 'not in', 'child_of', 'parent_of']));
  it('serializes flat AND/OR/NOT prefix domains', () => { component.filters.set([{ field: 'amount', operator: '>=', value: 10 }, { field: 'name', operator: '=like', value: 'ACME', negated: true }]); expect(component.buildDomain()).toEqual(['&', ['amount', '>=', 10], ['!', ['name', '=like', 'ACME']]]); component.domainMode.set('or'); component.negateDomain.set(true); component.domainEdited = true; expect(component.buildDomain()).toEqual(['!', '|', ['amount', '>=', 10], ['!', ['name', '=like', 'ACME']]]); });
  it('serializes and parses a single false clause without warning', () => {
    component.filters.set([{ field: 'name', operator: '=', value: false }]);
    expect(component.buildDomain()).toEqual([['name', '=', false]]);
    const parsed = (component as any).parseDomain(['name', '=', false]);
    expect(component.domainWarning()).toBe('');
    expect(parsed).toEqual([{ field: 'name', operator: '=', value: false }]);
  });
  it('serializes false as a boolean only for relational empty-value comparisons', () => {
        component.availableFields.set([
          { key: 'product_id', string: 'Product', type: 'many2one', relation: 'product.product' },
          { key: 'name', string: 'Name', type: 'char' },
        ]);
        component.filters.set([
          { field: 'product_id', operator: '!=', value: 'false' },
          { field: 'name', operator: '!=', value: 'false' },
        ]);

        expect(component.buildDomain()).toEqual([
          '&',
          ['product_id', '!=', false],
          ['name', '!=', 'false'],
        ]);
        expect(component.valuePlaceholder({ field: 'product_id', operator: '!=', value: '' })).toContain('false');
        expect(component.valuePlaceholder({ field: 'name', operator: '!=', value: '' })).toBe('Valor...');
      });
      it('converts numeric comma lists and scalar hierarchy IDs', () => { component.filters.set([{ field: 'amount', operator: 'in', value: '1, 20, -3' }, { field: 'amount', operator: 'child_of', value: '7' }]); expect(component.buildDomain()).toEqual(['&', ['amount', 'in', [1, 20, -3]], ['amount', 'child_of', 7]]); });
  it('round-trips datetime and negated clauses', () => { const domain = ['&', ['when', '>=', '2024-01-02 03:04:05'], ['!', ['name', 'not ilike', 'x']]]; const filters = (component as any).parseDomain(domain); component.filters.set(filters); component.domainEdited = true; expect(filters).toEqual([{ field: 'when', operator: '>=', value: '2024-01-02T03:04' }, { field: 'name', operator: 'not ilike', value: 'x', negated: true }]); expect(component.buildDomain()).toEqual(['&', ['when', '>=', '2024-01-02 03:04:00'], ['!', ['name', 'not ilike', 'x']]]); });
  it('preserves unsupported domains after a user edit', () => { const domain = ['|', ['name', '=', 'a'], ['&', ['name', '=', 'b'], ['name', '=', 'c']]]; (component as any).loadedDomain = domain; component.filters.set((component as any).parseDomain(domain)); component.domainEdited = true; expect(component.domainWarning()).toContain('no representable'); expect(component.buildDomain()).toEqual(domain); });
  it('creates (A OR B) AND C through nested group operations', () => {
    component.addGroup();
    const nested = component.filterTree().children[0] as any;
    component.setGroupConnector(nested.id, 'or');
    component.addCondition(nested.id);
    const a = (component.filterTree().children[0] as any).children[0] as any;
    component.updateCondition(a.id, { field: 'name', operator: '=', value: 'A' });
    component.addCondition(nested.id);
    const b = (component.filterTree().children[0] as any).children[1] as any;
    component.updateCondition(b.id, { field: 'name', operator: '=', value: 'B' });
    component.addCondition();
    const c = component.filterTree().children[1] as any;
    component.updateCondition(c.id, { field: 'name', operator: '=', value: 'C' });
    expect(component.buildDomain()).toEqual(['&', '|', ['name', '=', 'A'], ['name', '=', 'B'], ['name', '=', 'C']]);
  });
  it('creates A OR (B AND C) through group operations with a flat prefix domain', () => {
    component.addCondition();
    const a = component.filterTree().children[0] as any;
    component.updateCondition(a.id, { field: 'name', operator: '=', value: 'A' });
    component.addGroup();
    const nested = component.filterTree().children[1] as any;
    component.setGroupConnector(component.filterTree().id, 'or');
    component.addCondition(nested.id);
    const b = (component.filterTree().children[1] as any).children[0] as any;
    component.updateCondition(b.id, { field: 'name', operator: '=', value: 'B' });
    component.addCondition(nested.id);
    const c = (component.filterTree().children[1] as any).children[1] as any;
    component.updateCondition(c.id, { field: 'name', operator: '=', value: 'C' });
    expect(component.buildDomain()).toEqual(['|', ['name', '=', 'A'], '&', ['name', '=', 'B'], ['name', '=', 'C']]);
  });
  it('applies NOT to a group', () => {
    component.addGroup();
    const nested = component.filterTree().children[0] as any;
    component.addCondition(nested.id);
    const a = (component.filterTree().children[0] as any).children[0] as any;
    component.updateCondition(a.id, { field: 'name', operator: '=', value: 'A' });
    component.addCondition(nested.id);
    const b = (component.filterTree().children[0] as any).children[1] as any;
    component.updateCondition(b.id, { field: 'name', operator: '=', value: 'B' });
    component.toggleGroupNegated(nested.id);
    expect(component.buildDomain()).toEqual(['!', '&', ['name', '=', 'A'], ['name', '=', 'B']]);
  });
  it('removes a nested group and condition without leaving them in the domain', () => {
    component.addCondition();
    const a = component.filterTree().children[0] as any;
    component.updateCondition(a.id, { field: 'name', operator: '=', value: 'A' });
    component.addGroup();
    const nested = component.filterTree().children[1] as any;
    component.addCondition(nested.id);
    const b = (component.filterTree().children[1] as any).children[0] as any;
    component.updateCondition(b.id, { field: 'name', operator: '=', value: 'B' });
    component.removeCondition(b.id);
    expect(component.buildDomain()).toEqual([['name', '=', 'A']]);
    component.removeNode(nested.id);
    expect(component.buildDomain()).toEqual([['name', '=', 'A']]);
  });
  it('selecting a new model clears stale tree and domain state', () => {
    component.selectModel({ name: 'First', model: 'first.model' });
    http.expectOne((r) => r.url.includes('/explore/fields/first.model')).flush({ fields: { name: { string: 'Name', type: 'char' } } });
    component.toggleField('name');
    component.addCondition();
    const condition = component.filterTree().children[0] as any;
    component.updateCondition(condition.id, { field: 'name', operator: '=', value: 'stale' });
    component.selectModel({ name: 'Second', model: 'second.model' });
    expect(component.filterTree().children).toEqual([]);
    expect(component.buildDomain()).toEqual([]);
    expect(component.domainWarning()).toBe('');
    http.expectOne((r) => r.url.includes('/explore/fields/second.model')).flush({ fields: {} });
  });
  it('reset clears stale tree and domain state', () => {
    component.addCondition();
    const condition = component.filterTree().children[0] as any;
    component.updateCondition(condition.id, { field: 'name', operator: '=', value: 'stale' });
    component.domainMode.set('or');
    component.negateDomain.set(true);
    (component as any).reset();
    expect(component.filterTree().children).toEqual([]);
    expect(component.filters()).toEqual([]);
    expect(component.buildDomain()).toEqual([]);
    expect(component.domainMode()).toBe('and');
    expect(component.negateDomain()).toBe(false);
  });
});
describe('QueryCreate (create mode limit default)', () => {
  let http: HttpTestingController;
  let component: QueryCreate;
  let fixture: ComponentFixture<QueryCreate>;

  beforeEach(() => {
    const s = setup();
    http = s.http;
    component = s.component;
    fixture = s.fixture;
  });

  afterEach(() => {
    http.match(() => true).forEach((r) => {
      if (r.request.url.includes('/explore/models')) r.flush({ total: 0, models: [] });
      else if (r.request.url.includes('/categories/')) r.flush([]);
      else if (r.request.url.includes('/explore/fields/')) r.flush({ fields: {} });
      else r.flush({});
    });
    http.verify();
    TestBed.resetTestingModule();
  });

  it('blank limit field is sent as 0 (all records) when creating a query', () => {
    component.selectModel({ name: 'Sale Order', model: 'sale.order' });
    http.expectOne((r) => r.url.includes('/explore/fields/sale.order')).flush({
      fields: {
        name: { string: 'Nombre', type: 'char' },
      },
    });
    fixture.detectChanges();
    expect(component.limitVal()).toBeNull();
    component.queryName.set('test_query');
    component.toggleField('name');
    component.save();
    const req = http.expectOne('http://localhost:8000/queries/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.limit_val).toBe(0);
    req.flush({ registered: 'test_query' });
  });
});
