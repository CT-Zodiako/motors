import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MessageService } from 'primeng/api';
import { QueryRunner } from './query-runner';
import { OdooQuery } from '../../services/odoo-queries';

const ROWS: OdooQuery[] = [
  { id: 1, name: 'ventas_hoy', description: '', model: 'sale.order', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Ventas' } },
  { id: 2, name: 'clientes', description: '', model: 'res.partner', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 1, name: 'Clientes' } },
  { id: 3, name: 'facturas', description: '', model: 'account.move', method: 'search_read', limit_val: 100, active: true, created_at: '', category: { id: 2, name: 'Ventas' } },
  { id: 4, name: 'inactivo', description: '', model: 'res.partner', method: 'search_read', limit_val: 100, active: false, created_at: '', category: { id: 1, name: 'Clientes' } },
];

describe('QueryRunner (query-categories)', () => {
  let http: HttpTestingController;
  let component: QueryRunner;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [QueryRunner],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
      ],
    });
    const fixture = TestBed.createComponent(QueryRunner);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('http://localhost:8000/queries/').flush(ROWS);
  });

  afterEach(() => http.verify());

  it('groups selector options by category, alphabetical, active only', () => {
    const groups = component.groupedQueries();
    expect(groups.map((g) => g.label)).toEqual(['Clientes', 'Ventas']);
    const ventas = groups.find((g) => g.label === 'Ventas')!;
    expect(ventas.items.map((q) => q.name).sort()).toEqual(['facturas', 'ventas_hoy']);
    // inactive queries are excluded from grouping
    expect(groups.flatMap((g) => g.items.map((q) => q.name))).not.toContain('inactivo');
  });
});
