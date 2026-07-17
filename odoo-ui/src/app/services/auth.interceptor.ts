import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const msg = inject(MessageService);
  const auth = inject(AuthService);

  const authReq = req.clone({ withCredentials: true });

  return next(authReq).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && (err.status === 401 || err.status === 403)) {
        auth.clearAuth();
        msg.add({
          severity: 'error',
          summary: 'Sesión requerida',
          detail: 'Iniciá sesión para continuar',
        });
      }
      return throwError(() => err);
    })
  );
};
