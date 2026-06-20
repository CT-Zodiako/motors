import { Component, signal } from '@angular/core';
import { QueryList } from './pages/query-list/query-list';
import { QueryCreate } from './pages/query-create/query-create';
import { QueryRunner } from './pages/query-runner/query-runner';
import { BigQuerySync } from './pages/bigquery-sync/bigquery-sync';
import { ToastModule } from 'primeng/toast';

type Tab = 'list' | 'create' | 'runner' | 'bigquery';

interface NavItem { id: Tab; label: string; icon: string; }

@Component({
  selector: 'app-root',
  imports: [QueryList, QueryCreate, QueryRunner, BigQuerySync, ToastModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  activeTab = signal<Tab>('list');

  nav: NavItem[] = [
    { id: 'list',      label: 'Queries',       icon: 'pi-database' },
    { id: 'create',    label: 'Nuevo Query',   icon: 'pi-plus-circle' },
    { id: 'runner',    label: 'Ejecutar',      icon: 'pi-play-circle' },
    { id: 'bigquery',  label: 'BigQuery',      icon: 'pi-cloud-download' },
  ];

  setTab(tab: Tab) { this.activeTab.set(tab); }
}
