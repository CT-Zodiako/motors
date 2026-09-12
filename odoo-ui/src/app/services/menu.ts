import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../environments/environment';

export interface MenuOption {
  id: string;
  module_id: string;
  name: string;
  menu_key: string;
  workflow_url?: string | null;
  permission_id: string;
  active: boolean;
  sort_order: number;
}

export interface NavigationModule {
  id: string;
  system_id: string;
  name: string;
  active: boolean;
  sort_order: number;
  menu: MenuOption[];
}

export interface NavigationSystem {
  id: string;
  name: string;
  active: boolean;
  sort_order: number;
  modules: NavigationModule[];
}

export interface NavigationContext {
  systems: NavigationSystem[];
  selected_system_id: string | null;
  selected_module_id: string | null;
  menu: MenuOption[];
}

@Injectable({ providedIn: 'root' })
export class MenuService {
  private http = inject(HttpClient);

  getContext(systemId?: string, moduleId?: string) {
    let params = new HttpParams();
    if (systemId) params = params.set('system_id', systemId);
    if (systemId && moduleId) params = params.set('module_id', moduleId);
    return this.http.get<NavigationContext>(`${environment.apiUrl}/auth/context`, {
      params,
      withCredentials: true,
    });
  }
}
