import { Component, inject, OnInit, signal } from '@angular/core';
import { filter } from 'rxjs';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  readonly api = inject(ApiService);
  private readonly router = inject(Router);

  /** Estado de visibilidad de la barra lateral (true = visible). Persistido en localStorage. */
  readonly showSidebar = signal(true);

  /** Ruta interna del catálogo (sin detalle /products/:id). */
  readonly listRoute = signal(false);
  readonly typeChip = signal('');
  readonly qChip = signal('');

  ngOnInit(): void {
    void this.api.refreshSession();
    this.syncSubnavFromUrl();
    this.router.events.pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd)).subscribe(() => {
      this.syncSubnavFromUrl();
    });
    try {
      const collapsed = localStorage.getItem('sidebarCollapsed') === '1';
      this.showSidebar.set(!collapsed);
    } catch (e) {
      // ignore (e.g. server-side rendering or restricted storage)
    }
  }

  toggleSidebar(): void {
    const next = !this.showSidebar();
    this.showSidebar.set(next);
    try {
      localStorage.setItem('sidebarCollapsed', next ? '0' : '1');
    } catch (e) {
      // ignore
    }
  }

  private syncSubnavFromUrl(): void {
    const tree = this.router.parseUrl(this.router.url);
    const path = (this.router.url.split('?')[0] || '/').replace(/\/$/, '') || '/';
    this.listRoute.set(path === '/products');
    this.typeChip.set((tree.queryParams['type'] as string) || '');
    this.qChip.set((tree.queryParams['q'] as string) || '');
  }

  /** Chips “Todo”: conserva búsqueda q si existe, quita tipo (y el resto de filtros del catálogo). */
  chipTodoQuery(): Record<string, string> {
    const q = this.qChip();
    return q ? { q } : {};
  }

  chipTypeQuery(t: 'sale' | 'exchange' | 'donation'): Record<string, string> {
    const out: Record<string, string> = { type: t };
    const q = this.qChip();
    if (q) out['q'] = q;
    return out;
  }

  chipTodoActive(): boolean {
    return this.listRoute() && !this.typeChip();
  }

  chipTypeActive(t: string): boolean {
    return this.listRoute() && this.typeChip() === t;
  }

  async logout(): Promise<void> {
    await this.api.logout();
    await this.router.navigateByUrl('/products');
  }
}
