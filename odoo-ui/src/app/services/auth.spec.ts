import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AuthService, User } from './auth';

describe('AuthService', () => {
  let svc: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    svc = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('login POSTs credentials and updates user signal', () => {
    let got: { user: User } | undefined;
    const user: User = { id: '1', email: 'a@b.com', role: 'admin' };
    svc.login({ email: 'a@b.com', password: 'pw' }).subscribe((r) => (got = r));

    const req = http.expectOne('http://localhost:8000/auth/login');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email: 'a@b.com', password: 'pw' });
    expect(req.request.withCredentials).toBe(true);
    req.flush({ user });

    expect(got?.user).toEqual(user);
    expect(svc.isAuthenticated()).toBe(true);
  });

  it('logout POSTs and clears user signal', () => {
    svc.login({ email: 'a@b.com', password: 'pw' }).subscribe();
    const loginReq = http.expectOne('http://localhost:8000/auth/login');
    loginReq.flush({ user: { id: '1', email: 'a@b.com', role: 'admin' } });
    expect(svc.isAuthenticated()).toBe(true);

    svc.logout().subscribe();
    const req = http.expectOne('http://localhost:8000/auth/logout');
    expect(req.request.method).toBe('POST');
    expect(req.request.withCredentials).toBe(true);
    req.flush({ ok: true });

    expect(svc.isAuthenticated()).toBe(false);
  });

  it('fetchMe GETs /auth/me and stores user', () => {
    const user: User = { id: '1', email: 'a@b.com', role: 'admin' };
    svc.fetchMe().subscribe();
    const req = http.expectOne('http://localhost:8000/auth/me');
    expect(req.request.method).toBe('GET');
    expect(req.request.withCredentials).toBe(true);
    req.flush(user);
    expect(svc.user()).toEqual(user);
  });

  it('fetchMe clears user on 401', () => {
    svc.login({ email: 'a@b.com', password: 'pw' }).subscribe();
    const loginReq = http.expectOne('http://localhost:8000/auth/login');
    loginReq.flush({ user: { id: '1', email: 'a@b.com', role: 'admin' } });
    expect(svc.isAuthenticated()).toBe(true);

    svc.fetchMe().subscribe((result) => {
      expect(result).toBeNull();
    });
    const req = http.expectOne('http://localhost:8000/auth/me');
    req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });
    expect(svc.isAuthenticated()).toBe(false);
  });

  it('changePassword POSTs payload with credentials', () => {
    let ok: boolean | undefined;
    svc.changePassword({ current_password: 'old', new_password: 'new' }).subscribe((r) => (ok = r.ok));
    const req = http.expectOne('http://localhost:8000/auth/change-password');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ current_password: 'old', new_password: 'new' });
    expect(req.request.withCredentials).toBe(true);
    req.flush({ ok: true });
    expect(ok).toBe(true);
  });
});
