import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { CheckboxModule } from 'primeng/checkbox';
import { MessageService } from 'primeng/api';
import {
  ColumnDecision,
  FileUploadService,
  InspectResponse,
  LoadResponse,
  PreviewResponse,
  SourceType,
} from '../../services/file-upload';
import { BigQueryService } from '../../services/bigquery';

// Mirrors _validate_identifier in odoo/routers/bigquery.py (design D13).
export const BQ_IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]{0,1023}$/;

const BQ_TYPES = ['INT64', 'FLOAT64', 'BOOL', 'DATE', 'TIMESTAMP', 'STRING'];

type Step = 'source' | 'sheet' | 'schema' | 'destination' | 'result';

interface DatasetOption {
  id: string;
  project: string;
}

@Component({
  selector: 'app-file-upload',
  imports: [FormsModule, ButtonModule, InputTextModule, SelectModule, TableModule, CheckboxModule],
  templateUrl: './file-upload.html',
  styleUrl: './file-upload.css',
})
export class FileUpload {
  private svc = inject(FileUploadService);
  private bq = inject(BigQueryService);
  private msg = inject(MessageService);

  step = signal<Step>('source');
  readonly steps: { id: Step; label: string }[] = [
    { id: 'source', label: 'Archivo' },
    { id: 'sheet', label: 'Hoja' },
    { id: 'schema', label: 'Esquema' },
    { id: 'destination', label: 'Destino' },
    { id: 'result', label: 'Resultado' },
  ];

  file = signal<File | null>(null);
  sourceType = signal<SourceType | null>(null);
  sourceError = signal('');
  inspect = signal<InspectResponse | null>(null);
  selectedSheet = signal<string | null>(null);
  preview = signal<PreviewResponse | null>(null);
  private previewCache = new Map<string, PreviewResponse>();
  columns = signal<ColumnDecision[]>([]);
  datasets = signal<DatasetOption[]>([]);
  dataset = signal<string | null>(null);
  table = signal('');
  busy = signal(false);
  error = signal('');
  result = signal<LoadResponse | null>(null);

  readonly bqTypes = BQ_TYPES;

  schemaValid = computed(() => {
    const included = this.columns().filter((c) => c.included);
    if (included.length === 0) return false;
    const seen = new Set<string>();
    for (const c of included) {
      const name = (c.name ?? '').trim();
      if (!BQ_IDENTIFIER_RE.test(name)) return false;
      const lowered = name.toLowerCase();
      if (seen.has(lowered)) return false;
      seen.add(lowered);
    }
    return true;
  });

  destinationValid = computed(
    () => !!this.dataset() && BQ_IDENTIFIER_RE.test(this.table().trim())
  );

  stepIndex(id: Step): number {
    return this.steps.findIndex((s) => s.id === id);
  }

  nameValid(name: string | null): boolean {
    return BQ_IDENTIFIER_RE.test((name ?? '').trim());
  }

  onFilePicked(event: Event) {
    const input = event.target as HTMLInputElement;
    const picked = input.files?.[0];
    if (!picked) return;
    this.sourceError.set('');
    this.error.set('');
    const name = picked.name.toLowerCase();
    const ext = name.includes('.') ? (name.split('.').pop() ?? '') : '';
    if (ext === 'xls') {
      this.sourceError.set('Los archivos .xls (formato viejo) no están soportados; guardalo como .xlsx');
      return;
    }
    if (ext !== 'xlsx' && ext !== 'csv') {
      this.sourceError.set('Formato no soportado. Aceptamos archivos .xlsx o .csv');
      return;
    }
    this.file.set(picked);
    this.sourceType.set(ext as SourceType);
    this.previewCache.clear();
    this.runPipeline(picked, ext as SourceType);
  }

  private runPipeline(f: File, st: SourceType) {
    this.busy.set(true);
    this.svc.inspect(f, st, undefined).subscribe({
      next: (resp) => {
        this.busy.set(false);
        this.inspect.set(resp);
        if (resp.sheetCount === 1) {
          this.selectedSheet.set(resp.sheets[0]);
          this.loadPreview();
        } else {
          this.step.set('sheet');
        }
      },
      error: (e) => {
        this.busy.set(false);
        this.sourceError.set(this.errorDetail(e));
      },
    });
  }

  retry() {
    const f = this.file();
    const st = this.sourceType();
    if (!f || !st) return;
    this.sourceError.set('');
    this.error.set('');
    this.runPipeline(f, st);
  }

  chooseSheet(name: string) {
    this.error.set('');
    this.selectedSheet.set(name);
    const cached = this.previewCache.get(this.cacheKey(name));
    if (cached) {
      this.preview.set(cached);
      this.columns.set(cached.columns.map((c) => ({ ...c })));
      this.step.set('schema');
      return;
    }
    this.loadPreview();
  }

  updateColumn(index: number, field: keyof ColumnDecision, value: unknown) {
    this.columns.update((cols) =>
      cols.map((c, i) => (i === index ? { ...c, [field]: value } : c))
    );
  }

  goDestination() {
    if (!this.schemaValid()) return;
    this.error.set('');
    this.step.set('destination');
    this.bq.listDatasets().subscribe({
      next: (resp) => this.datasets.set(resp.datasets),
      error: (e) => this.error.set(this.errorDetail(e)),
    });
  }

  confirmLoad() {
    if (this.busy()) return;
    const f = this.file();
    const st = this.sourceType();
    const ds = this.dataset();
    const tbl = this.table().trim();
    if (!f || !st || !ds || !BQ_IDENTIFIER_RE.test(tbl)) return;
    this.busy.set(true);
    this.error.set('');
    this.svc
      .load(f, st, this.selectedSheet() ?? undefined, this.columns(), ds, tbl, undefined)
      .subscribe({
      next: (resp) => {
        this.busy.set(false);
        this.result.set(resp);
        this.step.set('result');
      },
      error: (e) => {
        this.busy.set(false);
        this.error.set(this.errorDetail(e));
      },
    });
  }

  back() {
    if (this.step() === 'destination') {
      this.step.set('schema');
    } else if (this.step() === 'schema') {
      this.step.set(this.inspect() && this.inspect()!.sheetCount > 1 ? 'sheet' : 'source');
    } else if (this.step() === 'sheet') {
      this.step.set('source');
    } else if (this.step() === 'result') {
      this.step.set('destination');
    }
  }

  resetAll() {
    this.step.set('source');
    this.file.set(null);
    this.sourceType.set(null);
    this.sourceError.set('');
    this.inspect.set(null);
    this.selectedSheet.set(null);
    this.preview.set(null);
    this.previewCache.clear();
    this.columns.set([]);
    this.datasets.set([]);
    this.dataset.set(null);
    this.table.set('');
    this.busy.set(false);
    this.error.set('');
    this.result.set(null);
  }

  private loadPreview() {
    const f = this.file();
    const st = this.sourceType();
    if (!f || !st) return;
    this.busy.set(true);
    const sheet = this.selectedSheet() ?? undefined;
    this.svc.preview(f, st, sheet, undefined).subscribe({
      next: (resp) => {
        this.busy.set(false);
        if (sheet) this.previewCache.set(this.cacheKey(sheet), resp);
        this.preview.set(resp);
        this.columns.set(resp.columns.map((c) => ({ ...c })));
        this.step.set('schema');
      },
      error: (e) => {
        this.busy.set(false);
        const detail = this.errorDetail(e);
        if ((this.inspect()?.sheetCount ?? 1) > 1) {
          // Stay on the sheet step so the user can pick another sheet.
          this.error.set(detail);
          this.step.set('sheet');
        } else {
          this.sourceError.set(detail);
          this.step.set('source');
        }
      },
    });
  }

  private errorDetail(e: unknown): string {
    const err = e as { error?: { detail?: unknown }; message?: string };
    const detail = err?.error?.detail;
    if (typeof detail === 'string') return detail;
    return err?.message ?? 'Error inesperado';
  }

  private cacheKey(sheet: string): string {
    const f = this.file();
    return `${f?.name}:${f?.size}:${sheet}`;
  }
}
