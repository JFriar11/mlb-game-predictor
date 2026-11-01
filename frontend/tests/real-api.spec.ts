import { expect, test } from '@playwright/test';

test('local production preview reads the real API through its proxy', async ({ page, request }) => {
  test.skip(
    process.env.MLB_DASHBOARD_REAL_API !== '1',
    'Requires an explicitly started local API.',
  );
  const response = await request.get('/api/v1/predictions?date=2026-08-14');
  expect(response.ok()).toBe(true);
  const body = await response.json();
  const ready = await request.get('/health/ready');
  expect((await ready.json()).database).toBe('ready');
  await page.goto('/?date=2026-08-14');
  if (body.count === 0) {
    await expect(page.getByRole('heading', { name: 'No forecasts recorded.' })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'The notebook is open. The ledger is empty.' }),
    ).toBeVisible();
  } else {
    await expect(page.locator('.game-card')).toHaveCount(body.count);
  }
  await expect(page.getByText('DEMO · SYNTHETIC DATA', { exact: true })).toHaveCount(0);
  await expect(page.getByText('accepted_v1_2026_prospective', { exact: true })).toBeAttached();
});
