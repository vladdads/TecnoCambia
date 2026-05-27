import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { SeoService } from '../../services/seo.service';

@Component({
  selector: 'app-sell',
  imports: [FormsModule, RouterLink],
  templateUrl: './sell.component.html',
})
export class SellComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly seo = inject(SeoService);

  categories: string[] = [];
  title = '';
  description = '';
  listing_type = 'sale';
  category = '';
  item_condition = 'good';
  location = '';
  price = '';
  brand = '';
  model = '';
  year = '';
  accessories = '';
  error: string | null = null;
  images: File[] = [];

  async ngOnInit(): Promise<void> {
    this.seo.setSell();
    const m = await this.api.getMeta();
    this.categories = m.categories;
    if (!this.category && this.categories.length) this.category = this.categories[0];
  }

  onFiles(ev: Event): void {
    const t = ev.target as HTMLInputElement;
    this.images = t.files ? Array.from(t.files).slice(0, 6) : [];
  }

  async submit(): Promise<void> {
    this.error = null;
    if (!this.images.length) {
      this.error = 'Debes subir al menos una foto del producto.';
      return;
    }
    const fd = new FormData();
    fd.append('title', this.title);
    fd.append('description', this.description);
    fd.append('listing_type', this.listing_type);
    fd.append('category', this.category);
    fd.append('item_condition', this.item_condition);
    fd.append('location', this.location);
    fd.append('price', this.price);
    fd.append('brand', this.brand);
    fd.append('model', this.model);
    fd.append('year', this.year);
    fd.append('accessories', this.accessories);
    for (const f of this.images) fd.append('images', f);

    const res = await this.api.sell(fd);
    if (!res.ok) {
      this.error = res.error || 'Error';
      return;
    }
    location.href = `/app/products/${res.productId}`;
  }
}
