import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { MessageService } from 'primeng/api';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-change-password',
  imports: [FormsModule, ButtonModule, InputTextModule],
  templateUrl: './change-password.html',
  styleUrl: './change-password.css',
})
export class ChangePasswordComponent {
  private auth = inject(AuthService);
  private msg = inject(MessageService);

  currentPassword = '';
  newPassword = '';
  loading = signal(false);

  onSubmit() {
    if (!this.currentPassword || !this.newPassword) {
      this.msg.add({
        severity: 'warn',
        summary: 'Campos requeridos',
        detail: 'Completá ambos campos',
      });
      return;
    }

    if (this.currentPassword === this.newPassword) {
      this.msg.add({
        severity: 'warn',
        summary: 'Contraseña inválida',
        detail: 'La nueva contraseña debe ser distinta a la actual',
      });
      return;
    }

    this.loading.set(true);
    this.auth
      .changePassword({
        current_password: this.currentPassword,
        new_password: this.newPassword,
      })
      .subscribe({
        next: () => {
          this.loading.set(false);
          this.currentPassword = '';
          this.newPassword = '';
          this.msg.add({
            severity: 'success',
            summary: 'Listo',
            detail: 'Contraseña actualizada correctamente',
          });
        },
        error: (err: { error?: { detail?: string } }) => {
          this.loading.set(false);
          this.msg.add({
            severity: 'error',
            summary: 'Error',
            detail: err.error?.detail ?? 'No se pudo cambiar la contraseña',
          });
        },
      });
  }
}
