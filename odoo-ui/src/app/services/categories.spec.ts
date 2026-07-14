import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { CategoriesService, QueryCategory } from './categories';

describe('CategoriesService', () => {
  let svc: CategoriesService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    svc = TestBed.inject(CategoriesService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('list() GETs /categories/', () => {
    const mock: QueryCategory[] = [{ id: 1, name: 'General', description: null, created_at: '' }];
    let got: QueryCategory[] | undefined;
    svc.list().subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/categories/');
    expect(req.request.method).toBe('GET');
    req.flush(mock);
    expect(got).toEqual(mock);
  });

  it('create() POSTs name and description', () => {
    let got: QueryCategory | undefined;
    svc.create('Finance', 'd').subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/categories/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'Finance', description: 'd' });
    req.flush({ id: 2, name: 'Finance', description: 'd', created_at: '' });
    expect(got?.id).toBe(2);
  });

  it('remove() DELETEs /categories/{id}', () => {
    let done = false;
    svc.remove(3).subscribe(() => (done = true));
    const req = http.expectOne('http://localhost:8000/categories/3');
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: 'No Content' });
    expect(done).toBe(true);
  });
});
