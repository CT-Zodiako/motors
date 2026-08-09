import { describe, expect, it, beforeEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { MessageService } from 'primeng/api';
import { App } from './app';
import { AuthService, User } from './services/auth';
import { DashboardsService, Dashboard } from './services/dashboards';

class FakeAuthService {
  private userSignal = signal<User | null>(null);
  private permissionsSignal = signal<string[]>([]);
  user = computed(() => this.userSignal());
  isAuthenticated = computed(() => this.userSignal() !== null);
  hasPermission(permission: string): boolean {
    return this.permissionsSignal().includes(permission);
  }
  fetchMe() {
    return of(this.userSignal());
  }
  logout() {
    return of({ ok: true });
  }
  grant(user: User, permissions: string[]) {
    this.userSignal.set(user);
    this.permissionsSignal.set(permissions);
  }
}

class FakeDashboardsService {
  rows = signal<Dashboard[]>([]);
  list() {
    return of(this.rows());
  }
}

const VIEW_PERMISSION = 'menu.visualizaciones.dashboards';
const STATIC_PERMISSIONS = [
  'menu.consultar.queries',
  'menu.consultar.ejecutar',
  'menu.consultar.programar',
  'menu.cargar.create',
  'menu.cargar.upload',
  'menu.admin.usuarios',
  'menu.admin.dashboards',
  'menu.cuenta.change_password',
];

function dashboard(menuKey: string, name: string): Dashboard {
  return { menu_key: menuKey, name, embed_url: 'https://bi.example/x', definition: null, active: true };
}

describe('App dynamic dashboard menu', () => {
  let auth: FakeAuthService;
  let dashboards: FakeDashboardsService;

  beforeEach(() => {
    auth = new FakeAuthService();
    dashboards = new FakeDashboardsService();
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideAnimations(),
        MessageService,
        { provide: AuthService, useValue: auth },
        { provide: DashboardsService, useValue: dashboards },
      ],
    });
  });

  function createApp(): App {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  function visualizacionesGroup(app: App) {
    return app.visibleMenu().find((g) => g.label === 'Visualizaciones');
  }

  it('published dashboards appear under Visualizaciones as dashboard:<menu_key> nodes', () => {
    dashboards.rows.set([dashboard('dashboards', 'Dashboards'), dashboard('dashboards-ventas', 'Ventas')]);
    auth.grant({ id: '1', email: 'u@x.com', role: 'user' }, [VIEW_PERMISSION, ...STATIC_PERMISSIONS]);
    const app = createApp();

    const group = visualizacionesGroup(app);
    expect(group).toBeDefined();
    expect(group!.children!.map((c) => c.id)).toEqual(['dashboard:dashboards', 'dashboard:dashboards-ventas']);
    expect(group!.children!.map((c) => c.label)).toEqual(['Dashboards', 'Ventas']);
  });

  it('empty dashboard list renders no Visualizaciones group', () => {
    dashboards.rows.set([]);
    auth.grant({ id: '1', email: 'u@x.com', role: 'user' }, [VIEW_PERMISSION, ...STATIC_PERMISSIONS]);
    const app = createApp();

    expect(visualizacionesGroup(app)).toBeUndefined();
  });

  it('users without the view permission see no dashboard entries', () => {
    dashboards.rows.set([dashboard('dashboards', 'Dashboards')]);
    auth.grant({ id: '1', email: 'u@x.com', role: 'user' }, STATIC_PERMISSIONS);
    const app = createApp();

    expect(visualizacionesGroup(app)).toBeUndefined();
  });

  it('static tabs and groups remain unchanged', () => {
    dashboards.rows.set([dashboard('dashboards', 'Dashboards')]);
    auth.grant({ id: '1', email: 'u@x.com', role: 'user' }, [VIEW_PERMISSION, ...STATIC_PERMISSIONS]);
    const app = createApp();

    const labels = app.visibleMenu().map((g) => g.label);
    expect(labels).toEqual(['Consultar', 'Cargar datos', 'Administración', 'Visualizaciones']);

    const admin = app.visibleMenu().find((g) => g.label === 'Administración');
    expect(admin!.children!.map((c) => c.id)).toEqual(['admin', 'admin-dashboards']);
  });

  it('isDashboardTab identifies dynamic dashboard tabs only', () => {
    const app = createApp();
    expect(app.isDashboardTab('dashboard:dashboards')).toBe(true);
    expect(app.isDashboardTab('home')).toBe(false);
    expect(app.isDashboardTab('admin-dashboards')).toBe(false);
  });

  it('dashboardMenuKey() strips the dashboard: prefix and is null on static tabs', () => {
    const app = createApp();
    expect(app.dashboardMenuKey()).toBeNull();
    app.setTab('dashboard:ventas-por-vendedor');
    expect(app.dashboardMenuKey()).toBe('ventas-por-vendedor');
    app.setTab('home');
    expect(app.dashboardMenuKey()).toBeNull();
  });

  it('refreshDashboards() reloads menu entries (publish adds, unpublish/delete removes)', () => {
    dashboards.rows.set([dashboard('dashboards', 'Dashboards')]);
    auth.grant({ id: '1', email: 'u@x.com', role: 'user' }, [VIEW_PERMISSION, ...STATIC_PERMISSIONS]);
    const app = createApp();
    expect(visualizacionesGroup(app)!.children!.map((c) => c.id)).toEqual(['dashboard:dashboards']);

    dashboards.rows.set([]);
    app.refreshDashboards();
    expect(visualizacionesGroup(app)).toBeUndefined();

    dashboards.rows.set([dashboard('nuevo', 'Nuevo')]);
    app.refreshDashboards();
    expect(visualizacionesGroup(app)!.children!.map((c) => c.id)).toEqual(['dashboard:nuevo']);
  });
});
