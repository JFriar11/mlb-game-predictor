import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fixture from '../src/demo-fixture.json' with { type: 'json' };

const players = Array.from({ length: 20 }, (_, i) => ({ id: i + 100, name: `Player ${i + 100}` }));
const catalog = {
  teams: [
    { id: 10, name: 'Away Club' },
    { id: 20, name: 'Home Club' },
  ],
  players,
  venues: [{ id: 30, name: 'Test Park' }],
  latest_history_date: '2026-08-13',
  default_as_of: '2026-08-14T00:00:00Z',
};
async function mock(page: Page, mode: 'normal' | 'fail' | 'malformed' | 'slow' = 'normal') {
  await page.route('**/api/v1/sandbox/catalog', (route) => route.fulfill({ json: catalog }));
  await page.route('**/api/v1/sandbox/lineup?*', (route) => {
    const home = new URL(route.request().url()).searchParams.get('team_id') === '20';
    return route.fulfill({
      json: {
        game_date: '2026-08-13',
        venue_id: 30,
        starter_id: home ? 119 : 118,
        lineup: Array.from({ length: 9 }, (_, i) => i + (home ? 109 : 100)),
      },
    });
  });
  await page.route('**/api/v1/sandbox/predict', async (route) => {
    if (mode === 'fail')
      return route.fulfill({
        status: 503,
        json: {
          error: {
            message: 'The accepted local model is missing or failed checksum verification.',
          },
        },
      });
    if (mode === 'malformed') return route.fulfill({ json: { kind: 'official' } });
    if (mode === 'slow') await new Promise((resolve) => setTimeout(resolve, 700));
    const p = fixture.slate.predictions[0];
    return route.fulfill({
      json: {
        kind: 'hypothetical',
        is_official: false,
        saved: false,
        model_version: p.provenance.model_version,
        artifact_sha256: 'a'.repeat(64),
        generated_at: '2026-08-14T00:00:00Z',
        inputs: route.request().postDataJSON(),
        latest_history_date: '2026-08-13',
        home: { ...p.home, run_ranges: p.run_ranges.home },
        away: { ...p.away, run_ranges: p.run_ranges.away },
        calibrated_home_win_probability: p.calibrated_home_win_probability,
        away_win_probability: p.away_win_probability,
        most_likely_score_bins: p.most_likely_score_bins,
        warnings: ['Hypothetical fixture for interface testing.'],
        explanation: p.explanation,
        confidence: p.confidence,
      },
    });
  });
  await page.goto('/?sandbox=1');
  await page.getByRole('button', { name: 'Load away retained lineup' }).click();
  await expect(page.getByLabel('away hitter 1', { exact: true })).toHaveValue('Player 100 (#100)');
  await page.getByRole('button', { name: 'Load home retained lineup' }).click();
  await expect(page.getByLabel('home hitter 1', { exact: true })).toHaveValue('Player 109 (#109)');
}

test('custom lineups produce a labeled ephemeral result; edits clear it', async ({ page }) => {
  const writes: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST') writes.push(new URL(r.url()).pathname);
  });
  await mock(page);
  await page.getByRole('button', { name: 'Predict this matchup' }).click();
  await expect(page.getByRole('heading', { name: 'Away Club at Home Club' })).toBeVisible();
  await expect(page.getByText('HYPOTHETICAL RESULT · NOT SAVED')).toBeVisible();
  await page.getByText('Away run distribution', { exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Runs', exact: true })).toBeVisible();
  await page.getByText('Baseball inputs behind this result').click();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(writes).toEqual(['/api/v1/sandbox/predict']);
  await page.getByLabel('away hitter 1', { exact: true }).fill('Player 119 (#119)');
  await expect(page.getByText('HYPOTHETICAL RESULT · NOT SAVED')).toHaveCount(0);
});

test('duplicate or unrecognized hitters do not submit', async ({ page }) => {
  await mock(page);
  await page.getByLabel('away hitter 1', { exact: true }).fill('Player 101 (#101)');
  await page.getByRole('button', { name: 'Predict this matchup' }).click();
  await expect(page.getByRole('alert')).toContainText('18 different hitters');
  await page.getByLabel('away hitter 1', { exact: true }).fill('Somebody');
  await page.getByRole('button', { name: 'Predict this matchup' }).click();
  await expect(page.getByRole('alert')).toContainText('player suggestions');
});

for (const mode of ['fail', 'malformed'] as const)
  test(`${mode} response never becomes a forecast`, async ({ page }) => {
    await mock(page, mode);
    await page.getByRole('button', { name: 'Predict this matchup' }).click();
    await expect(page.getByRole('alert')).toContainText(
      mode === 'fail' ? 'model is missing' : 'failed validation',
    );
    await expect(page.getByText('HYPOTHETICAL RESULT · NOT SAVED')).toHaveCount(0);
  });

test('editing during calculation discards the earlier result', async ({ page }) => {
  await mock(page, 'slow');
  await page.getByRole('button', { name: 'Predict this matchup' }).click();
  await expect(page.getByRole('button', { name: 'Working with local history…' })).toBeDisabled();
  await page.getByLabel('away hitter 1', { exact: true }).fill('Player 119 (#119)');
  await page.waitForTimeout(900);
  await expect(page.getByText('HYPOTHETICAL RESULT · NOT SAVED')).toHaveCount(0);
});

test('lineup form fits mobile and supports keyboard access', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mock(page);
  await page.getByLabel('away hitter 1', { exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('away hitter 2', { exact: true })).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test('real local sandbox uses retained lineups and the accepted model', async ({ page }) => {
  test.skip(
    process.env.MLB_SANDBOX_REAL_API !== '1',
    'Requires the explicitly enabled local sandbox.',
  );
  await page.goto('/?sandbox=1');
  await page.getByRole('button', { name: 'Load away retained lineup' }).click();
  await expect(page.getByLabel('away hitter 1', { exact: true })).not.toHaveValue('');
  await page.getByRole('button', { name: 'Load home retained lineup' }).click();
  await expect(page.getByLabel('home hitter 1', { exact: true })).not.toHaveValue('');
  await page.getByRole('button', { name: 'Predict this matchup' }).click();
  await expect(page.getByText('HYPOTHETICAL RESULT · NOT SAVED')).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/sandbox-desktop.png', fullPage: true });
});
