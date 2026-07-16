import { Component, inject, OnInit, computed, signal, Input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { OdooQueriesService, OdooQuery } from '../../services/odoo-queries';
import { CategoriesService, QueryCategory } from '../../services/categories';
import { QueryEditStateService } from '../../services/query-edit-state';
import { sortByCategoryThenName } from '../../utils/category-groups';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { SkeletonModule } from 'primeng/skeleton';
import { SelectModule } from 'primeng/select';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-query-list',
  imports: [FormsModule, TableModule, ButtonModule, TagModule, SkeletonModule, SelectModule, ToggleSwitchModule, TooltipModule],
  templateUrl: './query-list.html',
  styleUrl: './query-list.css',
})
export class QueryList implements OnInit {
  private svc = inject(OdooQueriesService);
  private categoriesSvc = inject(CategoriesService);
  private msg = inject(MessageService);
  private editState = inject(QueryEditStateService);

  @Input() onNavigateToTab: ((tab: 'list' | 'create' | 'runner' | 'schedules' | 'upload') => void) | null = null;

  queries = signal<OdooQuery[]>([]);
  categories = signal<QueryCategory[]>([]);
  loading = signal(true);
  selectedCategoryFilter = signal<number | null>(null);

  // query-categories change: rows grouped by category (alphabetical), then by name
  sortedQueries = computed(() => sortByCategoryThenName(this.queries()));

  filteredQueries = computed(() => {
    const rows = this.sortedQueries();
    const catId = this.selectedCategoryFilter();
    if (catId === null) return rows;
    return rows.filter((q) => q.category?.id === catId || (catId === -1 && !q.category));
  });

  categoryFilterOptions = computed(() => [
    { label: 'Todas las categorías', value: null },
    { label: 'Sin categoría', value: -1 },
    ...this.categories().map((c) => ({ label: c.name, value: c.id })),
  ]);

  ngOnInit() {
    this.load();
    this.loadCategories();
  }

  load() {
    this.loading.set(true);
    this.svc.list().pipe(finalize(() => this.loading.set(false))).subscribe({
      next: (data) => this.queries.set(data),
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los queries' }),
    });
  }

  loadCategories() {
    this.categoriesSvc.list().subscribe({
      next: (cats) => this.categories.set(cats),
      error: () => {},
    });
  }

  toggleActive(q: OdooQuery, active: boolean) {
    this.svc.setActive(q.name, active).subscribe({
      next: () => {
        this.queries.update((rows) => rows.map((r) => (r.name === q.name ? { ...r, active } : r)));
        this.msg.add({
          severity: 'success',
          summary: 'Listo',
          detail: `Query "${q.name}" ${active ? 'activado' : 'desactivado'}`,
        });
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo cambiar el estado' });
      },
    });
  }

  deleteQuery(q: OdooQuery) {
    this.svc.delete(q.name).subscribe({
      next: () => {
        this.queries.update((rows) => rows.filter((r) => r.name !== q.name));
        this.msg.add({ severity: 'success', summary: 'Listo', detail: `Query "${q.name}" eliminado` });
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo eliminar el query' });
      },
    });
  }

  editQuery(q: OdooQuery) {
    this.editState.beginEdit(q);
    if (this.onNavigateToTab) {
      this.onNavigateToTab('create');
    }
  }
}
