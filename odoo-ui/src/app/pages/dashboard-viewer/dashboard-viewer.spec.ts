import { describe, expect, it, beforeEach, afterEach, vitest } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideAnimations } from '@angular/platform-browser/animations';
import { DashboardViewer } from './dashboard-viewer';
import { DashboardData, DashboardDefinition } from '../../services/dashboards';

const DEFINITION: DashboardDefinition = {
  model: 'sale.order',
  fields: ['amount_total'],
  group_by: ['user_id'],
  domain: [],
  aggregations: { amount_total: 'sum' },
};

const NATIVE_DATA: DashboardData = {
  menu_key: 'ventas-por-vendedor',
  name: 'Ventas por vendedor',
  model: 'sale.order',
  columns: [
    { key: 'user_id', label: 'Salesperson', kind: 'group' },
    { key: 'amount_total', label: 'Total (sum)', kind: 'aggregate', function: 'sum' },
  ],
  rows: [
    { user_id: [7, 'J. Perez'], amount_total: 152340.5, __count: 42 },
    { user_id: [9, 'A. Gomez'], amount_total: 8010, __count: 5 },
  ],
};

describe('DashboardViewer', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DashboardViewer],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideAnimations(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function createViewer(menuKey: string) {
    const fixture = TestBed.createComponent(DashboardViewer);
    fixture.componentRef.setInput('menuKey', menuKey);
    fixture.detectChanges();
    return fixture;
  }

  it('embed dashboard renders the sanitized iframe (legacy path unchanged)', () => {
    const fixture = createViewer('dashboards');
    const req = http.expectOne('http://localhost:8000/dashboards/dashboards');
    expect(req.request.method).toBe('GET');
    req.flush({ name: 'Dashboards', embed_url: 'https://bi.example/embed', definition: null });
    fixture.detectChanges();

    const iframe = fixture.nativeElement.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(String(iframe.src)).toContain('https://bi.example/embed');
    expect(fixture.nativeElement.textContent).toContain('Dashboards');
  });

  it('native dashboard fetches /data and renders the grouped table with count column', () => {
    const fixture = createViewer('ventas-por-vendedor');
    http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor').flush({
      name: 'Ventas por vendedor',
      embed_url: null,
      definition: DEFINITION,
    });
    const dataReq = http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor/data');
    expect(dataReq.request.method).toBe('GET');
    dataReq.flush(NATIVE_DATA);
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('iframe')).toBeNull();
    const text = el.textContent ?? '';
    expect(text).toContain('Salesperson');
    expect(text).toContain('Total (sum)');
    expect(text).toContain('Count');
    // relational [id, label] pairs render the label, not the id
    expect(text).toContain('J. Perez');
    expect(text).toContain('A. Gomez');
    expect(text).toContain('152340.5');
    expect(text).toContain('42');
  });

  it('404 shows the unavailable state and emits (unavailable) when the user returns', () => {
    const fixture = createViewer('dashboards');
    http.expectOne('http://localhost:8000/dashboards/dashboards').flush(null, {
      status: 404,
      statusText: 'Not Found',
    });
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Este dashboard ya no está disponible');

    const spy = vitest.fn();
    fixture.componentInstance.unavailable.subscribe(spy);
    const button = el.querySelector<HTMLButtonElement>('.unavailable-panel button');
    expect(button).not.toBeNull();
    button!.click();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('422 stale_definition on data shows the backend message in the unavailable panel', () => {
    const fixture = createViewer('ventas-por-vendedor');
    http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor').flush({
      name: 'Ventas por vendedor',
      embed_url: null,
      definition: DEFINITION,
    });
    http.expectOne('http://localhost:8000/dashboards/ventas-por-vendedor/data').flush(
      { detail: { code: 'stale_definition', message: "Field 'x_custom' no longer exists on model 'sale.order'", model: 'sale.order', field: 'x_custom' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain("Field 'x_custom' no longer exists on model 'sale.order'");
    expect(el.querySelector('iframe')).toBeNull();
  });

  it('switching menuKey refetches and renders the newly selected dashboard', () => {
    const fixture = createViewer('dashboards');
    http.expectOne('http://localhost:8000/dashboards/dashboards').flush({
      name: 'Dashboards',
      embed_url: 'https://bi.example/embed',
      definition: null,
    });
    fixture.detectChanges();
    expect(String(fixture.nativeElement.querySelector('iframe').src)).toContain(
      'https://bi.example/embed',
    );

    fixture.componentRef.setInput('menuKey', 'powerbi');
    fixture.detectChanges();

    http
      .expectOne('http://localhost:8000/dashboards/powerbi')
      .flush({ name: 'Power BI', embed_url: 'https://pbi.example/embed', definition: null });
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(String(el.querySelector('iframe')!.src)).toContain('https://pbi.example/embed');
    expect(el.textContent).toContain('Power BI');
  });

  it('unavailable panel has no management controls (view-only invariant)', () => {
    const fixture = createViewer('dashboards');
    http.expectOne('http://localhost:8000/dashboards/dashboards').flush(null, {
      status: 404,
      statusText: 'Not Found',
    });
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).not.toContain('Editar');
    expect(el.textContent).not.toContain('Publicar');
    expect(el.textContent).not.toContain('Eliminar');
  });
});
