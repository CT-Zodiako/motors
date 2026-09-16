import { Component, computed, effect, inject, OnInit, signal, untracked } from '@angular/core';
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
import { MenuService, NavigationContext, NavigationSystem } from './services/menu';

type StaticTab = 'home' | 'list' | 'create' | 'runner' | 'schedules' | 'upload'
  | 'admin' | 'admin-dashboards' | 'change-password';
type DashboardTab = `dashboard:${string}`;
type Tab = StaticTab | DashboardTab | `demo:${string}` | `workflow:${string}`;

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
  backToProcesses(frame: HTMLIFrameElement) {
    // Assign even when unchanged: Bizagi may have navigated inside the iframe.
    frame.src = '/WorkFlow/index.html';
  }
  authenticated = this.auth.isAuthenticated;
  authChecked = this.auth.authChecked;
  user = this.auth.user;
  sidebarCollapsed = signal(false);
  appVersion = APP_VERSION;
  private menuService = inject(MenuService);
  context = signal<NavigationContext | null>(null);
  selectedSystem = signal('');
  selectedModule = signal('');
  contextLoading = signal(false);
  contextError = signal(false);
  systems = signal<NavigationSystem[]>([]);
  modules = computed(() => this.systems().find(s => s.id === this.selectedSystem())?.modules ?? []);
  demoOption = computed(() => this.context()?.menu.find(o => `demo:${o.id}` === this.activeTab()));
  workflowOption = computed(() => this.context()?.menu.find(o =>
    o.active && o.module_id === this.selectedModule() && ['1', '2'].includes(this.selectedSystem())
    && o.workflow_url === '/WorkFlow/index.html'
    && `workflow:${o.id}` === this.activeTab()));

  constructor() {
    let contextUser: ReturnType<typeof this.user> = null;
    effect((onCleanup) => {
      const user = this.user();
      const system = this.selectedSystem();
      const module = this.selectedModule();
      // Applying the server's selection is not a new navigation request.
      const current = untracked(this.context);
      if (user && user === contextUser && current
        && (current.selected_system_id ?? '') === system
        && (current.selected_module_id ?? '') === module) return;
      untracked(() => {
        this.activeTab.set('home');
        this.context.set(null);
        this.contextError.set(false);
        this.contextLoading.set(!!user);
      });
      if (!user) {
        untracked(() => {
          this.systems.set([]);
          this.selectedSystem.set('');
          this.selectedModule.set('');
        });
        return;
      }
      const request = this.menuService.getContext(system || undefined, module || undefined).subscribe({
        next: context => {
          // An unscoped context includes all available systems, but the API may
          // leave the selection null. Normalize the first available system and
          // module locally so the module selector is populated without issuing
          // a second request.
          const selected = context.systems.find(item => item.id === system) ?? context.systems[0];
          const selectedModule = selected?.modules.find(item => item.id === module) ?? selected?.modules[0];
          const normalized = {
            ...context,
            selected_system_id: context.selected_system_id ?? selected?.id ?? null,
            selected_module_id: context.selected_module_id ?? selectedModule?.id ?? null,
          };
          this.context.set(normalized);
          this.systems.set(context.systems);
          contextUser = user;
          this.selectedSystem.set(normalized.selected_system_id ?? '');
          this.selectedModule.set(normalized.selected_module_id ?? '');
          this.contextLoading.set(false);
        },
        error: () => {
          this.contextError.set(true);
          this.contextLoading.set(false);
        },
      });
      onCleanup(() => request.unsubscribe());
    });
  }

  selectSystem(id: string) {
    this.context.set(null);
    this.activeTab.set('home');
    const system = this.systems().find(system => system.id === id && system.active);
    this.selectedModule.set(system?.modules.find(module => module.active)?.id ?? '');
    this.selectedSystem.set(id);
  }

  selectModule(id: string) {
    this.context.set(null);
    this.activeTab.set('home');
    this.selectedModule.set(id);
  }

  private contextItems(): MenuNode[] {
    const context = this.context();
    if (!context || context.selected_system_id !== this.selectedSystem()
      || context.selected_module_id !== this.selectedModule()) return [];
    const known = [...this.staticMenu.flatMap(group => group.children ?? []), ...this.accountMenu];
    return context.menu.filter(option => option.active && option.module_id === this.selectedModule())
      .flatMap(option => {
        if (['1', '2'].includes(this.selectedSystem()) && option.workflow_url === '/WorkFlow/index.html') {
          return [{ id: `workflow:${option.id}` as Tab, label: option.name, icon: 'pi-sitemap' }];
        }
        if (this.selectedSystem() === '2') {
          return [{ id: `demo:${option.id}` as Tab, label: option.name, icon: 'pi-info-circle' }];
        }
        if (this.selectedSystem() !== '1') return [];
        const target = known.find(item => item.permission === `menu.${option.menu_key}`);
        return target ? [{ ...target, label: option.name }] : [];
      });
  }

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
        // Dashboards feature temporarily deactivated per user request (2026-09-10).
        // Kept commented out (not deleted) so it can be re-enabled in the future.
        // { id: 'admin-dashboards', label: 'Dashboards', icon: 'pi-chart-bar', permission: 'menu.admin.dashboards' },
      ]
    },
  ];

  // Dynamic dashboard entries derived from GET /dashboards/ (spec §6).
  dashboardItems = signal<MenuNode[]>([]);

  // Hierarchical menu definition. Supports 2 levels today and 3+ levels tomorrow
  // via the recursive filterMenu / render helpers. The Visualizaciones group only
  // exists while there is at least one published dashboard (spec §6).
  menuTree = computed<MenuNode[]>(() => {
    // Dashboards feature temporarily deactivated per user request (2026-09-10):
    // the "Visualizaciones" menu is disabled, so menuTree always returns just
    // the static menu, regardless of dashboardItems(). Kept commented out
    // (not deleted) so the dynamic merge can be restored in the future.
    // const items = this.dashboardItems();
    // return items.length > 0
    //   ? [...this.staticMenu, { label: 'Visualizaciones', children: items }]
    //   : [...this.staticMenu];
    return [...this.staticMenu];
  });

  // Footer items rendered outside the recursive menu tree.
  accountMenu: MenuNode[] = [
    { id: 'change-password', label: 'Cambiar contraseña', icon: 'pi-lock', permission: 'menu.cuenta.change_password' },
  ];

  visibleMenu = computed<MenuNode[]>(() => {
    const children = this.contextItems().filter(item => item.id !== 'change-password');
    return children.length ? [{ label: this.modules().find(m => m.id === this.selectedModule())?.name ?? 'Menú', children }] : [];
  });
  visibleAccountMenu = computed(() => this.contextItems().filter(item => item.id === 'change-password'));
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
      // refreshDashboards() is disabled while the dashboards feature is
      // deactivated per user request (2026-09-10). The method itself is left
      // intact and unused so it can be re-wired here in the future.
      complete: () => {},
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

  navigateFromQueryList(tab: Tab) {
    if (tab === 'create') {
      // Editing uses the create form even when it is outside the current menu.
      if (this.authenticated() && this.auth.hasPermission('menu.cargar.create')) {
        this.activeTab.set(tab);
      }
      return;
    }
    this.setTab(tab);
  }

  setTab(tab: Tab) {
    if (tab === 'home' || this.contextItems().some(item => item.id === tab)) {
      this.activeTab.set(tab);
    }
  }

  changePassword() {
    this.setTab('change-password');
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

