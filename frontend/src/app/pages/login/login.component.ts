import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { SeoService } from '../../services/seo.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule, RouterLink],
  templateUrl: './login.component.html',
})
export class LoginComponent implements OnInit {
  readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly seo = inject(SeoService);

  email = '';
  password = '';
  error: string | null = null;

  ngOnInit(): void {
    this.seo.setLogin();
  }

  async submit(): Promise<void> {
    this.error = null;
    const next = this.route.snapshot.queryParamMap.get('next') || '/app/products';
    const res = await this.api.login(this.email, this.password, next);
    if (!res.ok) {
      this.error = res.error || 'Error';
      return;
    }
    location.href = res.next || '/app/products';
  }
}
