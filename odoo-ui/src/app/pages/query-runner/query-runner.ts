import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OdooQueriesService, OdooQuery, QueryResult } from '../../services/odoo-queries';
import { SelectModule } from 'primeng/select';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ChipModule } from 'primeng/chip';
import { SkeletonModule } from 'primeng/skeleton';
import { MessageService } from 'primeng/api';
import { SplitButtonModule } from 'primeng/splitbutton';

@Component({
  selector: 'app-query-runner',
  imports: [FormsModule, SelectModule, ButtonModule, TableModule, TagModule, ChipModule, SkeletonModule, SplitButtonModule],
  templateUrl: './query-runner.html',
  styleUrl: './query-runner.css',
})
export class QueryRunner implements OnInit {
  private svc = inject(OdooQueriesService);
  private msg = inject(MessageService);
  private apiBase = 'http://localhost:8000';

  queries = signal<OdooQuery[]>([]);
  selected = signal<OdooQuery | null>(null);
  running = signal(false);
  result = signal<QueryResult | null>(null);
  checkedColumns = signal<Set<string>>(new Set());

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
}
