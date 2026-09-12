import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MenuService } from './menu';
import { environment } from '../../environments/environment';

describe('MenuService', () => {
  let service: MenuService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(MenuService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads the authenticated context without inventing a selection', () => {
    service.getContext().subscribe(context => expect(context.menu).toEqual([]));
    const request = http.expectOne(`${environment.apiUrl}/auth/context`);
    expect(request.request.method).toBe('GET');
    expect(request.request.withCredentials).toBe(true);
    request.flush({ systems: [], selected_system_id: null, selected_module_id: null, menu: [] });
  });

  it('passes opaque system and module IDs as encoded query parameters', () => {
    service.getContext('system/2', 'sales & orders').subscribe();
    const request = http.expectOne(req => req.url === `${environment.apiUrl}/auth/context`);
    expect(request.request.params.get('system_id')).toBe('system/2');
    expect(request.request.params.get('module_id')).toBe('sales & orders');
    request.flush({ systems: [], selected_system_id: 'system/2', selected_module_id: 'sales & orders', menu: [] });
  });

  it('propagates denied context rather than falling back to local permissions', () => {
    let status = 0;
    service.getContext('2', '2-ventas').subscribe({ error: error => status = error.status });
    http.expectOne(req => req.url === `${environment.apiUrl}/auth/context`)
      .flush({}, { status: 403, statusText: 'Forbidden' });
    expect(status).toBe(403);
  });
});
