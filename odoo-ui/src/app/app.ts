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
import { ToastModule } from 'primeng/toast';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { AuthService } from './services/auth';
import { APP_VERSION } from './version';

type Tab = 'home' | 'list' | 'create' | 'runner' | 'schedules' | 'upload' | 'admin' | 'change-password';

interface MenuNode {
  id?: Tab;
  label: string;
  icon?: string;
  permission?: string;
  children?: MenuNode[];
}

@Component({
  selector: 'app-root',
  imports: [QueryList, QueryCreate, QueryRunner, ScheduleManager, FileUpload, UserAdminComponent, LoginComponent, ChangePasswordComponent, WelcomeComponent, ToastModule, ButtonModule, TooltipModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App implements OnInit {
  private auth = inject(AuthService);
  private msg = inject(MessageService);

  activeTab = signal<Tab>('home');
  authenticated = this.auth.isAuthenticated;
  user = this.auth.user;
  sidebarCollapsed = signal(false);
  appVersion = APP_VERSION;

  // Hierarchical menu definition. Supports 2 levels today and 3+ levels tomorrow
  // via the recursive filterMenu / render helpers.
  menuTree: MenuNode[] = [
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
      ]
    }
  ];

  // Footer items rendered outside the recursive menu tree.
  accountMenu: MenuNode[] = [
    { id: 'change-password', label: 'Cambiar contraseña', icon: 'pi-lock', permission: 'menu.cuenta.change_password' },
  ];

  visibleMenu = computed(() => this.filterMenu(this.menuTree));
  visibleAccountMenu = computed(() => this.filterMenu(this.accountMenu));
  hasAnyMenu = computed(() => this.visibleMenu().length > 0 || this.visibleAccountMenu().length > 0);

  ngOnInit() {
    this.auth.fetchMe().subscribe({
      error: () => {},
      complete: () => {},
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

