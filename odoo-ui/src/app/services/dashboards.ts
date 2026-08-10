import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface DashboardDefinition {
  model: string;
  fields: string[];
  group_by: string[];
  domain: unknown[];
  aggregations: Record<string, 'sum' | 'avg' | 'count'>;
}

export interface Dashboard {
  menu_key: string;
  name: string;
  embed_url: string | null;
  definition: DashboardDefinition | null;
  active: boolean;
}

/** Response shape of GET /dashboards/{menu_key} (published view path, design DD4). */
export interface DashboardGetResponse {
  name: string;
  embed_url: string | null;
  definition: DashboardDefinition | null;
}

export interface DashboardCreate {
  menu_key: string;
  name: string;
  embed_url?: string | null;
  definition?: DashboardDefinition | null;
  active?: boolean;
}

export interface DashboardPatch {
  menu_key?: string;
  name?: string;
  embed_url?: string | null;
  definition?: DashboardDefinition | null;
  active?: boolean;
}

export interface DashboardDataColumn {
  key: string;
  label: string;
  kind: 'group' | 'aggregate';
  function?: string;
}

/** Wire format of GET /dashboards/{menu_key}/data and POST /dashboards/preview (design §4.2). */
export interface DashboardData {
  menu_key: string;
  name: string;
  model: string;
  columns: DashboardDataColumn[];
  rows: Array<Record<string, unknown>>;
}

@Injectable({ providedIn: 'root' })
export class DashboardsService {
  private base = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getByMenuKey(menuKey: string): Observable<DashboardGetResponse> {
    return this.http.get<DashboardGetResponse>(`${this.base}/dashboards/${menuKey}`);
  }

  list(): Observable<Dashboard[]> {
    return this.http.get<Dashboard[]>(`${this.base}/dashboards/`);
  }

  create(body: DashboardCreate): Observable<Dashboard> {
    return this.http.post<Dashboard>(`${this.base}/dashboards/`, body);
  }

  update(menuKey: string, patch: DashboardPatch): Observable<Dashboard> {
    return this.http.patch<Dashboard>(`${this.base}/dashboards/${menuKey}`, patch);
  }

  delete(menuKey: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/dashboards/${menuKey}`);
  }

  getData(menuKey: string): Observable<DashboardData> {
    return this.http.get<DashboardData>(`${this.base}/dashboards/${menuKey}/data`);
  }

  preview(definition: DashboardDefinition): Observable<DashboardData> {
    return this.http.post<DashboardData>(`${this.base}/dashboards/preview`, definition);
  }
}
