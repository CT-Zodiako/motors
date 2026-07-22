import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Dashboard {
  name: string;
  embed_url: string;
}

@Injectable({ providedIn: 'root' })
export class DashboardsService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  getByMenuKey(menuKey: string): Observable<Dashboard> {
    return this.http.get<Dashboard>(`${this.base}/dashboards/${menuKey}`);
  }
}
