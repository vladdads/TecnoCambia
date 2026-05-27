import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { ApiService } from '../services/api.service';

export const adminGuard: CanActivateFn = async () => {
  const api = inject(ApiService);
  const router = inject(Router);
  await api.refreshSession();
  const u = api.user();
  if (!u) {
    return router.createUrlTree(['/login'], { queryParams: { next: '/admin' } });
  }
  if (!u.isAdmin) {
    return router.createUrlTree(['/products']);
  }
  return true;
};
