import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OdooQueriesService, OdooQuery, QueryResult } from '../../services/odoo-queries';
import { BigQueryService, BigQueryDataset, BigQueryTable } from '../../services/bigquery';
import { SchedulesService, ScheduleFrequency, ScheduleCreatePayload } from '../../services/schedules';
import { InputNumber } from 'primeng/inputnumber';
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
    InputNumber,
  ],
  templateUrl: './query-runner.html',
  styleUrl: './query-runner.css',
})
export class QueryRunner implements OnInit {
  private svc = inject(OdooQueriesService);
  private bq = inject(BigQueryService);
  private schedulesSvc = inject(SchedulesService);
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
  bigQueryLoading = signal(false);
  bigQuerySubmitting = signal(false);

  // Dialog model properties: use plain fields for ngModel to avoid signal
  // change-detection issues with PrimeNG Select.
  selectedBigQueryDataset: BigQueryDataset | null = null;
  selectedBigQueryTableId = '';
  bigQueryTableName = '';
  bigQueryCreateNewTable = false;
  bigQueryModeOptions = [
    { label: 'Usar tabla existente', value: false },
    { label: 'Crear nueva tabla', value: true },
  ];

  // Schedule section
  bigQueryActionMode: 'now' | 'schedule' = 'now';
  bigQueryActionOptions = [
    { label: 'Enviar ahora', value: 'now' },
    { label: 'Programar envío', value: 'schedule' },
  ];
  bigQueryScheduleName = '';
  bigQueryFrequency: ScheduleFrequency = 'daily';
  bigQueryFrequencyOptions = [
    { label: 'Cada X horas', value: 'hourly' },
    { label: 'Diario', value: 'daily' },
    { label: 'Semanal', value: 'weekly' },
    { label: 'Mensual', value: 'monthly' },
  ];
  bigQueryScheduleHour = 0;
  bigQueryScheduleMinute = 0;
  bigQueryScheduleDayOfWeek = 1;
  bigQueryScheduleDayOfMonth = 1;
  bigQueryScheduleIntervalHours = 1;
  bigQueryScheduleDayOfWeekOptions = [
    { label: 'Domingo', value: 0 },
    { label: 'Lunes', value: 1 },
    { label: 'Martes', value: 2 },
    { label: 'Miércoles', value: 3 },
    { label: 'Jueves', value: 4 },
    { label: 'Viernes', value: 5 },
    { label: 'Sábado', value: 6 },
  ];

  insertDialogVisible = signal(false);
  insertLoading = signal(false);

  insertTableName = '';
  generatedSql = signal('');

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

  formatScheduleTime(): string {
    const h = this.bigQueryScheduleHour ?? 0;
    const m = this.bigQueryScheduleMinute ?? 0;
    const ampm = h >= 12 ? 'PM' : 'AM';
    const displayHour = h % 12 === 0 ? 12 : h % 12;
    const displayMinute = String(m).padStart(2, '0');
    return `${displayHour}:${displayMinute} ${ampm}`;
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
    this.selectedBigQueryDataset = null;
    this.selectedBigQueryTableId = '';
    this.bigQueryTables.set([]);
    this.bigQueryTableName = '';
    this.bigQueryCreateNewTable = false;
    this.bigQueryActionMode = 'now';
    this.bigQueryScheduleName = '';
    this.bigQueryFrequency = 'daily';
    this.bigQueryScheduleHour = 0;
    this.bigQueryScheduleMinute = 0;
    this.bigQueryScheduleDayOfWeek = 1;
    this.bigQueryScheduleDayOfMonth = 1;
    this.bigQueryScheduleIntervalHours = 1;
    this.loadBigQueryDatasets();
  }

  closeBigQueryDialog() {
    this.bigQueryDialogVisible.set(false);
    this.selectedBigQueryDataset = null;
    this.selectedBigQueryTableId = '';
    this.bigQueryTables.set([]);
    this.bigQueryTableName = '';
    this.bigQueryCreateNewTable = false;
    this.bigQueryActionMode = 'now';
  }

  openInsertDialog() {
    this.insertDialogVisible.set(true);
    this.insertTableName = '';
    this.generatedSql.set('');
  }

  closeInsertDialog() {
    this.insertDialogVisible.set(false);
    this.insertTableName = '';
    this.generatedSql.set('');
  }

  generateInsert() {
    const table = this.insertTableName.trim();
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
    const dataset = this.selectedBigQueryDataset;
    this.selectedBigQueryTableId = '';
    this.bigQueryTables.set([]);
    this.bigQueryTableName = '';
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

  confirmBigQueryUpload() {
    const dataset = this.selectedBigQueryDataset;
    const result = this.result();
    const cols = this.activeColumns();
    if (!dataset || !result || cols.length === 0) return;

    const tableName = this.bigQueryCreateNewTable
      ? this.bigQueryTableName.trim()
      : this.selectedBigQueryTableId;
    if (!tableName) return;

    if (this.bigQueryActionMode === 'schedule') {
      this.createSchedule(dataset.id, tableName);
      return;
    }

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

  createSchedule(datasetId: string, tableId: string) {
    const q = this.selected();
    if (!q) return;

    const name = this.bigQueryScheduleName.trim() || `${q.name} → ${datasetId}.${tableId}`;
    const payload: ScheduleCreatePayload = {
      name,
      query_name: q.name,
      dataset_id: datasetId,
      table_id: tableId,
      frequency: this.bigQueryFrequency,
    };

    if (this.bigQueryFrequency === 'hourly') {
      payload.interval_hours = this.bigQueryScheduleIntervalHours;
    } else {
      payload.hour = this.bigQueryScheduleHour;
      payload.minute = this.bigQueryScheduleMinute;
      if (this.bigQueryFrequency === 'weekly') {
        payload.day_of_week = this.bigQueryScheduleDayOfWeek;
      }
      if (this.bigQueryFrequency === 'monthly') {
        payload.day_of_month = this.bigQueryScheduleDayOfMonth;
      }
    }

    this.bigQuerySubmitting.set(true);
    this.schedulesSvc.create(payload).subscribe({
      next: () => {
        this.bigQuerySubmitting.set(false);
        this.msg.add({ severity: 'success', summary: 'Programado', detail: 'Envío programado correctamente' });
        this.closeBigQueryDialog();
      },
      error: (err) => {
        this.bigQuerySubmitting.set(false);
        const detail = err?.error?.detail || 'No se pudo programar el envío';
        this.msg.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }
}
