import { Component, Input } from '@angular/core';
import { TableModule } from 'primeng/table';
import { DashboardData } from '../../services/dashboards';

interface NativeColumn {
  key: string;
  label: string;
}

const COUNT_COLUMN: NativeColumn = { key: '__count', label: 'Count' };

/**
 * Shared render for the DashboardData wire format (design §4.2): group columns
 * first, then one column per aggregated field (server order), plus a trailing
 * Count column for __count. Used by the native viewer (§5.4) and the admin
 * preview (§5.5) so both can never diverge in rendering.
 */
@Component({
  selector: 'app-dashboard-data-table',
  imports: [TableModule],
  template: `
    <p-table
      [value]="data.rows"
      styleClass="p-datatable-striped p-datatable-gridlines p-datatable-sm"
    >
      <ng-template #header>
        <tr>
          @for (col of columns; track col.key) {
            <th>{{ col.label }}</th>
          }
        </tr>
      </ng-template>
      <ng-template #body let-row>
        <tr>
          @for (col of columns; track col.key) {
            <td>{{ cellText(row, col.key) }}</td>
          }
        </tr>
      </ng-template>
      <ng-template #emptymessage>
        <tr>
          <td [attr.colspan]="columns.length" class="empty-msg">No hay datos para este dashboard.</td>
        </tr>
      </ng-template>
    </p-table>
  `,
})
export class DashboardDataTable {
  @Input({ required: true }) data!: DashboardData;

  get columns(): NativeColumn[] {
    return [...this.data.columns.map((c) => ({ key: c.key, label: c.label })), COUNT_COLUMN];
  }

  /** Relational group values arrive as Odoo [id, label] pairs; render the label. */
  cellText(row: Record<string, unknown>, key: string): string {
    const value = row[key];
    if (Array.isArray(value) && value.length === 2) {
      return String(value[1] ?? '');
    }
    return value == null ? '' : String(value);
  }
}
