import { Component, inject, OnInit } from '@angular/core';
import { ApiService, type AdminOverview } from '../../../services/api.service';
import { SeoService } from '../../../services/seo.service';

@Component({
  selector: 'app-admin-panel',
  templateUrl: './admin-panel.component.html',
})
export class AdminPanelComponent implements OnInit {
  readonly api = inject(ApiService);
  private readonly seo = inject(SeoService);

  data: AdminOverview | null = null;
  error: string | null = null;
  actionMsg: string | null = null;

  async ngOnInit(): Promise<void> {
    this.seo.apply('Administración', 'Validar usuarios y revisar el marketplace.', '/admin');
    await this.load();
  }

  async load(): Promise<void> {
    this.error = null;
    try {
      this.data = await this.api.getAdminOverview();
    } catch (e: unknown) {
      const err = e as { status?: number };
      this.error = err.status === 403 ? 'No tienes permisos de administrador.' : 'No se pudo cargar el panel.';
    }
  }

  async identity(userId: number, action: 'approve' | 'reject'): Promise<void> {
    this.actionMsg = null;
    try {
      const res = await this.api.adminIdentityAction(userId, action);
      if (!res.ok) {
        this.error = res.error || 'Error';
        return;
      }
      this.actionMsg = action === 'approve' ? 'Usuario verificado.' : 'Usuario rechazado.';
      await this.load();
      await this.api.refreshSession();
    } catch {
      this.error = 'No se pudo actualizar el usuario.';
    }
  }
}
