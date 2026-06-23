import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface BigQueryDataset {
  id: string;
  project: string;
}

export interface BigQueryColumn {
  name: string;
  type: string;
  mode: string | null;
}

export interface BigQueryTable {
  id: string;
  dataset_id: string;
  full_id: string;
  rows: number;
  bytes: number;
  columns: BigQueryColumn[];
}

export interface BigQueryTablesResponse {
  dataset_id: string;
  tables: BigQueryTable[];
}

export interface BigQuerySyncResponse {
  synced: string;
  rows: number;
  message: string;
}

export interface BigQueryUploadResponse {
  dataset_id: string;
  table_id: string;
  rows_loaded: number;
}

@Injectable({ providedIn: 'root' })
export class BigQueryService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  listDatasets(): Observable<{ datasets: BigQueryDataset[] }> {
    return this.http.get<{ datasets: BigQueryDataset[] }>(`${this.base}/bigquery/datasets`);
  }

  listTables(datasetId: string): Observable<BigQueryTablesResponse> {
    return this.http.get<BigQueryTablesResponse>(`${this.base}/bigquery/tables/${datasetId}`);
  }

  syncTable(datasetId: string, tableId: string): Observable<BigQuerySyncResponse> {
    return this.http.post<BigQuerySyncResponse>(
      `${this.base}/bigquery/sync/${datasetId}/${tableId}`,
      {}
    );
  }

  uploadToBigQuery(
    datasetId: string,
    tableId: string,
    rows: Record<string, unknown>[]
  ): Observable<BigQueryUploadResponse> {
    return this.http.post<BigQueryUploadResponse>(
      `${this.base}/bigquery/upload/${datasetId}/${tableId}`,
      { rows }
    );
  }
}
