import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SchedulesService, Schedule, ScheduleFrequency, ScheduleRun } from '../../services/schedules';
import { OdooQueriesService, OdooQuery } from '../../services/odoo-queries';
import { BigQueryService, BigQueryDataset, BigQueryTable } from '../../services/bigquery';
import { Select } from 'primeng/select';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { InputNumber } from 'primeng/inputnumber';
import { Checkbox } from 'primeng/checkbox';
import { TableModule } from 'primeng/table';
import { Tag } from 'primeng/tag';
import { Dialog } from 'primeng/dialog';
import { MessageService } from 'primeng/api';
import { DatePipe } from '@angular/common';

const DAYS_OF_WEEK = [
  { label: 'Domingo', value: 0 },
  { label: 'Lunes', value: 1 },
  { label: 'Martes', value: 2 },
  { label: 'Miércoles', value: 3 },
  { label: 'Jueves', value: 4 },
  { label: 'Viernes', value: 5 },
  { label: 'Sábado', value: 6 },
];

const FREQUENCY_OPTIONS = [
  { label: 'Cada X horas', value: 'hourly' },
  { label: 'Diario', value: 'daily' },
  { label: 'Semanal', value: 'weekly' },
  { label: 'Mensual', value: 'monthly' },
];

@Component({
  selector: 'app-schedule-manager',
  imports: [
    FormsModule,
    Select,
    Button,
    InputText,
    InputNumber,
    Checkbox,
    TableModule,
    Tag,
    Dialog,
    DatePipe,
  ],
  templateUrl: './schedule-manager.html',
  styleUrl: './schedule-manager.css',
})
export class ScheduleManager implements OnInit {
  private svc = inject(SchedulesService);
  private queriesSvc = inject(OdooQueriesService);
  private bq = inject(BigQueryService);
  private msg = inject(MessageService);

  schedules = signal<Schedule[]>([]);
  queries = signal<OdooQuery[]>([]);
  datasets = signal<BigQueryDataset[]>([]);
  tables = signal<BigQueryTable[]>([]);
  loading = signal(false);
  saving = signal(false);
  runsLoading = signal(false);

  dialogVisible = false;
  editing: Schedule | null = null;

  // Form fields (plain values for ngModel)
  name = '';
  queryName = '';
  datasetId = '';
  tableId = '';
  frequency: ScheduleFrequency = 'daily';
  hour = 0;
  minute = 0;
  dayOfWeek = 1;
  dayOfMonth = 1;
  intervalHours = 1;
  active = true;

  runsDialogVisible = false;
  selectedSchedule: Schedule | null = null;
  runs = signal<ScheduleRun[]>([]);

  dayOfWeekOptions = DAYS_OF_WEEK;
  frequencyOptions = FREQUENCY_OPTIONS;

  showHourMinute = computed(() => this.frequency !== 'hourly');
  showDayOfWeek = computed(() => this.frequency === 'weekly');
  showDayOfMonth = computed(() => this.frequency === 'monthly');
  showIntervalHours = computed(() => this.frequency === 'hourly');

  ngOnInit() {
    this.loadSchedules();
    this.queriesSvc.list().subscribe({
      next: (q) => this.queries.set(q.filter(x => x.active)),
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los queries' }),
    });
    this.bq.listDatasets().subscribe({
      next: (res) => this.datasets.set(res.datasets),
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los datasets' }),
    });
  }

  loadSchedules() {
    this.loading.set(true);
    this.svc.list().subscribe({
      next: (s) => {
        this.schedules.set(s);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar las programaciones' });
      },
    });
  }

  onDatasetChange() {
    this.tableId = '';
    this.tables.set([]);
    if (!this.datasetId) return;
    this.bq.listTables(this.datasetId).subscribe({
      next: (res) => this.tables.set(res.tables),
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar las tablas' }),
    });
  }

  openCreate() {
    this.editing = null;
    this.resetForm();
    this.dialogVisible = true;
  }

  openEdit(schedule: Schedule) {
    this.editing = schedule;
    this.name = schedule.name;
    this.queryName = schedule.query_name;
    this.datasetId = schedule.dataset_id;
    this.frequency = schedule.frequency;
    this.hour = schedule.hour ?? 0;
    this.minute = schedule.minute ?? 0;
    this.dayOfWeek = schedule.day_of_week ?? 1;
    this.dayOfMonth = schedule.day_of_month ?? 1;
    this.intervalHours = schedule.interval_hours ?? 1;
    this.active = schedule.active;

    this.bq.listTables(this.datasetId).subscribe({
      next: (res) => {
        this.tables.set(res.tables);
        this.tableId = schedule.table_id;
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar las tablas' }),
    });

    this.dialogVisible = true;
  }

  closeDialog() {
    this.dialogVisible = false;
    this.editing = null;
    this.resetForm();
  }

  resetForm() {
    this.name = '';
    this.queryName = '';
    this.datasetId = '';
    this.tableId = '';
    this.frequency = 'daily';
    this.hour = 0;
    this.minute = 0;
    this.dayOfWeek = 1;
    this.dayOfMonth = 1;
    this.intervalHours = 1;
    this.active = true;
    this.tables.set([]);
  }

  save() {
    const payload = this.buildPayload();
    if (!payload) return;

    this.saving.set(true);
    const obs = this.editing
      ? this.svc.update(this.editing.id, payload)
      : this.svc.create(payload);

    obs.subscribe({
      next: () => {
        this.saving.set(false);
        this.dialogVisible = false;
        this.loadSchedules();
        this.msg.add({ severity: 'success', summary: 'Guardado', detail: 'Programación guardada correctamente' });
      },
      error: (err) => {
        this.saving.set(false);
        const detail = err?.error?.detail || 'No se pudo guardar la programación';
        this.msg.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  buildPayload() {
    if (!this.name.trim() || !this.queryName || !this.datasetId || !this.tableId) {
      this.msg.add({ severity: 'warn', summary: 'Faltan datos', detail: 'Completá todos los campos obligatorios' });
      return null;
    }

    const base = {
      name: this.name.trim(),
      query_name: this.queryName,
      dataset_id: this.datasetId,
      table_id: this.tableId,
      frequency: this.frequency,
      active: this.active,
    };

    if (this.frequency === 'hourly') {
      return { ...base, interval_hours: this.intervalHours };
    }

    const payload: any = { ...base, hour: this.hour, minute: this.minute };
    if (this.frequency === 'weekly') payload.day_of_week = this.dayOfWeek;
    if (this.frequency === 'monthly') payload.day_of_month = this.dayOfMonth;
    return payload;
  }

  deleteSchedule(schedule: Schedule) {
    this.svc.delete(schedule.id).subscribe({
      next: () => {
        this.loadSchedules();
        this.msg.add({ severity: 'success', summary: 'Eliminado', detail: 'Programación eliminada' });
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo eliminar la programación' }),
    });
  }

  toggleActive(schedule: Schedule) {
    this.svc.update(schedule.id, { active: !schedule.active }).subscribe({
      next: () => this.loadSchedules(),
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo actualizar el estado' }),
    });
  }

  runNow(schedule: Schedule) {
    this.svc.runNow(schedule.id).subscribe({
      next: (res) => {
        this.loadSchedules();
        this.msg.add({
          severity: res.status === 'success' ? 'success' : 'error',
          summary: 'Ejecución',
          detail: res.message || `Estado: ${res.status}`,
        });
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo ejecutar la programación' }),
    });
  }

  openRuns(schedule: Schedule) {
    this.selectedSchedule = schedule;
    this.runsDialogVisible = true;
    this.runsLoading.set(true);
    this.svc.getRuns(schedule.id).subscribe({
      next: (r) => {
        this.runs.set(r);
        this.runsLoading.set(false);
      },
      error: () => {
        this.runsLoading.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar las ejecuciones' });
      },
    });
  }

  closeRuns() {
    this.runsDialogVisible = false;
    this.selectedSchedule = null;
    this.runs.set([]);
  }

  statusSeverity(status: string | null): 'success' | 'danger' | 'warn' | 'secondary' {
    if (!status) return 'secondary';
    if (status === 'success') return 'success';
    if (status === 'error') return 'danger';
    if (status === 'running') return 'warn';
    return 'secondary';
  }

  frequencyLabel(freq: ScheduleFrequency): string {
    const found = this.frequencyOptions.find(o => o.value === freq);
    return found?.label || freq;
  }

  dayOfWeekLabel(value: number | null): string {
    if (value === null) return '';
    return this.dayOfWeekOptions.find(d => d.value === value)?.label || String(value);
  }

  scheduleSummary(schedule: Schedule): string {
    if (schedule.frequency === 'hourly') return `Cada ${schedule.interval_hours}h`;
    const time = `${String(schedule.hour).padStart(2, '0')}:${String(schedule.minute).padStart(2, '0')}`;
    if (schedule.frequency === 'daily') return `Diario a las ${time}`;
    if (schedule.frequency === 'weekly') return `Los ${this.dayOfWeekLabel(schedule.day_of_week)} a las ${time}`;
    if (schedule.frequency === 'monthly') return `Día ${schedule.day_of_month} a las ${time}`;
    return schedule.frequency;
  }
}
