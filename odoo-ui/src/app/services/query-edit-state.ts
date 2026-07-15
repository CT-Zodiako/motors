import { Injectable, signal } from '@angular/core';
import { OdooQuery } from './odoo-queries';

export interface EditState {
  query: OdooQuery | null;
}

@Injectable({ providedIn: 'root' })
export class QueryEditStateService {
  private _state = signal<EditState>({ query: null });

  readonly state = this._state.asReadonly();

  beginEdit(query: OdooQuery): void {
    this._state.set({ query });
  }

  clear(): void {
    this._state.set({ query: null });
  }

  get isEditing(): boolean {
    return this._state().query !== null;
  }
}
