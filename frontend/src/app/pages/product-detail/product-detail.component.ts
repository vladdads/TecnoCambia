import { Component, inject, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService, type ProductDetail } from '../../services/api.service';
import { SeoService } from '../../services/seo.service';

@Component({
  selector: 'app-product-detail',
  imports: [RouterLink],
  templateUrl: './product-detail.component.html',
})
export class ProductDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  readonly api = inject(ApiService);
  private readonly seo = inject(SeoService);

  product: ProductDetail | null = null;
  error: string | null = null;

  ngOnInit(): void {
    this.route.paramMap.subscribe((pm) => {
      const id = Number(pm.get('id'));
      if (!Number.isFinite(id)) return;
      void this.load(id);
    });
  }

  private async load(id: number): Promise<void> {
    try {
      const res = await this.api.getProduct(id);
      this.product = res.product;
      this.error = null;
      const excerpt = (this.product.description || '').replace(/\s+/g, ' ').trim();
      this.seo.setProductDetail(this.product.title, excerpt || this.product.title, id);
    } catch {
      this.error = 'No encontramos este anuncio.';
      this.product = null;
    }
  }

  formatPrice(cents: number | null): string {
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

  formatCondition(code: string): string {
    const map: Record<string, string> = {
      new: 'Nuevo',
      like_new: 'Casi nuevo',
      good: 'Bueno',
      fair: 'Regular',
      for_parts: 'Para piezas',
    };
    return map[code] || code.replace(/_/g, ' ');
  }
}
