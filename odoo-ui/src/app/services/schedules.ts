import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type ScheduleFrequency = 'hourly' | 'daily' | 'weekly' | 'monthly';

export interface Schedule {
  id: number;
  name: string;
  query_name: string;
  dataset_id: string;
  table_id: string;
  frequency: ScheduleFrequency;
  hour: number | null;
  minute: number | null;
  day_of_week: number | null;
  day_of_month: number | null;
  interval_hours: number | null;
  active: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_message: string | null;
  created_at: string;
}

export interface ScheduleCreatePayload {
  name: string;
  query_name: string;
  dataset_id: string;
  table_id: string;
  frequency: ScheduleFrequency;
  hour?: number | null;
  minute?: number | null;
  day_of_week?: number | null;
  day_of_month?: number | null;
  interval_hours?: number | null;
  active?: boolean;
}

export interface ScheduleRun {
  id: number;
  schedule_id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  message: string | null;
  rows_loaded: number | null;
}

@Injectable({ providedIn: 'root' })
export class SchedulesService {
  private base = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  list(): Observable<Schedule[]> {
    return this.http.get<Schedule[]>(`${this.base}/schedules/`);
  }

  getRuns(scheduleId: number): Observable<ScheduleRun[]> {
    return this.http.get<ScheduleRun[]>(`${this.base}/schedules/${scheduleId}/runs`);
  }

  create(payload: ScheduleCreatePayload): Observable<Schedule> {
    return this.http.post<Schedule>(`${this.base}/schedules/`, payload);
  }

  update(scheduleId: number, payload: Partial<ScheduleCreatePayload>): Observable<Schedule> {
    return this.http.patch<Schedule>(`${this.base}/schedules/${scheduleId}`, payload);
  }

  delete(scheduleId: number): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>(`${this.base}/schedules/${scheduleId}`);
  }

  runNow(scheduleId: number): Observable<{ status: string; rows_loaded?: number; message?: string }> {
    return this.http.post<{ status: string; rows_loaded?: number; message?: string }>(
      `${this.base}/schedules/${scheduleId}/run`,
      {}
    );
  }
}
