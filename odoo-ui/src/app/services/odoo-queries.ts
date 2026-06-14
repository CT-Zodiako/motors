import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface OdooQuery {
  id: number;
  name: string;
  description: string;
  model: string;
  method: string;
  limit_val: number;
  active: boolean;
  created_at: string;
}

export interface QueryResult {
  query: string;
  total: number;
  data: Record<string, unknown>[];
}

export interface CreateQueryPayload {
  name: string;
  description: string;
  model: string;
  method: string;
  domain: unknown[];
  fields: string[];
  limit_val: number;
}

export interface FieldMeta {
  key: string;
  string: string;
  type: string;
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

  deactivate(name: string): Observable<unknown> {
    return this.http.delete(`${this.base}/queries/${name}`);
  }

  run(name: string): Observable<QueryResult> {
    return this.http.get<QueryResult>(`${this.base}/run/${name}`);
  }

  getFields(model: string): Observable<{ model: string; fields: Record<string, { string: string; type: string }> }> {
    return this.http.get<{ model: string; fields: Record<string, { string: string; type: string }> }>(
      `${this.base}/explore/fields/${model}`
    );
  }

  getAllModels(): Observable<{ total: number; models: { name: string; model: string; info: string }[] }> {
    return this.http.get<{ total: number; models: { name: string; model: string; info: string }[] }>(
      `${this.base}/explore/models`
    );
  }
}
