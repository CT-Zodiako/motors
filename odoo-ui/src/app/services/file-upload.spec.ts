import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { FileUploadService, ColumnDecision } from './file-upload';

describe('FileUploadService', () => {
  let svc: FileUploadService;
  let http: HttpTestingController;
  const file = new File(['a,b\n1,2\n'], 'datos.csv', { type: 'text/csv' });

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    svc = TestBed.inject(FileUploadService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('inspect() POSTs FormData with file and sourceType to /inspect', () => {
    let got: unknown;
    svc.inspect(file, 'csv').subscribe((r) => (got = r));
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/inspect');
    expect(req.request.method).toBe('POST');
    const body = req.request.body as FormData;
    expect(body instanceof FormData).toBe(true);
    expect(body.get('sourceType')).toBe('csv');
    expect(body.get('file')).toBeTruthy();
    req.flush({ sourceType: 'csv', fileName: 'datos.csv', sizeBytes: 8, sheets: ['CSV'], sheetCount: 1 });
    expect(got).toEqual({ sourceType: 'csv', fileName: 'datos.csv', sizeBytes: 8, sheets: ['CSV'], sheetCount: 1 });
  });

  it('preview() sends the sheet field when provided', () => {
    svc.preview(file, 'xlsx', 'Hoja2').subscribe();
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/preview');
    const body = req.request.body as FormData;
    expect(body.get('sourceType')).toBe('xlsx');
    expect(body.get('sheet')).toBe('Hoja2');
    req.flush({ sheet: 'Hoja2', columns: [], sample: [], totalRows: 0 });
  });

  it('preview() omits the sheet field when not provided', () => {
    svc.preview(file, 'csv').subscribe();
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/preview');
    const body = req.request.body as FormData;
    expect(body.get('sheet')).toBeNull();
    req.flush({ sheet: 'CSV', columns: [], sample: [], totalRows: 0 });
  });

  it('load() sends decisions as JSON string plus dataset/table', () => {
    const decisions: ColumnDecision[] = [
      { source: 'precio', name: 'precio', type: 'INT64', included: true },
      { source: 'cant', name: 'cant', type: 'INT64', included: false },
    ];
    svc.load(file, 'csv', 'CSV', decisions, 'raw', 'nueva').subscribe();
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/load');
    const body = req.request.body as FormData;
    expect(body.get('dataset')).toBe('raw');
    expect(body.get('table')).toBe('nueva');
    expect(body.get('sheet')).toBe('CSV');
    expect(JSON.parse(body.get('decisions') as string)).toEqual(decisions);
    req.flush({ table: 'p.raw.nueva', rows: 2 });
  });

  it('propagates backend errors', () => {
    let err: unknown;
    svc.inspect(file, 'csv').subscribe({ error: (e: unknown) => (err = e) });
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/inspect');
    req.flush({ detail: 'Unsupported file type' }, { status: 415, statusText: 'Unsupported Media Type' });
    expect((err as { status: number }).status).toBe(415);
  });

  it('inspect() sends skipRows when provided', () => {
    svc.inspect(file, 'csv', 2).subscribe();
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/inspect');
    expect((req.request.body as FormData).get('skipRows')).toBe('2');
    req.flush({ sourceType: 'csv', fileName: 'd.csv', sizeBytes: 8, sheets: ['CSV'], sheetCount: 1 });
  });

  it('preview() sends skipRows when provided and omits it otherwise', () => {
    svc.preview(file, 'csv', 'CSV', 2).subscribe();
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/preview');
    expect((req.request.body as FormData).get('skipRows')).toBe('2');
    req.flush({ sheet: 'CSV', columns: [], sample: [], totalRows: 0 });
  });

  it('load() sends skipRows when provided', () => {
    const decisions: ColumnDecision[] = [{ source: 'a', name: 'a', type: 'STRING', included: true }];
    svc.load(file, 'csv', 'CSV', decisions, 'raw', 't', 3).subscribe();
    const req = http.expectOne('http://localhost:8000/bigquery/upload-file/load');
    expect((req.request.body as FormData).get('skipRows')).toBe('3');
    req.flush({ table: 'p.raw.t', rows: 1 });
  });
});
