import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TitleCasePipe } from '@angular/common';
import { finalize, forkJoin, Observable } from 'rxjs';
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

  deleteDialogVisible = signal(false);
  userToDelete = signal<UserAdmin | null>(null);

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
      const edits: Observable<any>[] = [this.admin.updateUser(model.id, payload)];
      if (model.password) {
        edits.push(this.admin.resetPassword(model.id, model.password));
      }
      forkJoin(edits).subscribe({
        next: () => {
          const successMessage = model.password ? 'Usuario, contraseña y permisos actualizados' : 'Usuario y permisos actualizados';
          this.savePermissions(model.id!, successMessage);
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
        .subscribe({
          next: (created) => {
            this.savePermissionsAfterCreate(created.id);
          },
          error: (err) => {
            this.saving.set(false);
            const detail = err.status === 409 ? 'El email ya existe' : 'No se pudo crear el usuario';
            this.msg.add({ severity: 'error', summary: 'Error', detail });
          },
        });
    }
  }

  private savePermissionsAfterCreate(userId: string) {
    const requests = this.permissions()
      .filter((perm) => this.selectedPermissions()[perm.id] !== undefined)
      .map((perm) =>
        this.admin.setPermission(userId, {
          permission_id: perm.id,
          granted: !!this.selectedPermissions()[perm.id],
        })
      );

    if (requests.length === 0) {
      this.finishSave('Usuario creado');
      return;
    }

    forkJoin(requests).subscribe({
      next: () => this.finishSave('Usuario y permisos creados'),
      error: () => this.finishSave('Usuario creado, pero algunos permisos fallaron', 'warn'),
    });
  }

  private savePermissions(userId: string, successMessage = 'Usuario y permisos actualizados') {
    const requests = this.permissions()
      .filter((perm) => this.selectedPermissions()[perm.id] !== undefined)
      .map((perm) =>
        this.admin.setPermission(userId, {
          permission_id: perm.id,
          granted: !!this.selectedPermissions()[perm.id],
        })
      );

    if (requests.length === 0) {
      this.finishSave(successMessage);
      return;
    }

    forkJoin(requests).subscribe({
      next: () => this.finishSave(successMessage),
      error: () => this.finishSave('Usuario actualizado, pero algunos permisos fallaron', 'warn'),
    });
  }

  private finishSave(detail: string, severity: 'success' | 'warn' = 'success') {
    this.saving.set(false);
    this.dialogVisible.set(false);
    this.loadUsers();
    this.msg.add({ severity, summary: severity === 'success' ? 'Listo' : 'Atención', detail });
  }

  openDeleteDialog(user: UserAdmin) {
    this.userToDelete.set(user);
    this.deleteDialogVisible.set(true);
  }

  cancelDelete() {
    this.userToDelete.set(null);
    this.deleteDialogVisible.set(false);
  }

  confirmDelete() {
    const user = this.userToDelete();
    if (!user) return;
    this.admin.deleteUser(user.id).subscribe({
      next: () => {
        this.userToDelete.set(null);
        this.deleteDialogVisible.set(false);
        this.loadUsers();
        this.msg.add({ severity: 'success', summary: 'Listo', detail: 'Usuario eliminado' });
      },
      error: () => {
        this.userToDelete.set(null);
        this.deleteDialogVisible.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo eliminar el usuario' });
      },
    });
  }
}

