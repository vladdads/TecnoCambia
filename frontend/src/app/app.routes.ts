import { Routes } from '@angular/router';
import { ShellComponent } from './layout/shell/shell.component';
import { ProductListComponent } from './pages/product-list/product-list.component';
import { ProductDetailComponent } from './pages/product-detail/product-detail.component';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { SellComponent } from './pages/sell/sell.component';
import { ProfileComponent } from './pages/account/profile/profile.component';
import { MyListingsComponent } from './pages/account/listings/my-listings.component';
import { AdminPanelComponent } from './pages/admin/admin-panel/admin-panel.component';
import { authGuard } from './guards/auth.guard';
import { verifiedGuard } from './guards/verified.guard';
import { adminGuard } from './guards/admin.guard';

export const routes: Routes = [
  {
    path: '',
    component: ShellComponent,
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'products' },
      { path: 'products', component: ProductListComponent },
      { path: 'products/:id', component: ProductDetailComponent },
      { path: 'login', component: LoginComponent },
      { path: 'register', component: RegisterComponent },
      { path: 'sell', component: SellComponent, canActivate: [authGuard, verifiedGuard] },
      { path: 'account/profile', component: ProfileComponent, canActivate: [authGuard] },
      { path: 'account/listings', component: MyListingsComponent, canActivate: [authGuard] },
      { path: 'admin', component: AdminPanelComponent, canActivate: [authGuard, adminGuard] },
    ],
  },
];
