import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';
import { ApiService } from '../services/api.service';

export const authGuard: CanActivateFn = async (_route, state) => {
  const api = inject(ApiService);
  const router = inject(Router);
  await api.refreshSession();
  if (api.user()) return true;
  return router.createUrlTree(['/login'], { queryParams: { next: state.url } });
};
