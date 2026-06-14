import { Component, inject, OnInit, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { OdooQueriesService, OdooQuery } from '../../services/odoo-queries';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { SkeletonModule } from 'primeng/skeleton';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-query-list',
  imports: [TableModule, ButtonModule, TagModule, SkeletonModule],
  templateUrl: './query-list.html',
  styleUrl: './query-list.css',
})
export class QueryList implements OnInit {
  private svc = inject(OdooQueriesService);
  private msg = inject(MessageService);

  queries = signal<OdooQuery[]>([]);
  loading = signal(true);

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list().pipe(finalize(() => this.loading.set(false))).subscribe({
      next: (data) => this.queries.set(data),
      error: () => this.msg.add({ severity: 'error', summary: 'Error', detail: 'No se pudieron cargar los queries' }),
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
}
