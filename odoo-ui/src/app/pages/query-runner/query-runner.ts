import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OdooQueriesService, OdooQuery, QueryResult } from '../../services/odoo-queries';
import { BigQueryService, BigQueryDataset, BigQueryTable } from '../../services/bigquery';
import { Select } from 'primeng/select';
import { Button } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { Tag } from 'primeng/tag';
import { MessageService } from 'primeng/api';
import { SplitButton } from 'primeng/splitbutton';
import { Dialog } from 'primeng/dialog';
import { ProgressSpinner } from 'primeng/progressspinner';
import { InputTextModule } from 'primeng/inputtext';


@Component({
  selector: 'app-query-runner',
  imports: [
    FormsModule,
    Select,
    Button,
    TableModule,
    Tag,
    SplitButton,
    Dialog,
    ProgressSpinner,
    InputTextModule,
  ],
  templateUrl: './query-runner.html',
  styleUrl: './query-runner.css',
})
export class QueryRunner implements OnInit {
  private svc = inject(OdooQueriesService);
  private bq = inject(BigQueryService);
  private msg = inject(MessageService);
  private apiBase = 'http://localhost:8000';

  queries = signal<OdooQuery[]>([]);
  selected = signal<OdooQuery | null>(null);
  running = signal(false);
  result = signal<QueryResult | null>(null);
  checkedColumns = signal<Set<string>>(new Set());

  bigQueryDialogVisible = signal(false);
  bigQueryDatasets = signal<BigQueryDataset[]>([]);
  bigQueryTables = signal<BigQueryTable[]>([]);
  selectedBigQueryDataset = signal<BigQueryDataset | null>(null);
  selectedBigQueryTableId = signal<string>('');
  bigQueryTableName = signal('');
  bigQueryCreateNewTable = signal(false);
  bigQueryLoading = signal(false);
  bigQuerySubmitting = signal(false);

  insertDialogVisible = signal(false);
  insertTableName = signal('');
  generatedSql = signal('');
  insertLoading = signal(false);

  allColumns = computed(() => {
    const data = this.result()?.data;
    if (!data || data.length === 0) return [];
    return Object.keys(data[0]);
  });

  activeColumns = computed(() =>
    this.allColumns().filter(c => this.checkedColumns().has(c))
  );

  allChecked = computed(() =>
    this.allColumns().length > 0 &&
    this.allColumns().every(c => this.checkedColumns().has(c))
  );

  exportItems = computed(() => [
    { label: 'CSV',          icon: 'pi pi-file',       command: () => this.download('csv') },
    { label: 'Excel',        icon: 'pi pi-file-excel', command: () => this.download('excel') },
    { label: 'SQL Postgres', icon: 'pi pi-server',     command: () => this.download('sql', 'postgres') },
    { label: 'SQL Oracle',   icon: 'pi pi-server',     command: () => this.download('sql', 'oracle') },
  ]);

  ngOnInit() {
    this.svc.list().subscribe({ next: (q) => this.queries.set(q.filter(x => x.active)) });
  }

  run() {
    const q = this.selected();
    if (!q) return;
    this.running.set(true);
    this.result.set(null);
    this.checkedColumns.set(new Set());

    this.svc.run(q.name).subscribe({
      next: (res) => {
        this.result.set(res);
        this.running.set(false);
        const cols = res.data.length > 0 ? Object.keys(res.data[0]) : [];
        this.checkedColumns.set(new Set(cols));
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'Error al ejecutar el query' });
        this.running.set(false);
      },
    });
  }

  toggleColumn(col: string) {
    const next = new Set(this.checkedColumns());
    next.has(col) ? next.delete(col) : next.add(col);
    this.checkedColumns.set(next);
  }

  toggleAll() {
    this.checkedColumns.set(
      this.allChecked() ? new Set() : new Set(this.allColumns())
    );
  }

  isChecked(col: string) { return this.checkedColumns().has(col); }

  download(format: 'csv' | 'excel' | 'sql', target?: 'postgres' | 'oracle') {
    const q = this.selected();
    if (!q) return;
    const params = new URLSearchParams();
    const cols = this.activeColumns();
    if (cols.length < this.allColumns().length) params.set('columns', cols.join(','));
    if (format === 'sql' && target) params.set('target', target);
    const qs = params.toString();
    window.open(`${this.apiBase}/export/${format}/${q.name}${qs ? '?' + qs : ''}`, '_blank');
  }

  cellValue(row: Record<string, unknown>, col: string): string {
    const val = row[col];
    if (val === null || val === undefined) return '—';
    if (Array.isArray(val)) return val.join(', ');
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
  }

  private _exportableValue(val: unknown): unknown {
    if (val === null || val === undefined) return null;
    if (Array.isArray(val)) return val.join(', ');
    if (typeof val === 'object') return JSON.stringify(val);
    return val;
  }

  openBigQueryDialog() {
    this.bigQueryDialogVisible.set(true);
    this.selectedBigQueryDataset.set(null);
    this.selectedBigQueryTableId.set('');
    this.bigQueryTables.set([]);
    this.bigQueryTableName.set('');
    this.bigQueryCreateNewTable.set(false);
    this.loadBigQueryDatasets();
  }

  closeBigQueryDialog() {
    this.bigQueryDialogVisible.set(false);
    this.selectedBigQueryDataset.set(null);
    this.selectedBigQueryTableId.set('');
    this.bigQueryTables.set([]);
    this.bigQueryTableName.set('');
    this.bigQueryCreateNewTable.set(false);
  }

  openInsertDialog() {
    this.insertDialogVisible.set(true);
    this.insertTableName.set('');
    this.generatedSql.set('');
  }

  closeInsertDialog() {
    this.insertDialogVisible.set(false);
    this.insertTableName.set('');
    this.generatedSql.set('');
  }

  generateInsert() {
    const table = this.insertTableName().trim();
    if (!table) return;
    const cols = this.activeColumns();
    if (cols.length === 0) return;

    const result = this.result();
    const rows = (result?.data ?? []).map((row) => {
      const filtered: Record<string, unknown> = {};
      for (const col of cols) {
        filtered[col] = this._exportableValue(row[col]);
      }
      return filtered;
    });

    this.insertLoading.set(true);
    this.svc.generateInsertPreview(table, cols, rows).subscribe({
      next: (res) => {
        this.generatedSql.set(res.sql);
        this.insertLoading.set(false);
      },
      error: () => {
        this.insertLoading.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo generar el SQL' });
      },
    });
  }

  copySql() {
    const sql = this.generatedSql();
    if (!sql) return;
    navigator.clipboard.writeText(sql).then(() => {
      this.msg.add({ severity: 'success', summary: 'Copiado', detail: 'SQL copiado al portapapeles' });
    }).catch(() => {
      this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo copiar el SQL' });
    });
  }

  loadBigQueryDatasets() {
    this.bigQueryLoading.set(true);
    this.bq.listDatasets().subscribe({
      next: (res) => {
        this.bigQueryDatasets.set(res.datasets);
        this.bigQueryLoading.set(false);
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los datasets de BigQuery' });
        this.bigQueryLoading.set(false);
      },
    });
  }

  onBigQueryDatasetChange() {
    const dataset = this.selectedBigQueryDataset();
    this.selectedBigQueryTableId.set('');
    this.bigQueryTables.set([]);
    this.bigQueryTableName.set('');
    if (!dataset) return;
    this.bigQueryLoading.set(true);
    this.bq.listTables(dataset.id).subscribe({
      next: (res) => {
        this.bigQueryTables.set(res.tables);
        this.bigQueryLoading.set(false);
      },
      error: () => {
        this.bigQueryLoading.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar las tablas de BigQuery' });
      },
    });
  }

  bigQueryModeOptions = [
    { label: 'Usar tabla existente', value: false },
    { label: 'Crear nueva tabla', value: true },
  ];

  confirmBigQueryUpload() {
    const dataset = this.selectedBigQueryDataset();
    const result = this.result();
    const cols = this.activeColumns();
    if (!dataset || !result || cols.length === 0) return;

    const tableName = this.bigQueryCreateNewTable()
      ? this.bigQueryTableName().trim()
      : this.selectedBigQueryTableId();
    if (!tableName) return;

    const rows = result.data.map((row) => {
      const filtered: Record<string, unknown> = {};
      for (const col of cols) {
        filtered[col] = this._exportableValue(row[col]);
      }
      return filtered;
    });

    this.bigQuerySubmitting.set(true);
    this.bq.uploadToBigQuery(dataset.id, tableName, rows).subscribe({
      next: (res) => {
        this.bigQuerySubmitting.set(false);
        this.msg.add({
          severity: 'success',
          summary: 'BigQuery',
          detail: `Cargados ${res.rows_loaded} registros en ${res.dataset_id}.${res.table_id}`,
        });
        this.closeBigQueryDialog();
      },
      error: () => {
        this.bigQuerySubmitting.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los datos en BigQuery' });
      },
    });
  }
}
