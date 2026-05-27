import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, type UserProfile } from '../../../services/api.service';
import { SeoService } from '../../../services/seo.service';

@Component({
  selector: 'app-profile',
  imports: [FormsModule],
  templateUrl: './profile.component.html',
})
export class ProfileComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly seo = inject(SeoService);

  profile: UserProfile | null = null;
  name = '';
  error: string | null = null;
  success: string | null = null;
  loading = true;

  async ngOnInit(): Promise<void> {
    this.seo.apply('Mi perfil', 'Edita tu nombre y revisa el estado de verificación.', '/account/profile');
    await this.load();
  }

  async load(): Promise<void> {
    this.loading = true;
    this.error = null;
    try {
      const res = await this.api.getProfile();
      this.profile = res.user;
      this.name = res.user.name;
    } catch {
      this.error = 'No se pudo cargar tu perfil.';
    } finally {
      this.loading = false;
    }
  }

  async save(): Promise<void> {
    this.error = null;
    this.success = null;
    try {
      const res = await this.api.updateProfile(this.name);
      if (!res.ok) {
        this.error = res.error || 'No se pudo guardar.';
        return;
      }
      await this.api.refreshSession();
      await this.load();
      this.success = 'Perfil actualizado.';
    } catch {
      this.error = 'Error al guardar.';
    }
  }

  async uploadIne(e: Event): Promise<void> {
    this.error = null;
    this.success = null;
    const input = e.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    try {
      const res = await this.api.uploadIne(file);
      if (!res.ok) {
        this.error = res.error || 'Error al subir INE.';
        return;
      }
      this.success = 'Foto INE subida.';
      await this.load();
    } catch {
      this.error = 'Error al subir INE.';
    }
  }

  async uploadCurpDoc(e: Event): Promise<void> {
    this.error = null;
    this.success = null;
    const input = e.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    try {
      const res = await this.api.uploadCurpDoc(file);
      if (!res.ok) {
        this.error = res.error || 'Error al subir documento CURP.';
        return;
      }
      this.success = 'Documento CURP subido.';
      await this.load();
    } catch {
      this.error = 'Error al subir documento CURP.';
    }
  }

  async updateCurp(): Promise<void> {
    this.error = null;
    this.success = null;
    try {
      const res = await this.api.updateCurp(this.profile?.curp || '');
      if (!res.ok) {
        this.error = res.error || 'Error al guardar CURP.';
        return;
      }
      this.success = 'CURP actualizada.';
      await this.load();
    } catch {
      this.error = 'Error al guardar CURP.';
    }
  }

  statusLabel(s: string): string {
    if (s === 'verified') return 'Verificado';
    if (s === 'pending') return 'En revisión';
    if (s === 'rejected') return 'Rechazado';
    return s;
  }
}
