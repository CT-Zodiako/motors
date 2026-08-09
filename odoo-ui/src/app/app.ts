import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { QueryList } from './pages/query-list/query-list';
import { QueryCreate } from './pages/query-create/query-create';
import { QueryRunner } from './pages/query-runner/query-runner';
import { ScheduleManager } from './pages/schedule-manager/schedule-manager';
import { FileUpload } from './pages/file-upload/file-upload';
import { UserAdminComponent } from './pages/user-admin/user-admin';
import { LoginComponent } from './pages/login/login';
import { ChangePasswordComponent } from './pages/change-password/change-password';
import { WelcomeComponent } from './pages/welcome/welcome';
import { DashboardViewer } from './pages/dashboard-viewer/dashboard-viewer';
import { DashboardAdmin } from './pages/dashboard-admin/dashboard-admin';
import { ToastModule } from 'primeng/toast';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { AuthService } from './services/auth';
import { DashboardsService } from './services/dashboards';
import { APP_VERSION } from './version';

type StaticTab = 'home' | 'list' | 'create' | 'runner' | 'schedules' | 'upload'
  | 'admin' | 'admin-dashboards' | 'change-password';
type DashboardTab = `dashboard:${string}`;
type Tab = StaticTab | DashboardTab;

interface MenuNode {
  id?: Tab;
  label: string;
  icon?: string;
  permission?: string;
  children?: MenuNode[];
}

@Component({
  selector: 'app-root',
  imports: [QueryList, QueryCreate, QueryRunner, ScheduleManager, FileUpload, UserAdminComponent, LoginComponent, ChangePasswordComponent, WelcomeComponent, DashboardViewer, DashboardAdmin, ToastModule, ButtonModule, TooltipModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App implements OnInit {
  private auth = inject(AuthService);
  private msg = inject(MessageService);
  private dashboards = inject(DashboardsService);

  activeTab = signal<Tab>('home');
  authenticated = this.auth.isAuthenticated;
  user = this.auth.user;
  sidebarCollapsed = signal(false);
  appVersion = APP_VERSION;

  // Static menu definition (design §5.2): dynamic dashboard entries are merged
  // from the published dashboard list; Visualizaciones has no hardcoded children.
  private staticMenu: MenuNode[] = [
    {
      label: 'Consultar',
      children: [
        { id: 'list', label: 'Queries', icon: 'pi-database', permission: 'menu.consultar.queries' },
        { id: 'runner', label: 'Ejecutar', icon: 'pi-play-circle', permission: 'menu.consultar.ejecutar' },
        { id: 'schedules', label: 'Programar', icon: 'pi-calendar-clock', permission: 'menu.consultar.programar' },
      ]
    },
    {
      label: 'Cargar datos',
      children: [
        { id: 'create', label: 'Nuevo Query', icon: 'pi-plus-circle', permission: 'menu.cargar.create' },
        { id: 'upload', label: 'Cargar archivo', icon: 'pi-upload', permission: 'menu.cargar.upload' },
      ]
    },
    {
      label: 'Administración',
      children: [
        { id: 'admin', label: 'Usuarios', icon: 'pi-users', permission: 'menu.admin.usuarios' },
        { id: 'admin-dashboards', label: 'Dashboards', icon: 'pi-chart-bar', permission: 'menu.admin.dashboards' },
      ]
    },
  ];

  // Dynamic dashboard entries derived from GET /dashboards/ (spec §6).
  dashboardItems = signal<MenuNode[]>([]);

  // Hierarchical menu definition. Supports 2 levels today and 3+ levels tomorrow
  // via the recursive filterMenu / render helpers. The Visualizaciones group only
  // exists while there is at least one published dashboard (spec §6).
  menuTree = computed<MenuNode[]>(() => {
    const items = this.dashboardItems();
    return items.length > 0
      ? [...this.staticMenu, { label: 'Visualizaciones', children: items }]
      : [...this.staticMenu];
  });

  // Footer items rendered outside the recursive menu tree.
  accountMenu: MenuNode[] = [
    { id: 'change-password', label: 'Cambiar contraseña', icon: 'pi-lock', permission: 'menu.cuenta.change_password' },
  ];

  visibleMenu = computed(() => this.filterMenu(this.menuTree()));
  visibleAccountMenu = computed(() => this.filterMenu(this.accountMenu));
  hasAnyMenu = computed(() => this.visibleMenu().length > 0 || this.visibleAccountMenu().length > 0);

  // Content-branch helpers (design §5.2): `dashboard:` is a literal prefix and
  // menu_key cannot contain ':' per the backend MENU_KEY_RE, so the split is
  // unambiguous.
  isDashboardTab = (tab: Tab): boolean => tab.startsWith('dashboard:');
  dashboardMenuKey = computed<string | null>(() => {
    const tab = this.activeTab();
    return this.isDashboardTab(tab) ? tab.slice('dashboard:'.length) : null;
  });

  ngOnInit() {
    this.auth.fetchMe().subscribe({
      error: () => {},
      complete: () => this.refreshDashboards(),
    });
  }

  /** Reload the dynamic dashboard menu entries. Called after fetchMe() and by
   *  the admin screen after any dashboard mutation (spec §6). */
  refreshDashboards() {
    this.dashboards.list().subscribe({
      next: (rows) =>
        this.dashboardItems.set(rows.map((d) => ({
          id: `dashboard:${d.menu_key}` as Tab,
          label: d.name,
          icon: 'pi-chart-bar',
          permission: 'menu.visualizaciones.dashboards',
        }))),
      error: () => this.dashboardItems.set([]),
    });
  }

  /**
   * Recursively filter a menu tree by user permissions.
   * - Leaves without a permission are always visible.
   * - Leaves with a permission are visible only if the user has it.
   * - Branches are visible if at least one descendant is visible.
   */
  filterMenu(items: MenuNode[]): MenuNode[] {
    return items
      .map((item) => {
        if (item.children && item.children.length > 0) {
          const visibleChildren = this.filterMenu(item.children);
          if (visibleChildren.length > 0) {
            return { ...item, children: visibleChildren };
          }
          return null;
        }
        if (!item.permission || this.auth.hasPermission(item.permission)) {
          return item;
        }
        return null;
      })
      .filter((item): item is MenuNode => item !== null);
  }

  setTab(tab: Tab) {
    this.activeTab.set(tab);
  }

  changePassword() {
    this.activeTab.set('change-password');
  }

  toggleSidebar() {
    this.sidebarCollapsed.update((v) => !v);
  }

  logout() {
    this.auth.logout().subscribe({
      next: () => {
        this.activeTab.set('home');
        this.sidebarCollapsed.set(false);
        this.msg.add({ severity: 'success', summary: 'Listo', detail: 'Sesión cerrada' });
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo cerrar la sesión' });
      }
    });
  }
}

