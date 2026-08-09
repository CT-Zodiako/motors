import { Component, EventEmitter, OnInit, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { Dialog } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { MultiSelectModule } from 'primeng/multiselect';
import { Tag } from 'primeng/tag';
import { Tooltip } from 'primeng/tooltip';
import { ConfirmDialog } from 'primeng/confirmdialog';
import { ConfirmationService, MessageService } from 'primeng/api';
import {
  DashboardsService,
  Dashboard,
  DashboardCreate,
  DashboardData,
  DashboardDefinition,
  DashboardPatch,
} from '../../services/dashboards';
import { OdooQueriesService, FieldMeta } from '../../services/odoo-queries';
import { DashboardDataTable } from '../../components/dashboard-data-table/dashboard-data-table';

type Aggregation = 'sum' | 'avg' | 'count';
type DashboardType = 'embed' | 'native';

interface FilterRow {
  field: string;
  operator: string;
  value: string;
}

// DD2: sum/avg only on numeric Odoo field types; count on any type.
const NUMERIC_TYPES = new Set(['integer', 'float', 'monetary']);

const AGGREGATION_OPTIONS: { label: string; value: Aggregation }[] = [
  { label: 'Suma (sum)', value: 'sum' },
  { label: 'Promedio (avg)', value: 'avg' },
  { label: 'Conteo (count)', value: 'count' },
];

// Closed operator dropdown mirroring the backend DOMAIN_OPERATORS allowlist
// (design §3.7) — no free-text query input anywhere in this form.
const OPERATOR_OPTIONS = ['=', '!=', '>', '>=', '<', '<=', 'in', 'not in', 'like', 'ilike', 'child_of', 'parent_of'].map(
  (op) => ({ label: op, value: op }),
);

@Component({
  selector: 'app-dashboard-admin',
  imports: [
    FormsModule,
    TableModule,
    ButtonModule,
    Dialog,
    InputTextModule,
    SelectModule,
    MultiSelectModule,
    Tag,
    Tooltip,
    ConfirmDialog,
    DashboardDataTable,
  ],
  providers: [ConfirmationService],
  templateUrl: './dashboard-admin.html',
  styleUrl: './dashboard-admin.css',
})
export class DashboardAdmin implements OnInit {
  private svc = inject(DashboardsService);
  private odoo = inject(OdooQueriesService);
  private msg = inject(MessageService);
  private confirmation = inject(ConfirmationService);

  /** Emitted after every mutation so the parent refreshes the dynamic menu. */
  @Output() dashboardsChanged = new EventEmitter<void>();

  dashboards = signal<Dashboard[]>([]);
  loading = signal(false);
  saving = signal(false);

  dialogVisible = signal(false);
  isEditing = signal(false);
  editingKey = signal<string | null>(null);
  dialogTitle = computed(() => (this.isEditing() ? 'Editar dashboard' : 'Nuevo dashboard'));

  formName = signal('');
  formMenuKey = signal('');
  formType = signal<DashboardType>('embed');
  formEmbedUrl = signal('');
  formError = signal<string | null>(null);

  typeOptions = [
    { label: 'Embed (URL externa)', value: 'embed' as DashboardType },
    { label: 'Nativo (datos de Odoo)', value: 'native' as DashboardType },
  ];

  allModels = signal<{ name: string; model: string }[]>([]);
  private modelsRequested = false;
  modelOptions = computed(() => this.allModels().map((m) => ({ label: `${m.name} (${m.model})`, value: m.model })));

  selectedModel = signal<string | null>(null);
  availableFields = signal<FieldMeta[]>([]);
  loadingFields = signal(false);
  selectedFields = signal<string[]>([]);
  aggregations = signal<Record<string, Aggregation>>({});
  groupBy = signal<string[]>([]);
  filters = signal<FilterRow[]>([]);
  staleFields = signal<string[]>([]);

  previewData = signal<DashboardData | null>(null);
  previewLoading = signal(false);
  previewError = signal<string | null>(null);

  operatorOptions = OPERATOR_OPTIONS;

  fieldMap = computed(() => {
    const map = new Map<string, FieldMeta>();
    for (const f of this.availableFields()) map.set(f.key, f);
    return map;
  });

  fieldOptions = computed(() => this.availableFields().map((f) => ({ label: `${f.string} (${f.key})`, value: f.key })));

  canPreview = computed(() => this.formType() === 'native' && !!this.selectedModel() && this.selectedFields().length > 0);

  ngOnInit() {
    this.loadList();
  }

  loadList() {
    this.loading.set(true);
    this.svc.list().subscribe({
      next: (rows) => {
        this.dashboards.set(rows);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los dashboards' });
      },
    });
  }

  private ensureModels() {
    if (this.modelsRequested) return;
    this.modelsRequested = true;
    this.odoo.getAllModels().subscribe({
      next: (res) => this.allModels.set(res.models.sort((a, b) => a.name.localeCompare(b.name))),
      error: () => {
        this.modelsRequested = false;
      },
    });
  }

  openCreate() {
    this.isEditing.set(false);
    this.editingKey.set(null);
    this.formName.set('');
    this.formMenuKey.set('');
    this.formType.set('embed');
    this.formEmbedUrl.set('');
    this.formError.set(null);
    this.resetNativeForm();
    this.dialogVisible.set(true);
    this.ensureModels();
  }

  openEdit(d: Dashboard) {
    this.isEditing.set(true);
    this.editingKey.set(d.menu_key);
    this.formName.set(d.name);
    this.formMenuKey.set(d.menu_key);
    this.formEmbedUrl.set(d.embed_url ?? '');
    this.formError.set(null);
    this.resetNativeForm();
    if (d.definition) {
      this.formType.set('native');
      const def = d.definition;
      this.selectedModel.set(def.model);
      this.selectedFields.set([...def.fields]);
      this.aggregations.set({ ...def.aggregations });
      this.groupBy.set([...def.group_by]);
      this.filters.set(this.parseDomain(def.domain));
      // Stale-metadata strategy (design §5.5): fetch fresh fields_get and mark
      // stored fields/groupings missing from the response as stale in the UI.
      this.loadFields(def.model, def);
    } else {
      this.formType.set('embed');
    }
    this.dialogVisible.set(true);
    this.ensureModels();
  }

  private resetNativeForm() {
    this.selectedModel.set(null);
    this.availableFields.set([]);
    this.selectedFields.set([]);
    this.aggregations.set({});
    this.groupBy.set([]);
    this.filters.set([]);
    this.staleFields.set([]);
    this.previewData.set(null);
    this.previewError.set(null);
  }

  private parseDomain(domain: unknown[]): FilterRow[] {
    if (!Array.isArray(domain)) return [];
    return domain
      .filter((item): item is [unknown, unknown, unknown] => Array.isArray(item) && item.length === 3)
      .map(([field, operator, value]) => ({ field: String(field), operator: String(operator), value: String(value ?? '') }));
  }

  private loadFields(model: string, stored?: DashboardDefinition) {
    this.loadingFields.set(true);
    this.odoo.getFields(model).subscribe({
      next: (res) => {
        const fields: FieldMeta[] = Object.entries(res.fields)
          .map(([key, meta]) => ({ key, ...meta }))
          .filter((f) => f.key !== 'id')
          .sort((a, b) => a.string.localeCompare(b.string));
        this.availableFields.set(fields);
        this.loadingFields.set(false);
        if (stored) {
          const known = new Set(fields.map((f) => f.key));
          const stale = [...stored.fields, ...stored.group_by].filter((k) => !known.has(k));
          this.staleFields.set([...new Set(stale)]);
        }
      },
      error: () => {
        this.loadingFields.set(false);
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los campos del modelo' });
      },
    });
  }

  onModelChange(model: string | null) {
    this.selectedModel.set(model);
    this.availableFields.set([]);
    this.selectedFields.set([]);
    this.aggregations.set({});
    this.groupBy.set([]);
    this.filters.set([]);
    this.staleFields.set([]);
    this.previewData.set(null);
    this.previewError.set(null);
    if (model) this.loadFields(model);
  }

  onFieldsChange(keys: string[]) {
    this.selectedFields.set(keys);
    this.aggregations.update((aggs) => {
      const next: Record<string, Aggregation> = {};
      for (const key of keys) {
        next[key] = this.normalizeAggregation(key, aggs[key]);
      }
      return next;
    });
    this.previewData.set(null);
  }

  private normalizeAggregation(field: string, agg: Aggregation | undefined): Aggregation {
    if (agg && this.aggregationAllowed(field, agg)) return agg;
    return NUMERIC_TYPES.has(this.fieldMap().get(field)?.type ?? '') ? 'sum' : 'count';
  }

  aggregationAllowed(field: string, agg: Aggregation): boolean {
    if (agg === 'count') return true;
    return NUMERIC_TYPES.has(this.fieldMap().get(field)?.type ?? '');
  }

  /** Per-field aggregation dropdown filtered by DD2 applicability. */
  aggregationOptionsFor(field: string) {
    return AGGREGATION_OPTIONS.filter((o) => this.aggregationAllowed(field, o.value));
  }

  setAggregation(field: string, agg: Aggregation) {
    this.aggregations.update((a) => ({ ...a, [field]: agg }));
  }

  addFilter() {
    const first = this.availableFields()[0];
    this.filters.update((rows) => [...rows, { field: first?.key ?? '', operator: '=', value: '' }]);
  }

  removeFilter(i: number) {
    this.filters.update((rows) => rows.filter((_, idx) => idx !== i));
  }

  updateFilter(i: number, patch: Partial<FilterRow>) {
    this.filters.update((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  buildDomain(): unknown[] {
    return this.filters()
      .filter((f) => f.field && f.value !== '')
      .map((f) => [f.field, f.operator, f.value]);
  }

  buildDefinition(): DashboardDefinition | null {
    const model = this.selectedModel();
    if (!model || this.selectedFields().length === 0) return null;
    return {
      model,
      fields: [...this.selectedFields()],
      group_by: [...this.groupBy()],
      domain: this.buildDomain(),
      aggregations: { ...this.aggregations() },
    };
  }

  previewDashboard() {
    const def = this.buildDefinition();
    if (!def) return;
    this.previewLoading.set(true);
    this.previewError.set(null);
    this.previewData.set(null);
    this.svc.preview(def).subscribe({
      next: (data) => {
        this.previewData.set(data);
        this.previewLoading.set(false);
      },
      error: (err) => {
        this.previewLoading.set(false);
        this.previewError.set(this.errorMessage(err));
      },
    });
  }

  save() {
    this.formError.set(null);
    const name = this.formName().trim();
    const menuKey = this.formMenuKey().trim();
    if (!name || !menuKey) {
      this.formError.set('Nombre y clave de menú son obligatorios');
      return;
    }

    const isEmbed = this.formType() === 'embed';
    if (isEmbed && !this.formEmbedUrl().trim()) {
      this.formError.set('La URL de embed es obligatoria');
      return;
    }
    const definition = isEmbed ? null : this.buildDefinition();
    if (!isEmbed && !definition) {
      this.formError.set('Seleccioná un modelo y al menos un campo');
      return;
    }

    this.saving.set(true);
    if (this.isEditing()) {
      const key = this.editingKey()!;
      // Explicit nulls clear the inactive branch so post-merge XOR re-validation
      // on the backend keeps passing on type switches (design §3.8).
      const patch: DashboardPatch = isEmbed
        ? { name, embed_url: this.formEmbedUrl().trim(), definition: null }
        : { name, embed_url: null, definition };
      if (menuKey !== key) patch.menu_key = menuKey;
      this.svc.update(key, patch).subscribe({
        next: () => this.finishMutation('Dashboard actualizado'),
        error: (err) => this.failSave(err),
      });
    } else {
      const body: DashboardCreate = isEmbed
        ? { menu_key: menuKey, name, embed_url: this.formEmbedUrl().trim() }
        : { menu_key: menuKey, name, definition };
      this.svc.create(body).subscribe({
        next: () => this.finishMutation('Dashboard creado'),
        error: (err) => this.failSave(err),
      });
    }
  }

  private failSave(err: HttpErrorResponse) {
    this.saving.set(false);
    // Inline 422 surfacing (design §5.5): show the backend message in the form.
    this.formError.set(this.errorMessage(err));
  }

  private finishMutation(detail: string) {
    this.saving.set(false);
    this.dialogVisible.set(false);
    this.msg.add({ severity: 'success', summary: 'Listo', detail });
    this.loadList();
    this.dashboardsChanged.emit();
  }

  toggleActive(d: Dashboard) {
    this.svc.update(d.menu_key, { active: !d.active }).subscribe({
      next: () => {
        this.msg.add({
          severity: 'success',
          summary: 'Listo',
          detail: d.active ? `Dashboard "${d.name}" despublicado` : `Dashboard "${d.name}" publicado`,
        });
        this.loadList();
        this.dashboardsChanged.emit();
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo cambiar el estado' }),
    });
  }

  askDelete(d: Dashboard) {
    this.confirmation.confirm({
      header: 'Eliminar dashboard',
      message: `¿Eliminar el dashboard "${d.name}"? Esta acción no se puede deshacer.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Eliminar',
      rejectLabel: 'Cancelar',
      accept: () => this.deleteDashboard(d),
    });
  }

  private deleteDashboard(d: Dashboard) {
    this.svc.delete(d.menu_key).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Listo', detail: `Dashboard "${d.name}" eliminado` });
        this.loadList();
        this.dashboardsChanged.emit();
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo eliminar el dashboard' }),
    });
  }

  private errorMessage(err: HttpErrorResponse): string {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message;
    if (err.status === 409) return 'Ya existe un dashboard con esa clave de menú';
    return 'No se pudo guardar el dashboard';
  }
}
