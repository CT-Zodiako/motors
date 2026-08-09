import { Component, EventEmitter, Input, Output, OnInit, inject, signal, ElementRef, ViewChild, HostListener } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { HttpErrorResponse } from '@angular/common/http';
import { DashboardsService, DashboardData } from '../../services/dashboards';
import { DashboardDataTable } from '../../components/dashboard-data-table/dashboard-data-table';

interface StaleDetail {
  code?: string;
  message?: string;
}

@Component({
  selector: 'app-dashboard-viewer',
  imports: [DashboardDataTable],
  templateUrl: './dashboard-viewer.html',
  styleUrl: './dashboard-viewer.css',
})
export class DashboardViewer implements OnInit {
  @Input() menuKey = 'dashboards';
  @Output() unavailable = new EventEmitter<void>();

  @ViewChild('dashboardContainer', { static: true }) dashboardContainer!: ElementRef<HTMLDivElement>;

  private dashboards = inject(DashboardsService);
  private sanitizer = inject(DomSanitizer);

  loading = signal(true);
  notFound = signal(false);
  unavailableMessage = signal('Este dashboard ya no está disponible.');
  error = signal(false);
  name = signal<string | null>(null);
  embedUrl = signal<SafeResourceUrl | null>(null);
  nativeData = signal<DashboardData | null>(null);
  isFullscreen = signal(false);

  ngOnInit() {
    this.dashboards.getByMenuKey(this.menuKey).subscribe({
      next: (dashboard) => {
        this.name.set(dashboard.name);
        if (dashboard.definition == null) {
          // Embed path: unchanged legacy behavior (sanitized iframe + fullscreen).
          this.embedUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(dashboard.embed_url ?? ''));
          this.loading.set(false);
        } else {
          this.loadNativeData();
        }
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

  private loadNativeData() {
    this.dashboards.getData(this.menuKey).subscribe({
      next: (data) => {
        this.nativeData.set(data);
        this.name.set(data.name);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        const detail = err.error?.detail as StaleDetail | string | undefined;
        if (err.status === 404) {
          this.notFound.set(true);
        } else if (err.status === 422 && typeof detail === 'object' && detail?.code === 'stale_definition') {
          this.unavailableMessage.set(detail.message ?? this.unavailableMessage());
          this.notFound.set(true);
        } else {
          this.error.set(true);
        }
      },
    });
  }

  @HostListener('document:fullscreenchange')
  onFullscreenChange() {
    this.isFullscreen.set(!!document.fullscreenElement);
  }

  enterFullscreen() {
    const el = this.dashboardContainer?.nativeElement;
    if (el && el.requestFullscreen) {
      el.requestFullscreen().catch((err) => {
        console.error('Error al entrar en pantalla completa:', err);
      });
    }
  }

  exitFullscreen() {
    if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch((err) => {
        console.error('Error al salir de pantalla completa:', err);
      });
    }
  }
}
