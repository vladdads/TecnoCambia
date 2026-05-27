import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { SeoService } from '../../services/seo.service';

@Component({
  selector: 'app-register',
  imports: [FormsModule, RouterLink],
  templateUrl: './register.component.html',
})
export class RegisterComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly seo = inject(SeoService);

  name = '';
  email = '';
  password = '';
  curp = '';
  error: string | null = null;
  ineFile: File | null = null;

  ngOnInit(): void {
    this.seo.setRegister();
  }

  onIne(ev: Event): void {
    const t = ev.target as HTMLInputElement;
    this.ineFile = t.files?.[0] ?? null;
  }

  async submit(): Promise<void> {
    this.error = null;
    if (!this.ineFile) {
      this.error = 'Sube la foto de tu INE (frente).';
      return;
    }
    const fd = new FormData();
    fd.append('name', this.name);
    fd.append('email', this.email);
    fd.append('password', this.password);
    fd.append('curp', this.curp.toUpperCase());
    fd.append('ine_photo', this.ineFile);
    const next = this.route.snapshot.queryParamMap.get('next') || '/app/products';
    fd.append('next', next);

    const res = await this.api.register(fd);
    if (!res.ok) {
      this.error = res.error || 'Error';
      return;
    }
    location.href = res.next || '/app/products';
  }
}
