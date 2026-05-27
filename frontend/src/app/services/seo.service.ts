import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';

const DEFAULT_DESC =
  'Publica en venta, intercambio o donación. Recicla y da segunda vida a tu tecnología en Tecnocambia.';

@Injectable({ providedIn: 'root' })
export class SeoService {
  private readonly title = inject(Title);
  private readonly meta = inject(Meta);
  private readonly document = inject(DOCUMENT);

  private baseUrl(): string {
    const w = this.document.defaultView;
    if (!w?.location?.origin) return '';
    return w.location.origin;
  }

  private canonicalPath(path: string): string {
    const base = this.baseUrl();
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${base}/app${p}`;
  }

  apply(pageTitle: string, description: string, pathForOg: string): void {
    const fullTitle = pageTitle.includes('Tecnocambia') ? pageTitle : `${pageTitle} | Tecnocambia`;
    this.title.setTitle(fullTitle);
    this.meta.updateTag({ name: 'description', content: description });

    const url = this.canonicalPath(pathForOg);
    this.meta.updateTag({ property: 'og:title', content: fullTitle });
    this.meta.updateTag({ property: 'og:description', content: description });
    this.meta.updateTag({ property: 'og:type', content: 'website' });
    if (url) {
      this.meta.updateTag({ property: 'og:url', content: url });
      this.meta.updateTag({ property: 'og:image', content: `${this.baseUrl()}/logo.jpeg` });
    }
  }

  setCatalog(): void {
    this.apply('Catálogo', DEFAULT_DESC, '/products');
  }

  setProductDetail(productTitle: string, excerpt: string, id: number): void {
    const desc = excerpt.length > 160 ? `${excerpt.slice(0, 157)}…` : excerpt || DEFAULT_DESC;
    this.apply(productTitle, desc, `/products/${id}`);
  }

  setLogin(): void {
    this.apply('Iniciar sesión', 'Accede a tu cuenta Tecnocambia.', '/login');
  }

  setRegister(): void {
    this.apply('Crear cuenta', 'Registro con verificación de identidad (INE y CURP).', '/register');
  }

  setSell(): void {
    this.apply('Publicar anuncio', 'Publica equipo en venta, intercambio o donación.', '/sell');
  }
}
