import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';
import { ApiService } from '../services/api.service';

export const verifiedGuard: CanActivateFn = async () => {
  const api = inject(ApiService);
  const router = inject(Router);
  await api.refreshSession();
  const u = api.user();
  if (!u) return router.createUrlTree(['/login']);
  if (u.verificationStatus === 'verified') return true;
  return router.createUrlTree(['/products'], {
    queryParams: { aviso: 'verificacion' },
  });
};
