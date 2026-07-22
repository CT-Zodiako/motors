import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { HttpErrorResponse } from '@angular/common/http';
import { DashboardsService } from '../../services/dashboards';

@Component({
  selector: 'app-dashboard-viewer',
  imports: [],
  templateUrl: './dashboard-viewer.html',
  styleUrl: './dashboard-viewer.css',
})
export class DashboardViewer implements OnInit {
  @Input() menuKey = 'dashboards';

  private dashboards = inject(DashboardsService);
  private sanitizer = inject(DomSanitizer);

  loading = signal(true);
  notFound = signal(false);
  error = signal(false);
  name = signal<string | null>(null);
  embedUrl = signal<SafeResourceUrl | null>(null);

  ngOnInit() {
    this.dashboards.getByMenuKey(this.menuKey).subscribe({
      next: (dashboard) => {
        this.name.set(dashboard.name);
        this.embedUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(dashboard.embed_url));
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 404) {
          this.notFound.set(true);
        } else {
          this.error.set(true);
        }
      },
    });
  }
}
