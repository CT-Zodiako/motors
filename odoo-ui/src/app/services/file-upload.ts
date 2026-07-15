import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type SourceType = 'xlsx' | 'csv';

export interface InspectResponse {
  sourceType: SourceType;
  fileName: string;
  sizeBytes: number;
  sheets: string[];
  sheetCount: number;
}

export interface PreviewColumn {
  source: string;
  name: string;
  type: string;
  included: boolean;
}

export interface PreviewResponse {
  sheet: string;
  columns: PreviewColumn[];
  sample: unknown[][];
  totalRows: number;
}

export interface ColumnDecision {
  source: string;
  name: string | null;
  type: string | null;
  included: boolean;
}

export interface LoadResponse {
  table: string;
  rows: number;
}

@Injectable({ providedIn: 'root' })
export class FileUploadService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  inspect(file: File, sourceType: SourceType, skipRows?: number): Observable<InspectResponse> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('sourceType', sourceType);
    if (skipRows) {
      form.append('skipRows', String(skipRows));
    }
    return this.http.post<InspectResponse>(`${this.base}/bigquery/upload-file/inspect`, form);
  }

  preview(
    file: File,
    sourceType: SourceType,
    sheet?: string,
    skipRows?: number
  ): Observable<PreviewResponse> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('sourceType', sourceType);
    if (sheet !== undefined) {
      form.append('sheet', sheet);
    }
    if (skipRows) {
      form.append('skipRows', String(skipRows));
    }
    return this.http.post<PreviewResponse>(`${this.base}/bigquery/upload-file/preview`, form);
  }

  load(
    file: File,
    sourceType: SourceType,
    sheet: string | undefined,
    decisions: ColumnDecision[],
    dataset: string,
    table: string,
    skipRows?: number
  ): Observable<LoadResponse> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('sourceType', sourceType);
    if (sheet !== undefined) {
      form.append('sheet', sheet);
    }
    form.append('decisions', JSON.stringify(decisions));
    form.append('dataset', dataset);
    form.append('table', table);
    if (skipRows) {
      form.append('skipRows', String(skipRows));
    }
    return this.http.post<LoadResponse>(`${this.base}/bigquery/upload-file/load`, form);
  }
}
