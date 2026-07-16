import { Component, inject, signal, computed, OnInit, Input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OdooQueriesService, FieldMeta, OdooQuery } from '../../services/odoo-queries';
import { CategoriesService, QueryCategory } from '../../services/categories';
import { QueryEditStateService } from '../../services/query-edit-state';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { StepperModule } from 'primeng/stepper';
import { CardModule } from 'primeng/card';
import { TagModule } from 'primeng/tag';
import { SkeletonModule } from 'primeng/skeleton';
import { MessageService } from 'primeng/api';
import { InputNumberModule } from 'primeng/inputnumber';
import { DialogModule } from 'primeng/dialog';

export interface ModelOption {
  label: string; model: string; description: string; icon: string;
}
export interface FilterRow {
  field: string; operator: string; value: unknown;
}
export interface OperatorOption {
  value: string; label: string; forTypes: string[];
}

const PINNED: ModelOption[] = [
  { label: 'Clientes y Proveedores', model: 'res.partner',      description: 'Contactos, clientes, proveedores',   icon: '👥' },
  { label: 'Ventas',                 model: 'sale.order',       description: 'Órdenes de venta y presupuestos',    icon: '🛒' },
  { label: 'Facturas',               model: 'account.move',     description: 'Facturas emitidas y recibidas',      icon: '🧾' },
  { label: 'Productos',              model: 'product.template', description: 'Catálogo de productos',              icon: '📦' },
  { label: 'Compras',                model: 'purchase.order',   description: 'Órdenes de compra',                  icon: '🏪' },
  { label: 'Empleados',              model: 'hr.employee',      description: 'Personas de la empresa',             icon: '👤' },
  { label: 'Proyectos',              model: 'project.project',  description: 'Proyectos y tareas',                 icon: '📋' },
  { label: 'CRM / Oportunidades',    model: 'crm.lead',         description: 'Leads y oportunidades comerciales',  icon: '💼' },
];

const OPERATORS: OperatorOption[] = [
  { value: '=',         label: 'es igual a',        forTypes: ['all'] },
  { value: '!=',        label: 'es distinto de',    forTypes: ['all'] },
  { value: 'ilike',     label: 'contiene',           forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: 'not ilike', label: 'no contiene',        forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: '>',         label: 'mayor que',          forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: '>=',        label: 'mayor o igual a',   forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: '<',         label: 'menor que',          forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: '<=',        label: 'menor o igual a',   forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
];

@Component({
  selector: 'app-query-create',
  imports: [FormsModule, ButtonModule, InputTextModule, SelectModule, StepperModule, CardModule, TagModule, SkeletonModule, InputNumberModule, DialogModule],
  templateUrl: './query-create.html',
  styleUrl: './query-create.css',
})
export class QueryCreate implements OnInit {
  private svc = inject(OdooQueriesService);
  private categoriesSvc = inject(CategoriesService);
  private msg = inject(MessageService);
  private editState = inject(QueryEditStateService);

  @Input() onNavigateToTab: ((tab: 'list' | 'create' | 'runner' | 'schedules' | 'upload') => void) | null = null;

  activeStep = signal(0);

  // Edit mode state
  isEditMode = signal(false);
  editingQuery = signal<OdooQuery | null>(null);
  propagationResult = signal<any | null>(null);
  showPropagationDialog = signal(false);
  showDestructiveConfirm = signal(false);
  removedFields = signal<string[]>([]);
  originalFields = signal<string[]>([]); // snapshot for destructive confirm

  pinnedModels = PINNED;
  allModels = signal<{ name: string; model: string }[]>([]);
  loadingModels = signal(false);
  modelSearch = signal('');
  selectedModel = signal<ModelOption | null>(null);

  filteredModels = computed(() => {
    const q = this.modelSearch().toLowerCase().trim();
    if (!q) return this.allModels();
    return this.allModels().filter(m =>
      m.name.toLowerCase().includes(q) || m.model.toLowerCase().includes(q)
    );
  });

  availableFields = signal<FieldMeta[]>([]);
  loadingFields = signal(false);
  fieldsError = signal('');
  checkedFields = signal<Set<string>>(new Set());
  fieldSearch = signal('');

  filteredFields = computed(() => {
    const q = this.fieldSearch().toLowerCase().trim();
    if (!q) return this.availableFields();
    return this.availableFields().filter(f =>
      f.string.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
    );
  });

  operators = OPERATORS;
  filters = signal<FilterRow[]>([]);

  boolOptions = [
    { label: 'Sí', value: true },
    { label: 'No', value: false },
  ];

  queryName = signal('');
  saving = signal(false);

  // query-categories change
  categories = signal<QueryCategory[]>([]);
  selectedCategoryId = signal<number | null>(null);
  showNewCategory = signal(false);
  newCategoryName = signal('');
  creatingCategory = signal(false);
  limitVal = signal<number | null>(null);

  fieldMap = computed(() => {
    const map = new Map<string, FieldMeta>();
    this.availableFields().forEach(f => map.set(f.key, f));
    return map;
  });

  checkedFieldsList = computed(() =>
    this.availableFields().filter(f => this.checkedFields().has(f.key))
  );

  allFieldsChecked = computed(() =>
    this.availableFields().length > 0 &&
    this.availableFields().every(f => this.checkedFields().has(f.key))
  );

  getFieldType(key: string): string {
    return this.fieldMap().get(key)?.type ?? 'char';
  }

  valueInputKind(f: FilterRow): 'bool' | 'number' | 'date' | 'datetime' | 'text' {
    if (f.operator === 'ilike' || f.operator === 'not ilike') return 'text';
    const type = this.getFieldType(f.field);
    if (type === 'boolean') return 'bool';
    if (['integer', 'float', 'monetary'].includes(type)) return 'number';
    if (type === 'date') return 'date';
    if (type === 'datetime') return 'datetime';
    return 'text';
  }

  defaultOperatorFor(fieldKey: string): string {
    const type = this.getFieldType(fieldKey);
    if (['char', 'text', 'html', 'many2one'].includes(type)) return 'ilike';
    return '=';
  }

  onFieldChange(i: number, fieldKey: string) {
    this.updateFilter(i, { field: fieldKey, operator: this.defaultOperatorFor(fieldKey), value: '' });
  }

  onOperatorChange(i: number, op: string) {
    this.updateFilter(i, { operator: op, value: '' });
  }

  operatorsFor(fieldKey: string): OperatorOption[] {
    const f = this.fieldMap().get(fieldKey);
    if (!f) return this.operators;
    return this.operators.filter(op =>
      op.forTypes.includes('all') || op.forTypes.includes(f.type)
    );
  }

  ngOnInit() {
    // Check if we're in edit mode
    const editQuery = this.editState.state().query;
    if (editQuery) {
      this.isEditMode.set(true);
      this.editingQuery.set(editQuery);
      this.loadQueryForEdit(editQuery);
    }

    this.loadingModels.set(true);
    this.svc.getAllModels().subscribe({
      next: (res) => {
        this.allModels.set(res.models.sort((a, b) => a.name.localeCompare(b.name)));
        this.loadingModels.set(false);
      },
      error: () => this.loadingModels.set(false),
    });
    this.categoriesSvc.list().subscribe({
      next: (cats) => {
        this.categories.set(cats);
        const general = cats.find((c) => c.name === 'General') ?? cats[0];
        if (general && this.selectedCategoryId() === null) {
          this.selectedCategoryId.set(general.id);
        }
      },
      error: () => {},
    });
  }

  private loadQueryForEdit(q: OdooQuery) {
    // Pre-fill the wizard with existing query data
    this.queryName.set(q.name);
    this.limitVal.set(q.limit_val > 0 ? q.limit_val : null);
    this.selectedCategoryId.set(q.category?.id ?? null);

    // Snapshot original fields for destructive confirmation
    this.originalFields.set(q.fields ?? []);

    // Load fields for the model
    const modelOpt = PINNED.find(p => p.model === q.model) || {
      label: q.model, model: q.model, description: q.model, icon: '🗂️'
    };
    this.selectedModel.set(modelOpt);

    this.svc.getFields(q.model).subscribe({
      next: (res) => {
        const fields: FieldMeta[] = Object.entries(res.fields)
          .map(([key, meta]) => ({ key, ...meta }))
          .filter(f => f.key !== 'id')
          .sort((a, b) => a.string.localeCompare(b.string));
        this.availableFields.set(fields);
        // Pre-check fields from the saved query
        this.checkedFields.set(new Set(q.fields ?? []));
        // Restore filters from domain (inverse of buildDomain)
        this.filters.set(this.parseDomain(q.domain ?? []));
        this.loadingFields.set(false);
        // Start directly on the fields step in edit mode; model is immutable.
        this.activeStep.set(1);
      },
      error: () => {
        this.fieldsError.set('No se pudieron cargar los campos.');
        this.loadingFields.set(false);
      },
    });
  }

  private parseDomain(domain: unknown[]): FilterRow[] {
    if (!Array.isArray(domain)) return [];
    return domain
      .filter((item): item is [unknown, unknown, unknown] => Array.isArray(item) && item.length === 3)
      .map(([field, operator, value]) => ({ field: String(field), operator: String(operator), value } as FilterRow));
  }

  confirmNewCategory() {
    const name = this.newCategoryName().trim();
    if (!name || this.creatingCategory()) return;
    this.creatingCategory.set(true);
    this.categoriesSvc.create(name).subscribe({
      next: (cat) => {
        this.categories.update((cs) => [...cs, cat]);
        this.selectedCategoryId.set(cat.id);
        this.newCategoryName.set('');
        this.showNewCategory.set(false);
        this.creatingCategory.set(false);
        this.msg.add({ severity: 'success', summary: 'Categoría creada', detail: `"${cat.name}" lista para usar` });
      },
      error: (err) => {
        this.creatingCategory.set(false);
        const detail = err?.error?.detail ?? 'No se pudo crear la categoría';
        this.msg.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  selectModel(opt: ModelOption | { name: string; model: string }) {
    if (this.isEditMode()) return; // model is immutable in edit mode (spec req 6)
    const m: ModelOption = 'icon' in opt
      ? opt as ModelOption
      : { label: opt.name, model: opt.model, description: opt.model, icon: '🗂️' };

    this.selectedModel.set(m);
    this.availableFields.set([]);
    this.checkedFields.set(new Set());
    this.filters.set([]);
    this.fieldsError.set('');
    this.fieldSearch.set('');
    this.loadingFields.set(true);
    this.activeStep.set(1);

    this.svc.getFields(m.model).subscribe({
      next: (res) => {
        const fields: FieldMeta[] = Object.entries(res.fields)
          .map(([key, meta]) => ({ key, ...meta }))
          .filter(f => f.key !== 'id')
          .sort((a, b) => a.string.localeCompare(b.string));
        this.availableFields.set(fields);
        this.loadingFields.set(false);
      },
      error: () => {
        this.fieldsError.set('No se pudieron cargar los campos.');
        this.loadingFields.set(false);
      },
    });
  }

  toggleField(key: string) {
    const next = new Set(this.checkedFields());
    next.has(key) ? next.delete(key) : next.add(key);
    this.checkedFields.set(next);
  }

  toggleAllFields() {
    const all = this.availableFields().map(f => f.key);
    const next = new Set(this.checkedFields());
    if (this.allFieldsChecked()) { all.forEach(k => next.delete(k)); }
    else { all.forEach(k => next.add(k)); }
    this.checkedFields.set(next);
  }

  isFieldChecked(key: string) { return this.checkedFields().has(key); }

  addFilter() {
    const first = this.availableFields()[0];
    const op = first ? this.defaultOperatorFor(first.key) : '=';
    this.filters.update(f => [...f, { field: first?.key ?? '', operator: op, value: '' }]);
  }

  removeFilter(i: number) {
    this.filters.update(f => f.filter((_, idx) => idx !== i));
  }

  updateFilter(i: number, patch: Partial<FilterRow>) {
    this.filters.update(rows => rows.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  }

  buildDomain(): unknown[] {
    return this.filters()
      .filter(f => f.field && f.value !== '' && f.value !== null && f.value !== undefined)
      .map(f => {
        let val = f.value;
        if (typeof val === 'string' && val.includes('T') && this.getFieldType(f.field) === 'datetime') {
          val = val.replace('T', ' ') + ':00';
        }
        return [f.field, f.operator, val];
      });
  }

  autoName(): string {
    const m = this.selectedModel();
    if (!m) return '';
    return m.label.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  }

  goTo(s: number) {
    if (s === 3 && !this.queryName()) this.queryName.set(this.autoName());
    this.activeStep.set(s);
  }

  save() {
    if (this.isEditMode()) {
      this.saveEdit();
      return;
    }

    const model = this.selectedModel();
    if (!model) return;
    this.saving.set(true);

    this.svc.create({
      name: this.queryName(),
      description: `${model.label}${this.filters().length ? ' (filtrado)' : ''}`,
      model: model.model,
      method: 'search_read',
      domain: this.buildDomain(),
      fields: this.checkedFieldsList().map(f => f.key),
      limit_val: this.limitVal() ?? 0,
      category_id: this.selectedCategoryId() ?? undefined,
    }).subscribe({
      next: (res) => {
        this.msg.add({ severity: 'success', summary: '¡Listo!', detail: `Query "${res.registered}" creado correctamente` });
        this.saving.set(false);
        this.reset();
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo guardar. Verificá que el nombre no esté repetido.' });
        this.saving.set(false);
      },
    });
  }

  private saveEdit() {
    const q = this.editingQuery();
    if (!q) return;

    const currentFields = this.checkedFieldsList().map(f => f.key);
    const removed = this.originalFields().filter(f => !currentFields.includes(f));
    if (removed.length > 0) {
      this.removedFields.set(removed);
      this.showDestructiveConfirm.set(true);
      return;
    }

    this._doSaveEdit();
  }

  private _doSaveEdit() {
    const q = this.editingQuery();
    if (!q) return;

    this.saving.set(true);
    const payload: any = {
      description: q.description, // preserve original description (wizard has no description editor)
      domain: this.buildDomain(),
      fields: this.checkedFieldsList().map(f => f.key),
      limit_val: this.limitVal() ?? 0,
      category_id: this.selectedCategoryId() ?? undefined,
    };

    this.svc.update(q.name, payload).subscribe({
      next: (res) => {
        this.propagationResult.set(res.propagation);
        this.showPropagationDialog.set(true);
        this.msg.add({ severity: 'success', summary: '¡Listo!', detail: `Query "${q.name}" actualizado` });
        this.saving.set(false);
        this.editState.clear();
        this.isEditMode.set(false);
        this.editingQuery.set(null);
        this.originalFields.set([]);
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail || 'No se pudo actualizar' });
        this.saving.set(false);
      },
    });
  }

  confirmDestructiveSave() {
    this.showDestructiveConfirm.set(false);
    this._doSaveEdit();
  }

  private reset() {
    this.activeStep.set(0);
    this.selectedModel.set(null);
    this.availableFields.set([]);
    this.checkedFields.set(new Set());
    this.filters.set([]);
    this.queryName.set('');
    this.modelSearch.set('');
    this.fieldSearch.set('');
    this.limitVal.set(null);
  }
}
