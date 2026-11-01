import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fixture from '../src/demo-fixture.json' with { type: 'json' };

const demoUrl = '/?demo=1&date=2026-08-14';

async function mockApi(page: Page) {
  await page.route('**/api/v1/model', (route) => route.fulfill({ json: fixture.model }));
  await page.route('**/health/ready', (route) =>
    route.fulfill({ json: { status: 'ready', database: 'ready', artifact: 'verified' } }),
  );
  await page.route('**/api/v1/predictions?*', (route) => {
    const date = new URL(route.request().url()).searchParams.get('date');
    return route.fulfill({
      json:
        date === fixture.slate.date
          ? fixture.slate
          : { ...fixture.slate, date, count: 0, predictions: [] },
    });
  });
  await page.route('**/api/v1/games/*', (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)!;
    const details = fixture.details as Record<string, unknown>;
    return route.fulfill({
      status: details[id] ? 200 : 404,
      json: details[id] ?? { error: { code: 'game_not_found' } },
    });
  });
}

test('explicit demo is useful and makes no API requests', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => {
    if (/\/(api|health)\//.test(new URL(request.url()).pathname)) requests.push(request.url());
  });
  await page.goto(demoUrl);
  await expect(page.getByText('DEMO · SYNTHETIC DATA', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
  await expect(page.getByText('56.5%', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '95% range' }).click();
  await expect(page.getByRole('button', { name: '95% range' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: 'Away offense' }).click();
  await expect(page.getByRole('button', { name: 'Away offense' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByText('Read the probability table', { exact: true }).click();
  await expect(page.getByRole('rowheader', { name: '12+', exact: true })).toBeVisible();
  await page.getByText('Retrospective calibration evidence', { exact: true }).click();
  await expect(page.getByText(/5,928 games/)).toBeVisible();
  expect(requests).toEqual([]);
});

test('real empty ledger never silently substitutes synthetic records', async ({ page }) => {
  await mockApi(page);
  await page.goto('/?date=2026-11-01');
  await expect(
    page.getByRole('heading', { name: 'The notebook is open. The ledger is empty.' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No forecasts recorded.' })).toBeVisible();
  await expect(page.getByText('DEMO · SYNTHETIC DATA', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Explore the demo' }).click();
  await expect(page).toHaveURL(/demo=1/);
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
  await page.getByRole('button', { name: /Return to recorded forecasts/ }).click();
  await expect(page.getByText('DEMO · SYNTHETIC DATA', { exact: true })).toHaveCount(0);
});

test('game selection and history navigation preserve missing-evidence semantics', async ({
  page,
}) => {
  await page.goto(demoUrl);
  await page.getByRole('button', { name: /New York Yankees.*Boston Red Sox/ }).click();
  await expect(page).toHaveURL(/game=8000002/);
  await expect(page.getByText('Input evidence was not retained.', { exact: true })).toBeVisible();
  await expect(page.getByText('Unknown', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
});

test('lookup distinguishes unrecorded games from unknown IDs', async ({ page }) => {
  await page.goto(demoUrl);
  await page.getByLabel('Find a retained game').fill('8000003');
  await page.getByRole('button', { name: 'Find game', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No official forecast recorded.' })).toBeVisible();
  await page.getByLabel('Find a retained game').fill('999999');
  await page.getByRole('button', { name: 'Find game', exact: true }).click();
  await expect(page.getByText('Game detail unavailable.', { exact: true })).toBeVisible();
  await page.getByLabel('Find a retained game').fill('0');
  await page.getByRole('button', { name: 'Find game', exact: true }).click();
  await expect(page.getByText('Enter a positive MLB game ID.', { exact: true })).toBeVisible();
});

test('dates clear old games and keep official-date semantics', async ({ page }) => {
  await page.goto(demoUrl);
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Next date' }).click();
  await expect(page.getByRole('heading', { name: 'No forecasts recorded.' })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Previous date' }).click();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
});

test('API errors are not empty ledgers and do not enable demo automatically', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/v1/predictions?*', (route) =>
    route.fulfill({ status: 503, json: { error: { code: 'database_unavailable' } } }),
  );
  await page.goto('/?date=2026-08-14');
  await expect(page.getByText('The slate could not be loaded.', { exact: true })).toBeVisible();
  await expect(page.getByText('DEMO · SYNTHETIC DATA', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'No forecasts recorded.' })).toHaveCount(0);
});

test('malformed responses fail closed', async ({ page }) => {
  await mockApi(page);
  const bad = structuredClone(fixture.slate);
  bad.predictions[0].home.run_distribution.probabilities = [1];
  await page.route('**/api/v1/predictions?*', (route) => route.fulfill({ json: bad }));
  await page.goto('/?date=2026-08-14');
  await expect(page.getByText(/API response failed validation/)).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toHaveCount(0);
});

test('failed refresh retains data with an explicit stale warning', async ({ page }) => {
  await mockApi(page);
  await page.goto('/?date=2026-08-14');
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
  await page.route('**/api/v1/predictions?*', (route) => route.fulfill({ status: 503, json: {} }));
  await page.route('**/api/v1/games/*', (route) => route.fulfill({ status: 503, json: {} }));
  await page.getByRole('button', { name: /Refresh/ }).click();
  await expect(
    page.getByText('Refresh failed. Showing the previously loaded slate.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Refresh failed. This is the previously loaded game record.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
});

test('missing artifact does not hide readable records', async ({ page }) => {
  await mockApi(page);
  await page.route('**/health/ready', (route) =>
    route.fulfill({
      status: 503,
      json: { status: 'not_ready', database: 'ready', artifact: 'missing' },
    }),
  );
  await page.goto('/?date=2026-08-14&game=8000001');
  await expect(page.getByText('Model artifact unavailable', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
});

test('settlement and censored score bins never replace the forecast', async ({ page }) => {
  await mockApi(page);
  const base = fixture.details['8000001'];
  const detail = {
    ...base,
    official_prediction: {
      ...base.official_prediction,
      most_likely_score_bins: [{ home_run_bucket: '12+', away_run_bucket: '3', probability: 0.01 }],
      observed_outcome: {
        home_team_runs: 15,
        away_team_runs: 3,
        home_win: true,
        observed_at: '2026-08-14T22:00:00Z',
        settlement_timestamp: '2026-08-14T22:00:00Z',
        completion_status: 'Final',
        actual_start_time_utc: '2026-08-14T18:20:00Z',
        minutes_before_actual_start: 30,
      },
    },
  };
  await page.route('**/api/v1/games/8000001', (route) => route.fulfill({ json: detail }));
  await page.goto('/?date=2026-08-14&game=8000001');
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals 3 — Chicago Cubs 15' }),
  ).toBeVisible();
  await expect(page.locator('.run-number', { hasText: '4.8' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '12+', exact: true })).toBeVisible();
});

test('loading state does not prematurely announce an empty ledger', async ({ page }) => {
  await mockApi(page);
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/predictions?*', async (route) => {
    await gate;
    await route.fulfill({ json: fixture.slate });
  });
  await page.goto('/?date=2026-08-14');
  await expect(page.getByText('Loading dated forecasts…', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'The notebook is open. The ledger is empty.' }),
  ).toHaveCount(0);
  release();
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
});

test('slow earlier dates cannot replace the active date', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/v1/predictions?date=2026-08-14', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill({ json: fixture.slate }).catch(() => {});
  });
  await page.goto('/?date=2026-08-14');
  await page.getByRole('button', { name: 'Next date' }).click();
  await expect(page.getByRole('heading', { name: 'No forecasts recorded.' })).toBeVisible();
  await page.waitForTimeout(1000);
  await expect(page.getByLabel('Game date')).toHaveValue('2026-08-15');
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toHaveCount(0);
});

test('mobile layout and keyboard navigation remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(demoUrl);
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to forecasts' })).toBeFocused();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: '95% range' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: '95% range' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.screenshot({ path: 'test-results/dashboard-mobile.png', fullPage: true });
});

test('desktop and expanded content pass automated accessibility checks', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(demoUrl);
  await expect(
    page.getByRole('heading', { name: 'St. Louis Cardinals at Chicago Cubs' }),
  ).toBeVisible();
  await page.getByText('Read the probability table', { exact: true }).click();
  await page.getByText('Retrospective calibration evidence', { exact: true }).click();
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true });
});
