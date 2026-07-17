import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { MessageService } from 'primeng/api';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-login',
  imports: [FormsModule, ButtonModule, InputTextModule],
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private msg = inject(MessageService);

  email = '';
  password = '';
  loading = signal(false);

  onSubmit() {
    if (!this.email || !this.password) {
      this.msg.add({
        severity: 'warn',
        summary: 'Campos requeridos',
        detail: 'Ingresá email y contraseña',
      });
      return;
    }

    this.loading.set(true);
    this.auth.login({ email: this.email, password: this.password }).subscribe({
      next: () => {
        this.loading.set(false);
        this.msg.add({
          severity: 'success',
          summary: 'Bienvenido',
          detail: 'Sesión iniciada correctamente',
        });
      },
      error: (err: { error?: { detail?: string } }) => {
        this.loading.set(false);
        this.msg.add({
          severity: 'error',
          summary: 'Error de acceso',
          detail: err.error?.detail ?? 'Email o contraseña incorrectos',
        });
      },
    });
  }
}
