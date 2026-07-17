import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface UserAdmin {
  id: string;
  email: string;
  role: string;
  active: boolean;
}

export interface UserWithPermissions extends UserAdmin {
  permissions: string[];
}

export interface Permission {
  id: string;
  label: string;
  category: string | null;
}

export interface CreateUserPayload {
  email: string;
  password: string;
  role: string;
  active: boolean;
}

export interface UpdateUserPayload {
  role?: string;
  active?: boolean;
}

export interface SetPermissionPayload {
  permission_id: string;
  granted: boolean;
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  listUsers(): Observable<UserAdmin[]> {
    return this.http.get<UserAdmin[]>(`${this.base}/admin/users`, {
      withCredentials: true,
    });
  }

  getUser(userId: string): Observable<UserWithPermissions> {
    return this.http.get<UserWithPermissions>(`${this.base}/admin/users/${userId}`, {
      withCredentials: true,
    });
  }

  createUser(payload: CreateUserPayload): Observable<UserAdmin> {
    return this.http.post<UserAdmin>(`${this.base}/admin/users`, payload, {
      withCredentials: true,
    });
  }

  updateUser(userId: string, payload: UpdateUserPayload): Observable<UserAdmin> {
    return this.http.patch<UserAdmin>(`${this.base}/admin/users/${userId}`, payload, {
      withCredentials: true,
    });
  }

  resetPassword(userId: string, password: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/admin/users/${userId}/reset-password`, {
      password,
    }, { withCredentials: true });
  }

  listPermissions(): Observable<{ permissions: Permission[] }> {
    return this.http.get<{ permissions: Permission[] }>(`${this.base}/admin/permissions`, {
      withCredentials: true,
    });
  }

  setPermission(userId: string, payload: SetPermissionPayload): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(
      `${this.base}/admin/users/${userId}/permissions`,
      payload,
      { withCredentials: true }
    );
  }
}
