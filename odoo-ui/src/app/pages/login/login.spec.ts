import { describe, expect, it, beforeEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideAnimations } from '@angular/platform-browser/animations';
import { MessageService } from 'primeng/api';
import { LoginComponent } from './login';
import { AuthService } from '../../services/auth';

describe('LoginComponent', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideAnimations(),
        MessageService,
      ],
    });
  });

  it('renders login form', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Iniciá sesión');
    expect(compiled.querySelector('input#email')).not.toBeNull();
    expect(compiled.querySelector('input#password')).not.toBeNull();
  });

  it('warns when fields are empty', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    const auth = TestBed.inject(AuthService);
    const msg = TestBed.inject(MessageService);
    const spy = vitest.spyOn(msg, 'add');

    fixture.componentInstance.onSubmit();
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ severity: 'warn' }));
    expect(auth.isAuthenticated()).toBe(false);
  });
});

import { vitest } from 'vitest';
