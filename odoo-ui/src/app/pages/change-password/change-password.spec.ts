import { describe, expect, it, beforeEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideAnimations } from '@angular/platform-browser/animations';
import { MessageService } from 'primeng/api';
import { ChangePasswordComponent } from './change-password';

describe('ChangePasswordComponent', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ChangePasswordComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideAnimations(),
        MessageService,
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  it('renders change password form', () => {
    const fixture = TestBed.createComponent(ChangePasswordComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Cambiar contraseña');
    expect(compiled.querySelector('input#current-password')).not.toBeNull();
    expect(compiled.querySelector('input#new-password')).not.toBeNull();
  });

  it('warns when new password equals current password', () => {
    const fixture = TestBed.createComponent(ChangePasswordComponent);
    const msg = TestBed.inject(MessageService);
    const spy = vitest.spyOn(msg, 'add');

    fixture.componentInstance.currentPassword = 'same';
    fixture.componentInstance.newPassword = 'same';
    fixture.componentInstance.onSubmit();

    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ severity: 'warn' }));
  });
});

import { vitest } from 'vitest';
