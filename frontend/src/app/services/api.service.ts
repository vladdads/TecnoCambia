import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type VerificationStatus = 'pending' | 'verified' | 'rejected';

export interface SessionUser {
  id: number;
  name: string;
  email: string;
  isAdmin: boolean;
  verificationStatus: VerificationStatus;
}

export interface UserProfile extends SessionUser {
  curp?: string | null;
  ineImageUrl?: string;
  curpDocumentUrl?: string;
  created_at?: string;
}

export interface ProductRow {
  id: number;
  title: string;
  description: string;
  listing_type: string;
  price_cents: number | null;
  category: string;
  item_condition: string;
  location: string;
  seller_name: string;
  status?: string;
  cover_image?: string | null;
  coverImageUrl?: string;
  image_count?: number;
  created_at?: string;
}

export interface ProductsResponse {
  page: number;
  totalPages: number;
  totalResults: number;
  products: ProductRow[];
  filters: Record<string, string>;
  categories: string[];
  locations: string[];
}

export interface ProductDetail extends ProductRow {
  images: { id: number; url: string }[];
  seller_email?: string;
  brand?: string | null;
  model?: string | null;
  year?: string | null;
  accessories?: string | null;
}

export interface AdminOverview {
  counts: {
    users: number;
    products: number;
    reportsOpen: number;
    pendingIdentity: number;
  };
  pendingUsers: {
    id: number;
    name: string;
    email: string;
    curp: string;
    ineImageUrl: string;
    created_at: string;
    verificationStatus: string;
  }[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  readonly user = signal<SessionUser | null>(null);
  readonly sessionLoaded = signal(false);
  private readonly apiBase = this.resolveApiBase();

  private resolveApiBase(): string {
    const raw = ((globalThis as { __TC_API_BASE__?: string }).__TC_API_BASE__ || '').trim();
    return raw.replace(/\/+$/, '');
  }

  private apiUrl(path: string): string {
    return `${this.apiBase}${path}`;
  }

  externalUrl(path: string): string {
    return this.apiUrl(path);
  }

  async refreshSession(): Promise<void> {
    const res = await firstValueFrom(this.http.get<{ user: SessionUser | null }>(this.apiUrl('/api/session'), { withCredentials: true }));
    this.user.set(res.user ?? null);
    this.sessionLoaded.set(true);
  }

  clearLocalUser(): void {
    this.user.set(null);
    this.sessionLoaded.set(true);
  }

  async login(email: string, password: string, next?: string): Promise<{ ok: boolean; error?: string; next?: string }> {
    try {
      const res = await firstValueFrom(
        this.http.post<{ ok: boolean; error?: string; next?: string }>(
          this.apiUrl('/api/auth/login'),
          {
            email,
            password,
            next: next || '/app/products',
          },
          { withCredentials: true },
        ),
      );
      if (res.ok) await this.refreshSession();
      return res;
    } catch (e: unknown) {
      const err = e as { error?: { error?: string }; status?: number };
      const msg = err.error?.error || 'No se pudo iniciar sesión.';
      return { ok: false, error: msg };
    }
  }

  async logout(): Promise<void> {
    await firstValueFrom(this.http.post<{ ok: boolean }>(this.apiUrl('/api/auth/logout'), {}, { withCredentials: true }));
    this.clearLocalUser();
  }

  async register(form: FormData): Promise<{ ok: boolean; error?: string; next?: string }> {
    try {
      const res = await firstValueFrom(
        this.http.post<{ ok: boolean; error?: string; next?: string }>(this.apiUrl('/api/auth/register'), form, { withCredentials: true }),
      );
      if (res.ok) await this.refreshSession();
      return res;
    } catch (e: unknown) {
      const err = e as { error?: { error?: string } };
      return { ok: false, error: err.error?.error || 'Error al registrar.' };
    }
  }

  getMeta() {
    return firstValueFrom(
      this.http.get<{ categories: string[]; listingTypes: string[]; conditions: string[] }>(this.apiUrl('/api/meta'), { withCredentials: true }),
    );
  }

  getProducts(params: Record<string, string | number | undefined>) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v));
    });
    return firstValueFrom(this.http.get<ProductsResponse>(this.apiUrl(`/api/products?${q.toString()}`), { withCredentials: true }));
  }

  getProduct(id: number) {
    return firstValueFrom(this.http.get<{ product: ProductDetail }>(this.apiUrl(`/api/products/${id}`), { withCredentials: true }));
  }

  async sell(form: FormData): Promise<{ ok: boolean; productId?: number; error?: string }> {
    try {
      return await firstValueFrom(this.http.post<{ ok: boolean; productId?: number; error?: string }>(this.apiUrl('/api/sell'), form, { withCredentials: true }));
    } catch (e: unknown) {
      const err = e as { error?: { error?: string } };
      return { ok: false, error: err.error?.error || 'No se pudo publicar.' };
    }
  }

  getProfile() {
    return firstValueFrom(this.http.get<{ user: UserProfile }>(this.apiUrl('/api/me'), { withCredentials: true }));
  }

  updateProfile(name: string) {
    return firstValueFrom(this.http.patch<{ ok: boolean; error?: string }>(this.apiUrl('/api/me'), { name }, { withCredentials: true }));
  }

  uploadIne(file: File) {
    const fd = new FormData();
    fd.append('ine', file);
    return firstValueFrom(this.http.post<{ ok: boolean; url?: string; error?: string }>(this.apiUrl('/api/me/ine'), fd, { withCredentials: true }));
  }

  uploadCurpDoc(file: File) {
    const fd = new FormData();
    fd.append('curp_doc', file);
    return firstValueFrom(this.http.post<{ ok: boolean; url?: string; error?: string }>(this.apiUrl('/api/me/curp-doc'), fd, { withCredentials: true }));
  }

  updateCurp(curp: string) {
    return firstValueFrom(this.http.patch<{ ok: boolean; error?: string }>(this.apiUrl('/api/me/curp'), { curp }, { withCredentials: true }));
  }

  getMyListings() {
    return firstValueFrom(this.http.get<{ products: ProductRow[] }>(this.apiUrl('/api/me/listings'), { withCredentials: true }));
  }

  getAdminOverview() {
    return firstValueFrom(this.http.get<AdminOverview>(this.apiUrl('/api/admin/overview'), { withCredentials: true }));
  }

  adminIdentityAction(userId: number, action: 'approve' | 'reject') {
    return firstValueFrom(
      this.http.post<{ ok: boolean; status?: string; error?: string }>(
        this.apiUrl(`/api/admin/identity/${userId}`),
        { action },
        { withCredentials: true },
      ),
    );
  }
}
