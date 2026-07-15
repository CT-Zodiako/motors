import { describe, expect, it, beforeEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { QueryEditStateService } from './query-edit-state';
import { OdooQuery } from './odoo-queries';

const mockQuery: OdooQuery = {
  id: 1, name: 'sales', description: 'Sales data', model: 'sale.order',
  method: 'search_read', domain: [], fields: ['name', 'amount'], limit_val: 50,
  active: true, created_at: '', category: { id: 2, name: 'Finance' },
};

describe('QueryEditStateService', () => {
  let svc: QueryEditStateService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), QueryEditStateService],
    });
    svc = TestBed.inject(QueryEditStateService);
  });

  it('beginEdit sets the query and state is readable', () => {
    svc.beginEdit(mockQuery);
    expect(svc.state().query).toEqual(mockQuery);
  });

  it('beginEdit replaces prior state on second call', () => {
    svc.beginEdit(mockQuery);
    const q2 = { ...mockQuery, name: 'other' };
    svc.beginEdit(q2 as OdooQuery);
    expect(svc.state().query?.name).toBe('other');
  });

  it('clear resets state to null', () => {
    svc.beginEdit(mockQuery);
    svc.clear();
    expect(svc.state().query).toBeNull();
  });
});
