import { Component, inject, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService, type ProductRow } from '../../../services/api.service';
import { SeoService } from '../../../services/seo.service';

@Component({
  selector: 'app-my-listings',
  imports: [RouterLink],
  templateUrl: './my-listings.component.html',
})
export class MyListingsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly seo = inject(SeoService);

  products: ProductRow[] = [];
  error: string | null = null;

  async ngOnInit(): Promise<void> {
    this.seo.apply('Mis publicaciones', 'Anuncios que publicaste en Tecnocambia.', '/account/listings');
    try {
      const res = await this.api.getMyListings();
      this.products = res.products;
    } catch {
      this.error = 'No se pudieron cargar tus publicaciones.';
    }
  }

  formatPrice(cents: number | null, listingType: string): string {
    if (listingType === 'donation') return 'Gratis';
    if (listingType === 'exchange') return 'Intercambio';
    if (cents == null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(
      cents / 100,
    );
  }

  typeLabel(t: string): string {
    if (t === 'sale') return 'Venta';
    if (t === 'exchange') return 'Intercambio';
    if (t === 'donation') return 'Donación';
    return t;
  }
}
