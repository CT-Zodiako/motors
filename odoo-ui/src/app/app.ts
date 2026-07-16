import { Component, signal } from '@angular/core';
import { QueryList } from './pages/query-list/query-list';
import { QueryCreate } from './pages/query-create/query-create';
import { QueryRunner } from './pages/query-runner/query-runner';
import { ScheduleManager } from './pages/schedule-manager/schedule-manager';
import { FileUpload } from './pages/file-upload/file-upload';
import { ToastModule } from 'primeng/toast';

type Tab = 'list' | 'create' | 'runner' | 'schedules' | 'upload';

interface NavItem { id: Tab; label: string; icon: string; }
interface NavGroup { label: string; items: NavItem[]; }

@Component({
  selector: 'app-root',
  imports: [QueryList, QueryCreate, QueryRunner, ScheduleManager, FileUpload, ToastModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  activeTab = signal<Tab>('list');

  navGroups: NavGroup[] = [
    {
      label: 'Consultar',
      items: [
        { id: 'list', label: 'Queries', icon: 'pi-database' },
        { id: 'runner', label: 'Ejecutar', icon: 'pi-play-circle' },
        { id: 'schedules', label: 'Programar', icon: 'pi-calendar-clock' },
      ]
    },
    {
      label: 'Cargar datos',
      items: [
        { id: 'create', label: 'Nuevo Query', icon: 'pi-plus-circle' },
        { id: 'upload', label: 'Cargar archivo', icon: 'pi-upload' },
      ]
    }
  ];

  setTab(tab: Tab) { this.activeTab.set(tab); }
}
