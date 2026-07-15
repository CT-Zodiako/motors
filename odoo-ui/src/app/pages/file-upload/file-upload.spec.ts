import { describe, expect, it, beforeEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { MessageService } from 'primeng/api';
import { of, throwError, Subject } from 'rxjs';
import { FileUpload } from './file-upload';
import { FileUploadService } from '../../services/file-upload';
import { BigQueryService } from '../../services/bigquery';

const PREVIEW_XLSX = {
  sheet: 'Hoja1',
  columns: [
    { source: 'Fecha', name: 'Fecha', type: 'DATE', included: true },
    { source: 'precio', name: 'precio', type: 'FLOAT64', included: true },
  ],
  sample: [['2024-01-15', 10.5]],
  totalRows: 1,
};

class StubFileUploadService {
  calls: { method: string; args: unknown[] }[] = [];
  inspectResult: unknown = { sourceType: 'csv', fileName: 'd.csv', sizeBytes: 4, sheets: ['CSV'], sheetCount: 1 };
  previewResult: unknown = PREVIEW_XLSX;
  loadResult: unknown = { table: 'p.raw.nueva', rows: 2 };
  inspectError: unknown = null;
  previewError: unknown = null;
  loadError: unknown = null;
  loadSubject: Subject<unknown> | null = null;

  inspect(...args: unknown[]) {
    this.calls.push({ method: 'inspect', args });
    return this.inspectError ? throwError(() => this.inspectError) : of(this.inspectResult);
  }
  preview(...args: unknown[]) {
    this.calls.push({ method: 'preview', args });
    return this.previewError ? throwError(() => this.previewError) : of(this.previewResult);
  }
  load(...args: unknown[]) {
    this.calls.push({ method: 'load', args });
    if (this.loadSubject) return this.loadSubject.asObservable();
    return this.loadError ? throwError(() => this.loadError) : of(this.loadResult);
  }
}

class StubBigQueryService {
  listDatasets() {
    return of({ datasets: [{ id: 'raw', project: 'p' }, { id: 'mart', project: 'p' }] });
  }
}

function pickFile(component: FileUpload, name: string) {
  const file = new File(['x'], name);
  component.onFilePicked({ target: { files: [file] } } as unknown as Event);
}

function setup() {
  const uploadStub = new StubFileUploadService();
  TestBed.configureTestingModule({
    imports: [FileUpload],
    providers: [
      provideZonelessChangeDetection(),
      MessageService,
      { provide: FileUploadService, useValue: uploadStub },
      { provide: BigQueryService, useClass: StubBigQueryService },
    ],
  });
  const fixture = TestBed.createComponent(FileUpload);
  return { fixture, component: fixture.componentInstance, stub: uploadStub };
}

describe('FileUpload wizard', () => {
  let component: FileUpload;
  let stub: StubFileUploadService;

  beforeEach(() => {
    ({ component, stub } = setup());
  });

  it('rejects .xls with a dedicated message and no backend call', () => {
    pickFile(component, 'viejo.xls');
    expect(component.sourceError()).toContain('.xls');
    expect(component.sourceError()).toContain('.xlsx');
    expect(stub.calls.length).toBe(0);
    expect(component.step()).toBe('source');
  });

  it('rejects unknown extensions before any backend call', () => {
    pickFile(component, 'datos.pdf');
    expect(component.sourceError()).toBeTruthy();
    expect(stub.calls.length).toBe(0);
    expect(component.step()).toBe('source');
  });

  it('CSV skips the sheet step and lands in schema', () => {
    pickFile(component, 'datos.csv');
    expect(stub.calls.map((c) => c.method)).toEqual(['inspect', 'preview']);
    expect(component.step()).toBe('schema');
    expect(component.columns().length).toBe(2);
  });

  it('multi-sheet xlsx shows the sheet step and previews the chosen sheet', () => {
    stub.inspectResult = { sourceType: 'xlsx', fileName: 'd.xlsx', sizeBytes: 4, sheets: ['Hoja1', 'Datos'], sheetCount: 2 };
    pickFile(component, 'datos.xlsx');
    expect(component.step()).toBe('sheet');
    component.chooseSheet('Datos');
    expect(stub.calls.map((c) => c.method)).toEqual(['inspect', 'preview']);
    expect(stub.calls[1].args[2]).toBe('Datos');
    expect(component.step()).toBe('schema');
  });

  it('schema validation blocks duplicate resolved names (case-insensitive)', () => {
    pickFile(component, 'datos.csv');
    component.columns.update((cols) => [
      { ...cols[0], name: 'fecha' },
      { ...cols[1], name: 'FECHA' },
    ]);
    expect(component.schemaValid()).toBe(false);
  });

  it('schema validation blocks invalid identifiers', () => {
    pickFile(component, 'datos.csv');
    component.columns.update((cols) => [
      { ...cols[0], name: 'con espacio' },
      { ...cols[1] },
    ]);
    expect(component.schemaValid()).toBe(false);
  });

  it('schema validation requires at least one included column', () => {
    pickFile(component, 'datos.csv');
    component.columns.update((cols) => cols.map((c) => ({ ...c, included: false })));
    expect(component.schemaValid()).toBe(false);
  });

  it('load success shows the result with table and rows', () => {
    pickFile(component, 'datos.csv');
    component.goDestination();
    component.dataset.set('raw');
    component.table.set('nueva');
    component.confirmLoad();
    expect(component.step()).toBe('result');
    expect(component.result()).toEqual({ table: 'p.raw.nueva', rows: 2 });
  });

  it('busy guard prevents double submit while load is in flight', () => {
    stub.loadSubject = new Subject<unknown>();
    pickFile(component, 'datos.csv');
    component.goDestination();
    component.dataset.set('raw');
    component.table.set('nueva');
    component.confirmLoad();
    component.confirmLoad();
    expect(stub.calls.filter((c) => c.method === 'load').length).toBe(1);
    expect(component.busy()).toBe(true);
  });

  it('409 error is shown verbatim and wizard state is preserved for resubmit', () => {
    stub.loadError = { error: { detail: 'Table already exists: p.raw.nueva. Choose another name.' } };
    pickFile(component, 'datos.csv');
    component.goDestination();
    component.dataset.set('raw');
    component.table.set('nueva');
    component.confirmLoad();
    expect(component.step()).toBe('destination');
    expect(component.error()).toBe('Table already exists: p.raw.nueva. Choose another name.');
    expect(component.table()).toBe('nueva');
    expect(component.columns().length).toBe(2);

    stub.loadError = null;
    component.table.set('otra');
    component.confirmLoad();
    expect(component.step()).toBe('result');
  });

  it('back navigation preserves schema edits', () => {
    pickFile(component, 'datos.csv');
    component.columns.update((cols) => [{ ...cols[0], name: 'renombrada' }, { ...cols[1] }]);
    component.goDestination();
    component.back();
    expect(component.step()).toBe('schema');
    expect(component.columns()[0].name).toBe('renombrada');
  });

  it('resetAll returns to the source step with clean state', () => {
    pickFile(component, 'datos.csv');
    component.goDestination();
    component.resetAll();
    expect(component.step()).toBe('source');
    expect(component.file()).toBeNull();
    expect(component.columns()).toEqual([]);
    expect(component.result()).toBeNull();
  });

  it('re-choosing the same sheet reuses the cached preview', () => {
    stub.inspectResult = { sourceType: 'xlsx', fileName: 'd.xlsx', sizeBytes: 4, sheets: ['Hoja1', 'Datos'], sheetCount: 2 };
    pickFile(component, 'datos.xlsx');
    component.chooseSheet('Hoja1');
    expect(stub.calls.filter((c) => c.method === 'preview').length).toBe(1);
    component.back();
    component.chooseSheet('Hoja1');
    expect(stub.calls.filter((c) => c.method === 'preview').length).toBe(1);
    expect(component.step()).toBe('schema');
  });

  it('choosing a different sheet invalidates the cache and re-previews', () => {
    stub.inspectResult = { sourceType: 'xlsx', fileName: 'd.xlsx', sizeBytes: 4, sheets: ['Hoja1', 'Datos'], sheetCount: 2 };
    pickFile(component, 'datos.xlsx');
    component.chooseSheet('Hoja1');
    component.back();
    component.chooseSheet('Datos');
    expect(stub.calls.filter((c) => c.method === 'preview').length).toBe(2);
    expect(stub.calls[2].args[2]).toBe('Datos');
  });

  it('preview failure on multi-sheet keeps the sheet step with the error inline', () => {
    stub.inspectResult = { sourceType: 'xlsx', fileName: 'd.xlsx', sizeBytes: 4, sheets: ['Hoja1', 'Datos'], sheetCount: 2 };
    stub.previewError = { error: { detail: 'Row 2 has 19 fields, expected 5' } };
    pickFile(component, 'datos.xlsx');
    component.chooseSheet('Hoja1');
    expect(component.step()).toBe('sheet');
    expect(component.error()).toBe('Row 2 has 19 fields, expected 5');

    stub.previewError = null;
    component.chooseSheet('Datos');
    expect(component.error()).toBe('');
    expect(component.step()).toBe('schema');
  });

  it('preview failure on single-sheet file returns to source with the error', () => {
    stub.previewError = { error: { detail: 'corrupt file' } };
    pickFile(component, 'datos.csv');
    expect(component.step()).toBe('source');
    expect(component.sourceError()).toBe('corrupt file');
  });

  it('sheet step startRow input changes the skipRows sent to preview', () => {
    stub.inspectResult = { sourceType: 'xlsx', fileName: 'd.xlsx', sizeBytes: 4, sheets: ['Hoja1', 'Datos'], sheetCount: 2 };
    pickFile(component, 'datos.xlsx');
    component.setStartRow(3);
    component.chooseSheet('Datos');
    expect(stub.calls[1].args[3]).toBe(2);
  });

  it('retry on the source step re-runs the pipeline with the adjusted start row', () => {
    stub.previewError = { error: { detail: 'ragged' } };
    pickFile(component, 'datos.csv');
    expect(component.step()).toBe('source');
    stub.previewError = null;
    component.setStartRow(3);
    component.retry();
    expect(stub.calls.filter((c) => c.method === 'inspect').length).toBe(2);
    expect(stub.calls[2].args[2]).toBe(2);
    expect(stub.calls[3].args[3]).toBe(2);
    expect(component.step()).toBe('schema');
  });

  it('load sends skipRows derived from startRow', () => {
    pickFile(component, 'datos.csv');
    component.setStartRow(4);
    component.goDestination();
    component.dataset.set('raw');
    component.table.set('nueva');
    component.confirmLoad();
    const loadCall = stub.calls.find((c) => c.method === 'load');
    expect(loadCall?.args[6]).toBe(3);
  });
});
