import { describe, expect, it, beforeEach, afterEach, vitest } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideAnimations } from '@angular/platform-browser/animations';
import { MessageService } from 'primeng/api';
import { DashboardAdmin } from './dashboard-admin';
import { Dashboard, DashboardDefinition } from '../../services/dashboards';

const BASE = 'http://localhost:8000';

const NATIVE_DEFINITION: DashboardDefinition = {
  model: 'sale.order',
  fields: ['amount_total', 'x_custom'],
  group_by: ['user_id'],
  domain: [],
  aggregations: { amount_total: 'sum', x_custom: 'count' },
};

const EMBED_ROW: Dashboard = {
  menu_key: 'dashboards',
  name: 'Dashboards',
  embed_url: 'https://bi.example/embed',
  definition: null,
  active: true,
};

const NATIVE_DRAFT: Dashboard = {
  menu_key: 'ventas',
  name: 'Ventas',
  embed_url: null,
  definition: NATIVE_DEFINITION,
  active: false,
};

const FIELDS_META = {
  model: 'sale.order',
  fields: {
    amount_total: { string: 'Total', type: 'monetary' },
    user_id: { string: 'Salesperson', type: 'many2one' },
    name: { string: 'Name', type: 'char' },
  },
};

describe('DashboardAdmin', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<DashboardAdmin>;
  let component: DashboardAdmin;

  function createAdmin(rows: Dashboard[]) {
    fixture = TestBed.createComponent(DashboardAdmin);
    component = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne(`${BASE}/dashboards/`).flush(rows);
    fixture.detectChanges();
  }

  function qs<T extends Element>(sel: string, root?: HTMLElement): T | null {
    return ((root ?? fixture.nativeElement) as HTMLElement).querySelector<T>(sel);
  }

  function row(key: string): HTMLElement {
    const el = fixture.nativeElement.querySelector(`tr[data-menu-key="${key}"]`);
    expect(el, `row for ${key}`).not.toBeNull();
    return el as HTMLElement;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DashboardAdmin],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideAnimations(),
        MessageService,
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    document.querySelectorAll('.p-confirmdialog, .p-dialog-mask').forEach((el) => el.remove());
  });

  it('list renders all rows including unpublished ones with type and state badges', () => {
    createAdmin([EMBED_ROW, NATIVE_DRAFT]);

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Dashboards');
    expect(text).toContain('Ventas');
    expect(text).toContain('ventas');
    // type badges
    expect(text).toContain('Embed');
    expect(text).toContain('Native');
    // state badges: published + draft both visible (admin sees unpublished rows)
    expect(row('dashboards').textContent).toContain('Publicado');
    expect(row('ventas').textContent).toContain('Borrador');
  });

  it('publish toggle PATCHes active: true and emits dashboardsChanged', () => {
    createAdmin([EMBED_ROW, NATIVE_DRAFT]);
    const spy = vitest.fn();
    component.dashboardsChanged.subscribe(spy);

    const toggle = qs<HTMLButtonElement>('.btn-toggle-active', row('ventas'));
    expect(toggle).not.toBeNull();
    toggle!.click();

    const req = http.expectOne(`${BASE}/dashboards/ventas`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ active: true });
    req.flush({ ...NATIVE_DRAFT, active: true });

    // list refresh after the mutation
    http.expectOne(`${BASE}/dashboards/`).flush([EMBED_ROW, { ...NATIVE_DRAFT, active: true }]);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('delete asks for confirmation before issuing DELETE', () => {
    createAdmin([EMBED_ROW]);
    const spy = vitest.fn();
    component.dashboardsChanged.subscribe(spy);

    qs<HTMLButtonElement>('.btn-delete', row('dashboards'))!.click();
    fixture.detectChanges();

    // confirmation dialog is shown; no DELETE has been issued yet
    http.expectNone((r) => r.method === 'DELETE');
    const accept = document.querySelector<HTMLButtonElement>('.p-confirmdialog-accept-button');
    expect(accept, 'ConfirmDialog accept button').not.toBeNull();
    accept!.click();

    const req = http.expectOne(`${BASE}/dashboards/dashboards`);
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: 'No Content' });

    http.expectOne(`${BASE}/dashboards/`).flush([]);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('edit load marks stored fields missing from fresh metadata as stale', () => {
    createAdmin([NATIVE_DRAFT]);

    qs<HTMLButtonElement>('.btn-edit', row('ventas'))!.click();
    fixture.detectChanges();

    // model picker + fresh field metadata (x_custom is gone from Odoo)
    http.expectOne(`${BASE}/explore/models`).flush({ total: 0, models: [] });
    http.expectOne(`${BASE}/explore/fields/sale.order`).flush(FIELDS_META);
    fixture.detectChanges();

    const warning = fixture.nativeElement.querySelector('.stale-warning');
    expect(warning, 'stale warning').not.toBeNull();
    expect(warning.textContent).toContain('x_custom');
    expect(warning.textContent).not.toContain('amount_total');
  });

  it('aggregation dropdown is filtered by DD2 applicability per field type', () => {
    createAdmin([]);

    qs<HTMLButtonElement>('.btn-new')!.click();
    fixture.detectChanges();
    http.expectOne(`${BASE}/explore/models`).flush({ total: 0, models: [] });

    component.formType.set('native');
    component.onModelChange('sale.order');
    http.expectOne(`${BASE}/explore/fields/sale.order`).flush(FIELDS_META);
    component.onFieldsChange(['amount_total', 'name']);

    // monetary field offers the full DD2 set; char field is count-only
    expect(component.aggregationOptionsFor('amount_total').map((o) => o.value)).toEqual(['sum', 'avg', 'count']);
    expect(component.aggregationOptionsFor('name').map((o) => o.value)).toEqual(['count']);
    // defaults: numeric defaults to sum, non-numeric to count
    expect(component.aggregations()).toEqual({ amount_total: 'sum', name: 'count' });
  });

  it('save surfaces the backend 422 message inline', () => {
    createAdmin([]);

    qs<HTMLButtonElement>('.btn-new')!.click();
    fixture.detectChanges();
    http.expectOne(`${BASE}/explore/models`).flush({ total: 0, models: [] });

    component.formType.set('native');
    component.formName.set('Nuevo');
    component.formMenuKey.set('nuevo');
    component.onModelChange('sale.order');
    http.expectOne(`${BASE}/explore/fields/sale.order`).flush(FIELDS_META);
    component.onFieldsChange(['amount_total']);
    fixture.detectChanges();

    qs<HTMLButtonElement>('.btn-save')!.click();
    const req = http.expectOne((r) => r.method === 'POST' && r.url === `${BASE}/dashboards/`);
    expect(req.request.body.definition).toEqual({
      model: 'sale.order',
      fields: ['amount_total'],
      group_by: [],
      domain: [],
      aggregations: { amount_total: 'sum' },
    });
    req.flush(
      { detail: { message: "Field 'amount_total' cannot use 'sum'", model: 'sale.order', field: 'amount_total' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    const error = fixture.nativeElement.querySelector('.form-error');
    expect(error, 'inline form error').not.toBeNull();
    expect(error.textContent).toContain("Field 'amount_total' cannot use 'sum'");
  });

  it('preview POSTs the built definition and renders the shared data table', () => {
    createAdmin([]);

    qs<HTMLButtonElement>('.btn-new')!.click();
    fixture.detectChanges();
    http.expectOne(`${BASE}/explore/models`).flush({ total: 0, models: [] });

    component.formType.set('native');
    component.formName.set('Preview test');
    component.formMenuKey.set('preview-test');
    component.onModelChange('sale.order');
    http.expectOne(`${BASE}/explore/fields/sale.order`).flush(FIELDS_META);
    component.onFieldsChange(['amount_total']);
    component.groupBy.set(['user_id']);
    fixture.detectChanges();

    qs<HTMLButtonElement>('.btn-preview')!.click();
    const req = http.expectOne(`${BASE}/dashboards/preview`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      model: 'sale.order',
      fields: ['amount_total'],
      group_by: ['user_id'],
      domain: [],
      aggregations: { amount_total: 'sum' },
    });
    req.flush({
      menu_key: 'preview-test',
      name: 'Preview test',
      model: 'sale.order',
      columns: [
        { key: 'user_id', label: 'Salesperson', kind: 'group' },
        { key: 'amount_total', label: 'Total (sum)', kind: 'aggregate', function: 'sum' },
      ],
      rows: [{ user_id: [7, 'J. Perez'], amount_total: 152340.5, __count: 42 }],
    });
    fixture.detectChanges();

    const preview = fixture.nativeElement.querySelector('.preview-panel');
    expect(preview, 'preview panel').not.toBeNull();
    expect(preview.textContent).toContain('Salesperson');
    expect(preview.textContent).toContain('Total (sum)');
    expect(preview.textContent).toContain('J. Perez');
    expect(preview.textContent).toContain('Count');
  });
});
