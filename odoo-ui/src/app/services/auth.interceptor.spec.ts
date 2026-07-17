import { describe, expect, it, beforeEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { authInterceptor } from './auth.interceptor';
import { HttpClient } from '@angular/common/http';

describe('authInterceptor', () => {
  let http: HttpTestingController;
  let client: HttpClient;
  let msg: MessageService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        MessageService,
      ],
    });
    http = TestBed.inject(HttpTestingController);
    client = TestBed.inject(HttpClient);
    msg = TestBed.inject(MessageService);
  });

  it('adds withCredentials to outgoing requests', () => {
    client.get('http://localhost:8000/queries/').subscribe();
    const req = http.expectOne('http://localhost:8000/queries/');
    expect(req.request.withCredentials).toBe(true);
    req.flush([]);
  });
});
