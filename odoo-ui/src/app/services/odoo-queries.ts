import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface QueryCategoryRef {
  id: number;
  name: string;
}

export interface OdooQuery {
  id: number;
  name: string;
  description: string;
  model: string;
  method: string;
  domain: unknown[];
  fields: string[];
  limit_val: number;
  active: boolean;
  created_at: string;
  category: QueryCategoryRef | null;
}

export interface QueryResult {
  query: string;
  total: number;
  data: Record<string, unknown>[];
}

export interface QueryDestination {
  id: number;
  query_name: string;
  dataset_id: string;
  table_id: string;
  origin: string | null;
  stale: boolean;
  last_error: string | null;
  last_sync_at: string | null;
  last_schema: unknown[] | null;
  created_at: string;
}

export interface CreateQueryPayload {
  name: string;
  description: string;
  model: string;
  method: string;
  domain: unknown[];
  fields: string[];
  limit_val: number;
  category_id?: number;
}

export interface FieldMeta {
  key: string;
  string: string;
  type: string;
  required?: boolean;
  readonly?: boolean;
  relation?: string;
  help?: string;
}

@Injectable({ providedIn: 'root' })
export class OdooQueriesService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  list(): Observable<OdooQuery[]> {
    return this.http.get<OdooQuery[]>(`${this.base}/queries/`);
  }

  create(payload: CreateQueryPayload): Observable<{ registered: string }> {
    return this.http.post<{ registered: string }>(`${this.base}/queries/`, payload);
  }

  setActive(name: string, active: boolean): Observable<unknown> {
    return this.http.patch(`${this.base}/queries/${encodeURIComponent(name)}`, { active });
  }

  delete(name: string): Observable<unknown> {
    return this.http.delete(`${this.base}/queries/${name}`);
  }

  updateCategory(name: string, categoryId: number): Observable<OdooQuery> {
    return this.http.patch<OdooQuery>(`${this.base}/queries/${name}`, { category_id: categoryId });
  }

  update(name: string, payload: Partial<CreateQueryPayload>): Observable<{ query: OdooQuery; propagation?: { total: number; ok: number; failed: number; destinations: { dataset_id: string; table_id: string; status: string; error?: string }[] } }> {
    return this.http.patch<{ query: OdooQuery; propagation?: any }>(`${this.base}/queries/${encodeURIComponent(name)}`, payload);
  }

  run(name: string): Observable<QueryResult> {
    return this.http.get<QueryResult>(`${this.base}/run/${name}`);
  }

  getDestination(queryName: string): Observable<QueryDestination | null> {
    return this.http.get<QueryDestination>(`${this.base}/queries/${encodeURIComponent(queryName)}/destination`)
      .pipe(catchError(() => of(null)));
  }

  generateInsertPreview(
    table: string,
    columns: string[],
    rows: Record<string, unknown>[],
  ): Observable<{ sql: string }> {
    return this.http.post<{ sql: string }>(`${this.base}/export/sql-preview`, { table, columns, rows });
  }

  getFields(model: string): Observable<{ model: string; fields: Record<string, { string: string; type: string; required?: boolean; readonly?: boolean; relation?: string; help?: string }> }> {
    return this.http.get<{ model: string; fields: Record<string, { string: string; type: string; required?: boolean; readonly?: boolean; relation?: string; help?: string }> }>(
      `${this.base}/explore/fields/${model}`
    );
  }

  getAllModels(): Observable<{ total: number; models: { name: string; model: string; info: string }[] }> {
    return this.http.get<{ total: number; models: { name: string; model: string; info: string }[] }>(
      `${this.base}/explore/models`
    );
  }
}
