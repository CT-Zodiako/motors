import { Component, inject, signal, computed, OnInit, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
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
  negated?: boolean;
  id?: number;
}
export interface FilterGroup {
  type: 'group'; id: number; connector: 'and' | 'or'; negated: boolean;
  children: Array<FilterRow | FilterGroup>;
}
export type FilterNode = FilterRow | FilterGroup;
export interface OperatorOption {
  value: string; label: string; help: string; forTypes: string[];
}
export interface FilterGuideItem {
  title: string;
  description: string;
  examples?: string[];
}
export interface FilterGuideSection {
  title: string;
  introduction: string;
  items: FilterGuideItem[];
}

const RELATIONAL_FIELD_TYPES = ['many2one', 'many2many', 'one2many'];

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
  { value: '=', label: 'es igual a', help: 'Valor exacto. Ej.: = 100', forTypes: ['all'] },
  { value: '!=', label: 'es distinto de', help: 'Excluye el valor exacto. Ej.: != borrador', forTypes: ['all'] },
  { value: '=?', label: 'igual (si definido)', help: 'Compara solo si no está vacío. Ej.: =? 3', forTypes: ['all'] },
  { value: '=like', label: 'coincide exactamente (sensible)', help: 'Texto sensible sin comodines implícitos. Ej.: =like ACME', forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: 'like', label: 'coincide (sensible)', help: 'Texto sensible a mayúsculas. Ej.: like ACME', forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: 'not like', label: 'no coincide (sensible)', help: 'Excluye una coincidencia. Ej.: not like test', forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: '=ilike', label: 'coincide exactamente', help: 'Texto sin distinguir mayúsculas y sin comodines implícitos. Ej.: =ilike acme', forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: 'ilike', label: 'contiene', help: 'Texto sin distinguir mayúsculas. Ej.: ilike acme', forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: 'not ilike', label: 'no contiene', help: 'Excluye texto sin distinguir mayúsculas. Ej.: not ilike test', forTypes: ['char', 'text', 'html', 'many2one'] },
  { value: '>', label: 'mayor que', help: 'Mayor que el valor. Ej.: > 100', forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: '>=', label: 'mayor o igual a', help: 'Mayor o igual. Ej.: >= 100', forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: '<', label: 'menor que', help: 'Menor que el valor. Ej.: < 100', forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: '<=', label: 'menor o igual a', help: 'Menor o igual. Ej.: <= 100', forTypes: ['integer', 'float', 'monetary', 'date', 'datetime'] },
  { value: 'in', label: 'está en la lista', help: 'Lista separada por comas. Ej.: in 1, 2, 3', forTypes: ['all'] },
  { value: 'not in', label: 'no está en la lista', help: 'Excluye una lista. Ej.: not in 1, 2, 3', forTypes: ['all'] },
  { value: 'child_of', label: 'es hijo de', help: 'ID o IDs padre. Ej.: child_of 7', forTypes: ['many2one', 'integer'] },
  { value: 'parent_of', label: 'es padre de', help: 'ID o IDs hijo. Ej.: parent_of 7', forTypes: ['many2one', 'integer'] },
];

const FILTER_GUIDE_SECTIONS: FilterGuideSection[] = [
  {
    title: '1. Elegí los campos antes de filtrar',
    introduction: 'En el paso Campos marcá los campos que querés devolver. El paso Filtros solo ofrece esos campos: si un filtro guardado usa un campo que ya no está seleccionado, primero volvé a seleccionarlo para poder editarlo.',
    items: [{ title: 'Campos disponibles', description: 'Seleccionar un campo lo hace disponible para las condiciones y también define las columnas del resultado. Podés buscar por nombre o por clave técnica.' }],
  },
  {
    title: '2. Operadores de comparación',
    introduction: 'Se aplican a números, fechas, horas y, cuando corresponde, otros valores. El valor debe respetar el tipo del campo.',
    items: [
      { title: '= — igual a', description: 'Coincidencia exacta.', examples: ['amount_total = 100'] },
      { title: '!= — distinto de', description: 'Excluye la coincidencia exacta.', examples: ['state != cancel'] },
      { title: '=? — igual si está definido', description: 'Compara con = cuando el valor está definido; un valor vacío no agrega una restricción útil. Es práctico para filtros opcionales.', examples: ['partner_id =? 45'] },
      { title: '> y >= — mayor / mayor o igual', description: 'Comparan valores numéricos, fechas o fechas-hora.', examples: ['amount_total > 1000', 'date_order >= 2024-01-01'] },
      { title: '< y <= — menor / menor o igual', description: 'Comparan valores numéricos, fechas o fechas-hora.', examples: ['amount_total < 500', 'date_order <= 2024-12-31'] },
    ],
  },
  {
    title: '3. Texto y patrones',
    introduction: 'Estos operadores se usan en campos de texto y relaciones que se buscan por nombre. % representa cualquier cantidad de caracteres y _ representa exactamente un carácter; podés escribirlos explícitamente.',
    items: [
      { title: '=like — coincidencia exacta sensible a mayúsculas', description: 'Usa LIKE sin comodines implícitos: ACME no equivale a %ACME%. Agregá % o _ si necesitás un patrón.', examples: ['name =like ACME', 'name =like ACME%'] },
      { title: 'like — contiene, sensible a mayúsculas', description: 'Odoo agrega comodines implícitos y se comporta como una búsqueda de contenido. También interpreta % y _ como comodines.', examples: ['name like acme → contiene acme'] },
      { title: 'not like — no contiene, sensible a mayúsculas', description: 'Excluye el patrón de like; sin comodines escritos se comporta como “no contiene” en Odoo.', examples: ['name not like test'] },
      { title: '=ilike — coincidencia exacta sin distinguir mayúsculas', description: 'Es la variante insensible a mayúsculas de =like y no agrega comodines implícitos.', examples: ['name =ilike acme', 'name =ilike ACME%'] },
      { title: 'ilike — contiene, sin distinguir mayúsculas', description: 'Odoo agrega comodines implícitos: es la búsqueda “contiene” recomendada para texto. % y _ siguen siendo comodines.', examples: ['name ilike acme → contiene Acme, ACME o acme'] },
      { title: 'not ilike — no contiene, sin distinguir mayúsculas', description: 'Excluye la búsqueda contiene de ilike.', examples: ['name not ilike test'] },
    ],
  },
  {
    title: '4. Listas y jerarquías',
    introduction: 'Escribí valores separados por comas; la interfaz los serializa como una lista. Se aceptan IDs numéricos o valores de texto cuando Odoo los admite.',
    items: [
      { title: 'in — está en', description: 'Coincide con cualquiera de los valores de la lista. Es útil en campos escalares, relaciones e IDs.', examples: ['id in 1, 2, 3'] },
      { title: 'not in — no está en', description: 'Excluye todos los valores indicados.', examples: ['state not in draft, cancel'] },
      { title: 'child_of — descendiente de', description: 'Busca registros descendientes de uno o varios IDs (incluye el registro de referencia según la semántica de Odoo). Se usa principalmente en relaciones jerárquicas, como categorías, departamentos o ubicaciones.', examples: ['categ_id child_of 7', 'categ_id child_of 7, 9'] },
      { title: 'parent_of — antecesor de', description: 'Busca registros que son antecesores de uno o varios IDs. Se usa en relaciones con jerarquía.', examples: ['parent_id parent_of 45'] },
    ],
  },
  {
    title: '5. Grupos AND, OR y NOT',
    introduction: 'Cada grupo combina sus condiciones con Y (AND) u O (OR). Podés negar una condición o un grupo completo para construir expresiones claras.',
    items: [
      { title: 'AND (Y)', description: 'Deben cumplirse todas las condiciones del grupo.', examples: ['(state = sale) AND (amount_total > 1000)'] },
      { title: 'OR (O) y grupos anidados', description: 'Al combinar grupos, construí exactamente la precedencia que necesitás.', examples: ['(name ilike acme OR email ilike acme) AND active = true'] },
      { title: 'NOT (no)', description: 'Invierte una condición o un grupo. Para registros sin relación, usá el booleano false con el operador correspondiente, no el texto “false”.', examples: ['product_id = false', 'NOT (state = cancel)'] },
    ],
  },
  {
    title: '6. Errores frecuentes y límites',
    introduction: 'Si una consulta devuelve resultados inesperados, revisá estos casos antes de cambiar el dominio.',
    items: [
      { title: 'Booleano false y texto “false”', description: 'En una relación, product_id = false significa que no hay producto relacionado. La palabra “false” entre comillas sería texto y no es equivalente; el editor la convierte a booleano solo para comparaciones vacías de relaciones.' },
      { title: 'Campos de relación', description: 'Las relaciones usan IDs para =, !=, =? e in, y pueden admitir búsqueda por nombre con like/ilike. child_of y parent_of solo tienen sentido en relaciones jerárquicas.' },
      { title: 'Empieza por', description: 'Como like/ilike son contiene en Odoo, para starts-with escribí el comodín explícito con igualdad de patrón: =ilike 45%.', examples: ['code =ilike 45%'] },
      { title: 'Valores vacíos', description: 'No dejes vacío un operador que requiere valor. Para ausencia de una relación usá false; =? sirve para filtros opcionales cuando el valor no está definido.' },
      { title: 'Límite y paginación', description: 'El límite de la consulta restringe los registros que devuelve. La tabla además pagina los resultados; aumentar páginas no recupera registros excluidos por el límite. Dejá el límite vacío para todos, teniendo en cuenta el costo de consultas grandes.' },
    ],
  },
];

@Component({
  selector: 'app-query-create',
  imports: [CommonModule, FormsModule, ButtonModule, InputTextModule, SelectModule, StepperModule, CardModule, TagModule, SkeletonModule, InputNumberModule, DialogModule],
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
  showFilterGuide = signal(false);
  filterGuideSections = FILTER_GUIDE_SECTIONS;
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
  filters = signal<FilterRow[]>([]); // Compatibility projection for existing callers.
  private nextNodeId = 1;
  filterTree = signal<FilterGroup>(this.newGroup());
  domainMode = signal<'and' | 'or'>('and');
  negateDomain = signal(false);
  private treeEdited = false;
  private loadedDomain: unknown[] | null = null;
  domainEdited = false;
  domainWarning = signal('');

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
    if (['in', 'not in', 'child_of', 'parent_of', 'like', 'not like', '=like', 'ilike', 'not ilike', '=ilike'].includes(f.operator)) return 'text';
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

  isRelationalField(fieldKey: string): boolean {
    return RELATIONAL_FIELD_TYPES.includes(this.getFieldType(fieldKey));
  }

  valuePlaceholder(row: FilterRow): string {
    if (this.isRelationalField(row.field) && ['=', '!=', '=?'].includes(row.operator)) {
      return 'ID o vacío (escribí false)...';
    }
    return row.operator === 'in' || row.operator === 'not in' || row.operator === 'child_of' || row.operator === 'parent_of'
      ? 'IDs o valores separados por comas...'
      : 'Valor...';
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
        this.loadedDomain = Array.isArray(q.domain) ? structuredClone(q.domain) : [];
        this.domainEdited = false;
        const parsed = this.parseTreeDomain(q.domain ?? []);
            this.filterTree.set(parsed ?? this.newGroup());
            this.filters.set(this.flattenFilters(this.filterTree()).map(({ id, ...row }) => row));
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

  private newGroup(connector: 'and' | 'or' = 'and'): FilterGroup { return { type: 'group', id: this.nextNodeId++, connector, negated: false, children: [] }; }

  private parseClause(raw: unknown): FilterRow | null {
    let clause = raw; let negated = false;
    if (Array.isArray(clause) && clause.length === 2 && clause[0] === '!') { negated = true; clause = clause[1]; }
    if (!Array.isArray(clause) || clause.length !== 3 || typeof clause[0] !== 'string' || typeof clause[1] !== 'string') return null;
    const value = clause[2];
    const normalized = this.getFieldType(clause[0]) === 'datetime' && typeof value === 'string' ? value.replace(' ', 'T').replace(/Z$/, '').slice(0, 16) : value;
    return { id: this.nextNodeId++, field: clause[0], operator: clause[1], value: normalized, ...(negated ? { negated: true } : {}) };
  }

  private parseExpression(tokens: unknown[], at: number): { node: FilterNode; next: number } | null {
    const token = tokens[at];
    if (token === '!') { const child = this.parseExpression(tokens, at + 1); if (!child) return null; child.node.negated = !child.node.negated; return child; }
    if (token === '&' || token === '|') {
      const left = this.parseExpression(tokens, at + 1); const right = left && this.parseExpression(tokens, left.next);
      if (!left || !right) return null;
      const group = this.newGroup(token === '|' ? 'or' : 'and'); group.children = [left.node, right.node]; return { node: group, next: right.next };
    }
    const clause = this.parseClause(token); return clause ? { node: clause, next: at + 1 } : null;
  }

  private parseTreeDomain(domain: unknown[]): FilterGroup | null {
    this.domainWarning.set('');
    if (!Array.isArray(domain) || domain.length === 0) return this.newGroup();
    // Normalize the legacy bare form ['field', '=', value] to one clause.
    if (domain.length === 3 && typeof domain[0] === 'string' && typeof domain[1] === 'string') {
      const clause = this.parseClause(domain);
      if (clause) { const group = this.newGroup(); group.children = [clause]; return group; }
    }
    if (!domain.some((x) => x === '&' || x === '|' || x === '!')) {
      const children = domain.map((x) => this.parseClause(x));
      if (children.every(Boolean)) { const group = this.newGroup(); group.children = children as FilterRow[]; return group; }
    }
    const parsed = this.parseExpression(domain, 0);
    if (parsed && parsed.next === domain.length) { if ('children' in parsed.node) return parsed.node; const group = this.newGroup(); group.children = [parsed.node]; return group; }
    this.domainWarning.set('Este dominio usa una estructura no representable visualmente. Se conservará sin cambios para evitar alterarlo.'); return null;
  }

  private parseDomain(domain: unknown[]): FilterRow[] { const tree = this.parseTreeDomain(domain); return tree ? this.flattenFilters(tree).map(({ id, ...row }) => row) : []; }
  private flattenFilters(group: FilterGroup): FilterRow[] { return group.children.flatMap(child => 'children' in child ? this.flattenFilters(child) : [child]); }

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
    this.resetFilterState();
    this.availableFields.set([]);
    this.checkedFields.set(new Set());
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

  private markTreeEdited() { this.domainEdited = true; this.treeEdited = true; }
  private updateGroup(id: number, patch: Partial<FilterGroup>) { const visit = (g: FilterGroup): FilterGroup => g.id === id ? { ...g, ...patch } : { ...g, children: g.children.map(c => 'children' in c ? visit(c) : c) }; this.filterTree.set(visit(this.filterTree())); this.filters.set(this.flattenFilters(this.filterTree())); }
  private updateGroupChildren(id: number, fn: (children: FilterNode[]) => FilterNode[]) { this.markTreeEdited(); const group = this.findGroup(this.filterTree(), id); if (group) this.updateGroup(id, { children: fn(group.children) }); }
  private findGroup(group: FilterGroup, id: number): FilterGroup | null { if (group.id === id) return group; for (const child of group.children) if ('children' in child) { const found = this.findGroup(child, id); if (found) return found; } return null; }
  private updateNode(id: number, fn: (node: FilterNode) => FilterNode) { const visit = (g: FilterGroup): FilterGroup => ({ ...g, children: g.children.map(c => 'children' in c ? visit(c) : c.id === id ? fn(c) as FilterRow : c) }); this.filterTree.set(visit(this.filterTree())); this.filters.set(this.flattenFilters(this.filterTree())); }
  addCondition(groupId = this.filterTree().id) {
        const first = this.checkedFieldsList()[0];
        if (!first) return;
        this.updateGroupChildren(groupId, children => [...children, { id: this.nextNodeId++, field: first.key, operator: this.defaultOperatorFor(first.key), value: '' }]);
      }
      isUnselectedFilterField(fieldKey: string): boolean {
        return !!fieldKey && !this.checkedFields().has(fieldKey);
      }
  addFilter() { this.addCondition(); }
  addGroup(groupId = this.filterTree().id) { const nested = this.newGroup(); this.updateGroupChildren(groupId, children => [...children, nested]); }
  addNestedGroup(groupId = this.filterTree().id) { this.addGroup(groupId); }
  removeCondition(id: number) { this.removeNode(id); }
  setGroupConnector(id: number, connector: 'and' | 'or') { this.markTreeEdited(); this.updateGroup(id, { connector }); }
  toggleGroupNegated(id: number) { const group = this.findGroup(this.filterTree(), id); if (group) { this.markTreeEdited(); this.updateGroup(id, { negated: !group.negated }); } }
  removeNode(id: number) { if (id === this.filterTree().id) return; this.markTreeEdited(); const remove = (g: FilterGroup): FilterGroup => ({ ...g, children: g.children.filter(c => c.id !== id).map(c => 'children' in c ? remove(c) : c) }); this.filterTree.set(remove(this.filterTree())); this.filters.set(this.flattenFilters(this.filterTree())); }
  removeFilter(i: number) { const row = this.filters()[i]; if (row?.id) this.removeNode(row.id); }
  updateCondition(id: number, patch: Partial<FilterRow>) { this.markTreeEdited(); this.updateNode(id, n => ({ ...n, ...patch })); }
  updateFilter(i: number, patch: Partial<FilterRow>) { const row = this.filters()[i]; if (row?.id) this.updateCondition(row.id, patch); else { this.domainEdited = true; this.filters.update(rows => rows.map((r, idx) => idx === i ? { ...r, ...patch } : r)); } }
  toggleNegated(i: number) { const row = this.filters()[i]; if (row?.id) this.updateCondition(row.id, { negated: !row.negated }); }

  private clause(row: FilterRow): unknown[] {
    let value: unknown = row.value;
    if (this.isRelationalField(row.field) && ['=', '!=', '=?'].includes(row.operator) &&
        typeof value === 'string' && value.trim().toLowerCase() === 'false') {
      value = false;
    } else if (row.operator === 'in' || row.operator === 'not in' || row.operator === 'child_of' || row.operator === 'parent_of') {
      const hierarchy = row.operator === 'child_of' || row.operator === 'parent_of';
      const scalarHierarchy = hierarchy && !Array.isArray(value) && String(value ?? '').trim() !== '';
      const values = Array.isArray(value) ? value : String(value ?? '').split(',').map(v => v.trim()).filter(Boolean);
      const numeric = (v: unknown) => /^-?\d+$/.test(String(v));
      value = scalarHierarchy ? (numeric(value) ? Number(value) : String(value).trim()) : values.map(v => numeric(v) ? Number(v) : v);
    } else if (typeof value === 'string' && value.includes('T') && this.getFieldType(row.field) === 'datetime') {
      value = value.replace('T', ' ') + ':00';
    }
    const clause: unknown[] = [row.field, row.operator, value];
    return row.negated ? ['!', clause] : clause;
  }

  private serializeNode(node: FilterNode): unknown[] {
    if (!('children' in node)) return this.clause(node);
    const children = node.children.filter(c => 'children' in c || (c.field && c.value !== '' && c.value !== null && c.value !== undefined));
    const parts = children
      .map(c => 'children' in c ? this.serializeNode(c) : [this.clause(c)])
      .filter(p => p.length);
    if (!parts.length) return [];
    const result = parts.length === 1
      ? parts[0]
      : [...Array(parts.length - 1).fill(node.connector === 'or' ? '|' : '&'), ...parts.flat()];
    return node.negated ? ['!', ...result] : result;
  }
  buildDomain(): unknown[] {
    if (this.domainWarning() && this.loadedDomain) return structuredClone(this.loadedDomain);
    if (!this.domainEdited && this.loadedDomain) return structuredClone(this.loadedDomain);
    if (this.treeEdited) {
      const serialized = this.serializeNode(this.filterTree());
      return serialized.length === 3 && !['!', '&', '|'].includes(String(serialized[0])) ? [serialized] : serialized;
    }
    const clauses = this.filters().filter(f => f.field && f.value !== '' && f.value !== null && f.value !== undefined).map(f => this.clause(f));
    if (!clauses.length) return [];
    const connector = this.domainMode() === 'or' ? '|' : '&';
    const result: unknown[] = clauses.length === 1 ? [clauses[0]] : [...Array(clauses.length - 1).fill(connector), ...clauses];
    return this.negateDomain() ? ['!', ...result] : result;
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
        this.saving.set(false);
        this.editState.clear();
        this.isEditMode.set(false);
        this.editingQuery.set(null);
        this.originalFields.set([]);
        if (res.propagation && res.propagation.total > 0) {
          this.propagationResult.set(res.propagation);
          this.showPropagationDialog.set(true);
        } else {
          this.onNavigateToTab?.('list');
        }
        this.msg.add({ severity: 'success', summary: '¡Listo!', detail: `Query "${q.name}" actualizado` });
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

  private resetFilterState() {
    this.filterTree.set(this.newGroup());
    this.filters.set([]);
    this.treeEdited = false;
    this.domainEdited = false;
    this.loadedDomain = null;
    this.domainWarning.set('');
    this.domainMode.set('and');
    this.negateDomain.set(false);
  }

  private reset() {
    this.activeStep.set(0);
    this.selectedModel.set(null);
    this.resetFilterState();
    this.availableFields.set([]);
    this.checkedFields.set(new Set());
    this.filters.set([]);
    this.queryName.set('');
    this.modelSearch.set('');
    this.fieldSearch.set('');
    this.limitVal.set(null);
  }
}
