import { test, expect } from '@playwright/test';

test.describe('Flujos principales', () => {
  test('el catálogo Angular carga', async ({ page }) => {
    await page.goto('/app/products');
    await expect(page.locator('.hero h1')).toContainText('segunda vida');
  });

  test('login con usuario demo y publicar anuncio', async ({ page }) => {
    await page.goto('/app/login');
    await page.locator('#login-email').fill('demo@tecnocambia.local');
    await page.locator('#login-pass').fill('demo1234');
    await page.getByRole('button', { name: 'Entrar' }).click();
    await page.waitForURL(/\/app\/products/, { timeout: 20_000 });

    await page.goto('/app/sell');
    await expect(page.locator('#sell-cat')).toBeVisible();
    await expect(page.locator('#sell-cat option').first()).toBeAttached();

    const stamp = Date.now();
    await page.locator('#sell-title').fill(`Prueba E2E ${stamp}`);
    await page.locator('#sell-desc').fill('Descripción generada por prueba automática de Playwright.');
    await page.locator('#sell-loc').fill('CDMX');
    await page.locator('#sell-price').fill('199');

    await page.getByRole('button', { name: 'Publicar' }).click();
    await expect(page).toHaveURL(/\/app\/products\/\d+/, { timeout: 25_000 });
  });
});
