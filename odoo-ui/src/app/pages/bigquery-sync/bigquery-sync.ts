import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';

import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { SkeletonModule } from 'primeng/skeleton';
import { MessageService } from 'primeng/api';

import {
  BigQueryService,
  BigQueryDataset,
  BigQueryTable,
} from '../../services/bigquery';

@Component({
  selector: 'app-bigquery-sync',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    TableModule,
    ButtonModule,
    SelectModule,
    SkeletonModule,
  ],
  templateUrl: './bigquery-sync.html',
  styleUrl: './bigquery-sync.css',
})
export class BigQuerySync implements OnInit {
  private svc = inject(BigQueryService);
  private msg = inject(MessageService);

  datasets = signal<BigQueryDataset[]>([]);
  selectedDataset = signal<string | null>(null);
  tables = signal<BigQueryTable[]>([]);
  datasetsLoading = signal(false);
  tablesLoading = signal(false);
  syncingTable = signal<string | null>(null);

  ngOnInit() {
    this.loadDatasets();
  }

  loadDatasets() {
    this.datasetsLoading.set(true);
    this.svc
      .listDatasets()
      .pipe(finalize(() => this.datasetsLoading.set(false)))
      .subscribe({
        next: (res) => this.datasets.set(res.datasets),
        error: () =>
          this.msg.add({
            severity: 'error',
            summary: 'Error',
            detail: 'No se pudieron cargar los datasets de BigQuery',
          }),
      });
  }

  onDatasetChange(datasetId: string | null) {
    this.selectedDataset.set(datasetId);
    this.tables.set([]);
    if (!datasetId) return;

    this.tablesLoading.set(true);
    this.svc
      .listTables(datasetId)
      .pipe(finalize(() => this.tablesLoading.set(false)))
      .subscribe({
        next: (res) => this.tables.set(res.tables),
        error: () =>
          this.msg.add({
            severity: 'error',
            summary: 'Error',
            detail: `No se pudieron cargar las tablas de ${datasetId}`,
          }),
      });
  }

  syncTable(table: BigQueryTable) {
    this.syncingTable.set(table.id);
    this.svc
      .syncTable(table.dataset_id, table.id)
      .pipe(finalize(() => this.syncingTable.set(null)))
      .subscribe({
        next: (res) =>
          this.msg.add({
            severity: 'success',
            summary: 'Sincronizado',
            detail: `${res.message}`,
          }),
        error: (err) =>
          this.msg.add({
            severity: 'error',
            summary: 'Error de sync',
            detail:
              err?.error?.detail ||
              `No se pudo sincronizar ${table.id}`,
          }),
      });
  }
}
