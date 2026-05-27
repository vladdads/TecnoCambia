import { Component, inject, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, type ProductRow } from '../../services/api.service';
import { SeoService } from '../../services/seo.service';

@Component({
  selector: 'app-product-list',
  imports: [RouterLink, FormsModule],
  templateUrl: './product-list.component.html',
})
export class ProductListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly seo = inject(SeoService);

  q = '';
  listingType = '';
  category = '';
  itemCondition = '';
  location = '';
  minPrice = '';
  maxPrice = '';
  withPhotos = '';
  sort = 'recent';
  page = 1;
  totalPages = 1;
  totalResults = 0;
  products: ProductRow[] = [];
  filterCategories: string[] = [];
  filterLocations: string[] = [];
  presetCategories: string[] = [];
  aviso = '';

  readonly conditionOptions: { value: string; label: string }[] = [
    { value: '', label: 'Cualquiera' },
    { value: 'new', label: 'Nuevo' },
    { value: 'like_new', label: 'Como nuevo' },
    { value: 'good', label: 'Bueno' },
    { value: 'fair', label: 'Regular' },
    { value: 'for_parts', label: 'Para piezas' },
  ];

  readonly sortOptions: { value: string; label: string }[] = [
    { value: 'recent', label: 'Más recientes' },
    { value: 'price_asc', label: 'Precio: menor a mayor' },
    { value: 'price_desc', label: 'Precio: mayor a menor' },
  ];

  ngOnInit(): void {
    this.seo.setCatalog();
    void this.api.getMeta().then((m) => {
      this.presetCategories = m.categories || [];
    });
    this.route.queryParamMap.subscribe((pm) => {
      this.q = pm.get('q') || '';
      this.listingType = pm.get('type') || '';
      this.category = pm.get('category') || '';
      this.itemCondition = pm.get('condition') || '';
      this.location = pm.get('location') || '';
      this.minPrice = pm.get('min_price') || '';
      this.maxPrice = pm.get('max_price') || '';
      this.withPhotos = pm.get('photos') || '';
      this.sort = pm.get('sort') || 'recent';
      this.page = Number(pm.get('page') || '1') || 1;
      this.aviso = pm.get('aviso') || '';
      void this.load();
    });
  }

  private async load(): Promise<void> {
    const data = await this.api.getProducts({
      q: this.q || undefined,
      type: this.listingType || undefined,
      category: this.category || undefined,
      condition: this.itemCondition || undefined,
      location: this.location || undefined,
      min_price: this.minPrice || undefined,
      max_price: this.maxPrice || undefined,
      photos: this.withPhotos || undefined,
      sort: this.sort && this.sort !== 'recent' ? this.sort : undefined,
      page: this.page,
    });
    this.products = data.products;
    this.totalPages = data.totalPages;
    this.totalResults = data.totalResults;
    this.filterCategories = data.categories || [];
    this.filterLocations = data.locations || [];
  }

  applyFilters(): void {
    this.router.navigate(['/products'], {
      queryParams: {
        q: this.q || null,
        type: this.listingType || null,
        category: this.category || null,
        condition: this.itemCondition || null,
        location: this.location || null,
        min_price: this.minPrice || null,
        max_price: this.maxPrice || null,
        photos: this.withPhotos || null,
        sort: this.sort && this.sort !== 'recent' ? this.sort : null,
        page: 1,
      },
      queryParamsHandling: '',
    });
  }

  clearFilters(): void {
    this.router.navigate(['/products']);
  }

  setType(t: string): void {
    this.listingType = t;
    this.applyFilters();
  }

  goPage(p: number): void {
    this.router.navigate(['/products'], {
      queryParams: { page: p },
      queryParamsHandling: 'merge',
    });
  }

  formatPrice(cents: number | null, listingType?: string): string {
    if (listingType === 'donation') return 'Gratis';
    if (listingType === 'exchange') return 'Intercambio';
    if (cents == null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(
      cents / 100,
    );
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

  typeLabel(t: string): string {
    if (t === 'sale') return 'Venta';
    if (t === 'exchange') return 'Intercambio';
    if (t === 'donation') return 'Donación';
    return t;
  }
}
