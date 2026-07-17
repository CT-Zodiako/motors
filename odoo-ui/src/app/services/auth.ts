import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, catchError, of, map } from 'rxjs';

export interface User {
  id: string;
  email: string;
  role: string;
}

export interface Credentials {
  email: string;
  password: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private base = 'http://localhost:8000';
  private userSignal = signal<User | null>(null);
  private permissionsSignal = signal<string[]>([]);
  private permissionsLoadedSignal = signal(false);

  user = computed(() => this.userSignal());
  isAuthenticated = computed(() => this.userSignal() !== null);
  permissions = computed(() => this.permissionsSignal());
  permissionsLoaded = computed(() => this.permissionsLoadedSignal());

  constructor(private http: HttpClient) {}

  private fetchPermissions(): Observable<string[]> {
    return this.http
      .get<{ permissions: string[] }>(`${this.base}/auth/permissions`, {
        withCredentials: true,
      })
      .pipe(
        map((res) => res.permissions ?? []),
        tap((permissions) => {
          this.permissionsSignal.set(permissions);
          this.permissionsLoadedSignal.set(true);
        }),
        catchError(() => {
          this.permissionsSignal.set([]);
          this.permissionsLoadedSignal.set(true);
          return of([]);
        })
      );
  }

  hasPermission(permission: string): boolean {
    return this.permissionsSignal().includes(permission);
  }

  login(credentials: Credentials): Observable<{ user: User }> {
    return this.http
      .post<{ user: User }>(`${this.base}/auth/login`, credentials, {
        withCredentials: true,
      })
      .pipe(
        tap((res) => {
          this.userSignal.set(res.user);
          this.fetchPermissions().subscribe();
        })
      );
  }

  logout(): Observable<{ ok: boolean }> {
    return this.http
      .post<{ ok: boolean }>(`${this.base}/auth/logout`, {}, { withCredentials: true })
      .pipe(
        tap(() => {
          this.userSignal.set(null);
          this.permissionsSignal.set([]);
          this.permissionsLoadedSignal.set(false);
        })
      );
  }

  fetchMe(): Observable<User | null> {
    return this.http
      .get<User>(`${this.base}/auth/me`, { withCredentials: true })
      .pipe(
        tap((user) => {
          this.userSignal.set(user);
          this.fetchPermissions().subscribe();
        }),
        catchError(() => {
          this.userSignal.set(null);
          this.permissionsSignal.set([]);
          this.permissionsLoadedSignal.set(false);
          return of(null);
        })
      );
  }

  changePassword(payload: ChangePasswordPayload): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(
      `${this.base}/auth/change-password`,
      payload,
      { withCredentials: true }
    );
  }

  clearAuth(): void {
    this.userSignal.set(null);
    this.permissionsSignal.set([]);
    this.permissionsLoadedSignal.set(false);
  }
}
