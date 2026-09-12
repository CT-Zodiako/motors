import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { MessageService } from 'primeng/api';
import { App } from './app';
import { AuthService } from './services/auth';
import { NavigationContext } from './services/menu';

const systems: NavigationContext['systems'] = ['1', '2'].map(id => ({
  id, name: id, active: true, sort_order: 0,
  modules: ['a', 'b'].map(suffix => ({
    id: `${id}-${suffix}`, system_id: id, name: suffix, active: true, sort_order: 0, menu: [],
  })),
}));

function context(system: string | null = '1', module: string | null = '1-a'): NavigationContext {
  return { systems, selected_system_id: system, selected_module_id: module, menu: [] };
}

describe('App authoritative menu context', () => {
  const user = signal<object | null>(null);
  let http: HttpTestingController;

  beforeEach(() => {
    user.set({ id: '1' });
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting(), MessageService,
        { provide: AuthService, useValue: {
          user, isAuthenticated: signal(true), authChecked: signal(true), fetchMe: () => of(user()),
        } },
      ],
    });
    TestBed.overrideComponent(App, { set: { template: '', imports: [] } });
    http = TestBed.inject(HttpTestingController);
  });

  function start() {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    return fixture;
  }

  it('loads once and accepts the server selection rather than the first available IDs', () => {
    const fixture = start();
    const request = http.expectOne(req => req.url.endsWith('/auth/context'));
    expect(request.request.params.keys()).toEqual([]);
    request.flush(context('2', '2-b'));
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedSystem()).toBe('2');
    expect(fixture.componentInstance.selectedModule()).toBe('2-b');
    http.verify();
  });

  it('selects the first available module locally and makes one request per selection', () => {
    const fixture = start();
    http.expectOne(req => req.url.endsWith('/auth/context')).flush(context());
    fixture.detectChanges();
    const app = fixture.componentInstance;
    app.selectSystem('2');
    expect(app.context()).toBeNull();
    fixture.detectChanges();
    const request = http.expectOne(req => req.url.endsWith('/auth/context'));
    expect(request.request.params.get('system_id')).toBe('2');
    expect(request.request.params.get('module_id')).toBe('2-a');
    request.flush(context('2', '2-b'));
    fixture.detectChanges();
    expect(app.selectedModule()).toBe('2-b');
    app.selectModule('2-a');
    fixture.detectChanges();
    http.expectOne(req => req.params.get('module_id') === '2-a').flush(context('2', '2-a'));
    fixture.detectChanges();
    http.verify();
  });

  it('normalizes null server selection locally without retrying', () => {
    const fixture = start();
    http.expectOne(req => req.url.endsWith('/auth/context')).flush(context(null, null));
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedSystem()).toBe('1');
    expect(fixture.componentInstance.selectedModule()).toBe('1-a');
    expect(fixture.componentInstance.context()?.selected_system_id).toBe('1');
    expect(fixture.componentInstance.context()?.selected_module_id).toBe('1-a');
    http.verify();
  });

  it('fails closed on denial and reloads context for a different authenticated user', () => {
    const fixture = start();
    http.expectOne(req => req.url.endsWith('/auth/context')).flush(context());
    fixture.detectChanges();
    user.set({ id: '2' });
    fixture.detectChanges();
    const app = fixture.componentInstance;
    expect(app.context()).toBeNull();
    http.expectOne(req => req.url.endsWith('/auth/context'))
      .flush({}, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();
    expect(app.contextError()).toBe(true);
    expect(app.visibleMenu()).toEqual([]);
    app.setTab('dashboard:ventas');
    expect(app.activeTab()).toBe('home');
    http.verify();
  });

  it.each(['1', '2'])('opens only the fixed workflow in system %s and clears it on module changes', (system) => {
    const fixture = start();
    const option = {
      id: 'process', module_id: `${system}-a`, name: 'Procesos Bizagi', menu_key: 'procesos.bizagi',
      permission_id: 'menu.operaciones.procesos', active: true, sort_order: 0,
      workflow_url: '/WorkFlow/index.html',
    };
    http.expectOne(req => req.url.endsWith('/auth/context')).flush({ ...context(system, `${system}-a`), menu: [option] });
    fixture.detectChanges();
    const app = fixture.componentInstance;
    app.setTab('workflow:process');
    expect(app.workflowOption()?.name).toBe('Procesos Bizagi');
    expect(app.demoOption()).toBeUndefined();
    const frame = document.createElement('iframe');
    frame.src = '/WorkFlow/index.html#diagram';
    const navigate = vi.spyOn(frame, 'src', 'set');
    for (let attempt = 0; attempt < 2; attempt++) {
      app.backToProcesses(frame);
      expect(navigate).toHaveBeenNthCalledWith(attempt + 1, '/WorkFlow/index.html');
      expect(app.activeTab()).toBe('workflow:process');
      expect(app.selectedSystem()).toBe(system);
      expect(app.selectedModule()).toBe(`${system}-a`);
    }
    navigate.mockRestore();
    app.context.set({ ...context(system, `${system}-a`), menu: [{ ...option, workflow_url: 'https://example.com' }] });
    expect(app.workflowOption()).toBeUndefined();
    app.setTab('home');
    app.setTab('workflow:process');
    expect(app.activeTab()).toBe('home');
    app.selectModule(`${system}-b`);
    expect(app.workflowOption()).toBeUndefined();
    http.verify();
  });

  it('keeps dashboard navigation deactivated even when returned by the backend', () => {
    const fixture = start();
    http.expectOne(req => req.url.endsWith('/auth/context')).flush({ ...context(), menu: [{
      id: 'dashboard', module_id: '1-a', name: 'Dashboards', menu_key: 'admin.dashboards',
      permission_id: 'permission', active: true, sort_order: 0,
    }] });
    fixture.detectChanges();
    const app = fixture.componentInstance;
    expect(app.visibleMenu()).toEqual([]);
    app.setTab('admin-dashboards');
    expect(app.activeTab()).toBe('home');
    http.verify();
  });
});
