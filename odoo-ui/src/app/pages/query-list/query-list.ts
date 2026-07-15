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
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-query-list',
  imports: [FormsModule, TableModule, ButtonModule, TagModule, SkeletonModule, SelectModule],
  templateUrl: './query-list.html',
  styleUrl: './query-list.css',
})
export class QueryList implements OnInit {
  private svc = inject(OdooQueriesService);
  private categoriesSvc = inject(CategoriesService);
  private msg = inject(MessageService);
  private editState = inject(QueryEditStateService);

  @Input() onNavigateToTab: ((tab: 'list' | 'create' | 'runner' | 'bigquery' | 'schedules' | 'upload') => void) | null = null;

  queries = signal<OdooQuery[]>([]);
  categories = signal<QueryCategory[]>([]);
  loading = signal(true);

  // query-categories change: rows grouped by category (alphabetical), then by name
  sortedQueries = computed(() => sortByCategoryThenName(this.queries()));

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

  onCategoryChange(q: OdooQuery, categoryId: number) {
    this.svc.updateCategory(q.name, categoryId).subscribe({
      next: (updated) => {
        this.queries.update((rows) => rows.map((r) => (r.name === q.name ? updated : r)));
        this.msg.add({ severity: 'success', summary: 'Categoría actualizada', detail: `"${q.name}" → ${updated.category?.name}` });
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudo cambiar la categoría' });
      },
    });
  }

  deactivate(name: string) {
    this.svc.deactivate(name).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Listo', detail: `Query "${name}" desactivado` });
        this.load();
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
