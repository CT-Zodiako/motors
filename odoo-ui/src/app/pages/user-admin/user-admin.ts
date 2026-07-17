import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TitleCasePipe } from '@angular/common';
import { finalize, forkJoin } from 'rxjs';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { Dialog } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { Checkbox } from 'primeng/checkbox';
import { ToggleSwitch } from 'primeng/toggleswitch';
import { Tag } from 'primeng/tag';
import { Tooltip } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import {
  AdminService,
  CreateUserPayload,
  Permission,
  UpdateUserPayload,
  UserAdmin,
} from '../../services/admin';

interface UserFormModel {
  id?: string;
  email: string;
  password: string;
  role: string;
  active: boolean;
}

interface PermissionGroup {
  category: string;
  permissions: Permission[];
}

@Component({
  selector: 'app-user-admin',
  imports: [FormsModule, TitleCasePipe, TableModule, ButtonModule, Dialog, InputTextModule, SelectModule, Checkbox, ToggleSwitch, Tag, Tooltip],
  templateUrl: './user-admin.html',
  styleUrl: './user-admin.css',
})
export class UserAdminComponent implements OnInit {
  private admin = inject(AdminService);
  private msg = inject(MessageService);

  users = signal<UserAdmin[]>([]);
  permissions = signal<Permission[]>([]);
  loading = signal(false);
  saving = signal(false);

  dialogVisible = signal(false);
  isEditing = signal(false);
  selectedUser = signal<UserFormModel | null>(null);
  selectedPermissions = signal<Record<string, boolean>>({});
  dialogTitle = computed(() => (this.isEditing() ? 'Editar usuario' : 'Nuevo usuario'));

  roleOptions = [
    { label: 'Admin', value: 'admin' },
    { label: 'Usuario', value: 'user' },
  ];

  permissionGroups = computed<PermissionGroup[]>(() => {
    const groups = new Map<string, Permission[]>();
    for (const perm of this.permissions()) {
      const category = perm.category || 'Otros';
      if (!groups.has(category)) {
        groups.set(category, []);
      }
      groups.get(category)!.push(perm);
    }
    return Array.from(groups.entries()).map(([category, permissions]) => ({
      category,
      permissions,
    }));
  });

  ngOnInit() {
    this.loadUsers();
    this.loadPermissions();
  }

  private loadUsers() {
    this.loading.set(true);
    this.admin
      .listUsers()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (data) => this.users.set(data),
        error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los usuarios' }),
      });
  }

  private loadPermissions() {
    this.admin.listPermissions().subscribe({
      next: (res) => this.permissions.set(res.permissions),
      error: () => {},
    });
  }

  openCreate() {
    this.isEditing.set(false);
    this.selectedUser.set({ email: '', password: '', role: 'user', active: true });
    this.selectedPermissions.set({});
    this.dialogVisible.set(true);
  }

  openEdit(user: UserAdmin) {
    this.isEditing.set(true);
    this.selectedUser.set({ id: user.id, email: user.email, password: '', role: user.role, active: user.active });
    this.selectedPermissions.set({});
    this.dialogVisible.set(true);
    this.loadUserPermissions(user.id);
  }

  private loadUserPermissions(userId: string) {
    this.admin.getUser(userId).subscribe({
      next: (user) => {
        const map: Record<string, boolean> = {};
        for (const p of this.permissions()) {
          map[p.id] = user.permissions.includes(p.id);
        }
        this.selectedPermissions.set(map);
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los permisos' }),
    });
  }

  togglePermission(permissionId: string, granted: boolean) {
    this.selectedPermissions.update((state) => ({ ...state, [permissionId]: granted }));
  }

  saveUser() {
    const model = this.selectedUser();
    if (!model) return;

    if (!model.email || (!model.password && !this.isEditing())) {
      this.msg.add({ severity: 'error', summary: 'Error', detail: 'Email y contraseña son obligatorios' });
      return;
    }

    this.saving.set(true);
    if (this.isEditing() && model.id) {
      const payload: UpdateUserPayload = { role: model.role, active: model.active };
      this.admin
        .updateUser(model.id, payload)
        .pipe(finalize(() => this.saving.set(false)))
        .subscribe({
          next: () => {
            this.savePermissions(model.id!);
          },
          error: () => {
            this.saving.set(false);
            this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo actualizar el usuario' });
          },
        });
    } else {
      const payload: CreateUserPayload = {
        email: model.email,
        password: model.password,
        role: model.role,
        active: model.active,
      };
      this.admin
        .createUser(payload)
        .pipe(finalize(() => this.saving.set(false)))
        .subscribe({
          next: (created) => {
            this.dialogVisible.set(false);
            this.loadUsers();
            this.msg.add({ severity: 'success', summary: 'Listo', detail: `Usuario ${created.email} creado` });
          },
          error: (err) => {
            const detail = err.status === 409 ? 'El email ya existe' : 'No se pudo crear el usuario';
            this.msg.add({ severity: 'error', summary: 'Error', detail });
          },
        });
    }
  }

  private savePermissions(userId: string) {
    const requests = this.permissions()
      .filter((perm) => this.selectedPermissions()[perm.id] !== undefined)
      .map((perm) =>
        this.admin.setPermission(userId, {
          permission_id: perm.id,
          granted: !!this.selectedPermissions()[perm.id],
        })
      );

    if (requests.length === 0) {
      this.dialogVisible.set(false);
      this.loadUsers();
      this.msg.add({ severity: 'success', summary: 'Listo', detail: 'Usuario actualizado' });
      return;
    }

    forkJoin(requests).subscribe({
      next: () => {
        this.dialogVisible.set(false);
        this.loadUsers();
        this.msg.add({ severity: 'success', summary: 'Listo', detail: 'Usuario y permisos actualizados' });
      },
      error: () => {
        this.dialogVisible.set(false);
        this.loadUsers();
        this.msg.add({ severity: 'warn', summary: 'Atención', detail: 'Usuario actualizado, pero algunos permisos fallaron' });
      },
    });
  }
}
