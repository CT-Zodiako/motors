import { Component, signal } from '@angular/core';
import { QueryList } from './pages/query-list/query-list';
import { QueryCreate } from './pages/query-create/query-create';
import { QueryRunner } from './pages/query-runner/query-runner';
import { ScheduleManager } from './pages/schedule-manager/schedule-manager';
import { FileUpload } from './pages/file-upload/file-upload';
import { ToastModule } from 'primeng/toast';

type Tab = 'list' | 'create' | 'runner' | 'schedules' | 'upload';

interface NavItem { id: Tab; label: string; icon: string; }

@Component({
  selector: 'app-root',
  imports: [QueryList, QueryCreate, QueryRunner, ScheduleManager, FileUpload, ToastModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  activeTab = signal<Tab>('list');

  nav: NavItem[] = [
    { id: 'list',       label: 'Queries',       icon: 'pi-database' },
    { id: 'create',     label: 'Nuevo Query',   icon: 'pi-plus-circle' },
    { id: 'runner',     label: 'Ejecutar',      icon: 'pi-play-circle' },
    { id: 'upload',     label: 'Cargar archivo', icon: 'pi-upload' },
    { id: 'schedules',  label: 'Programar',     icon: 'pi-calendar-clock' },
  ];

  setTab(tab: Tab) { this.activeTab.set(tab); }
}
