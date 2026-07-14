import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface QueryCategory {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class CategoriesService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  list(): Observable<QueryCategory[]> {
    return this.http.get<QueryCategory[]>(`${this.base}/categories/`);
  }

  create(name: string, description?: string): Observable<QueryCategory> {
    return this.http.post<QueryCategory>(`${this.base}/categories/`, {
      name,
      description: description ?? null,
    });
  }

  remove(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/categories/${id}`);
  }
}
