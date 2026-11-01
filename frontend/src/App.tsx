import { useEffect, useState, type FormEvent } from 'react';
import { api } from './api';
import { demo, DEMO_DATE } from './demo';
import type { Detail, Prediction } from './contracts';
import { Sandbox } from './Sandbox';
import { Forecast } from './Forecast';
import { moveDate, number, pct, prettyDate, teamName, time, today, validDate } from './format';
import { useResource } from './resource';

type Route = { date: string; game?: number; demo: boolean };
function readRoute(): Route {
  const query = new URLSearchParams(window.location.search);
  const date = query.get('date'),
    game = Number(query.get('game'));
  return {
    date: validDate(date) ? date : today(),
    demo: query.get('demo') === '1',
    game: Number.isInteger(game) && game > 0 && game <= 2_147_483_647 ? game : undefined,
  };
}

export function App() {
  return new URLSearchParams(window.location.search).get('sandbox') === '1' ? (
    <Sandbox />
  ) : (
    <Notebook />
  );
}

function Notebook() {
  const [route, setRoute] = useState<Route>(readRoute);
  const [refresh, setRefresh] = useState(0);
  const [lookup, setLookup] = useState('');
  const [lookupError, setLookupError] = useState('');
  useEffect(() => {
    const back = () => setRoute(readRoute());
    window.addEventListener('popstate', back);
    return () => window.removeEventListener('popstate', back);
  }, []);
  function navigate(next: Route) {
    const query = new URLSearchParams();
    query.set('date', next.date);
    if (next.game) query.set('game', String(next.game));
    if (next.demo) query.set('demo', '1');
    window.history.pushState(null, '', `?${query}`);
    setRoute(next);
    setLookupError('');
  }
  const mode = route.demo ? 'demo' : 'recorded';
  const slate = useResource(`${mode}:slate:${route.date}`, refresh, async (signal) => {
    const result = route.demo ? await demo.slate(route.date) : await api.slate(route.date, signal);
    if (result.date !== route.date)
      throw new Error('The API returned a different date. No forecast is displayed.');
    return result;
  });
  const selected = route.game ?? slate.data?.predictions[0]?.game_pk;
  const detail = useResource<Detail | null>(
    `${mode}:game:${route.date}:${selected ?? ''}`,
    refresh,
    async (signal) => {
      if (!selected) return null;
      const result = route.demo ? await demo.detail(selected) : await api.detail(selected, signal);
      if (result.game_pk !== selected)
        throw new Error('The API returned a different game. No forecast is displayed.');
      return result;
    },
  );
  const model = useResource(`${mode}:model`, refresh, (signal) =>
    route.demo ? demo.model() : api.model(signal),
  );
  const readiness = useResource(`${mode}:health`, refresh, async (signal) =>
    route.demo ? null : api.readiness(signal),
  );
  const predictions = slate.data?.predictions ?? [];
  const p = detail.data?.official_prediction;
  const isBusy = slate.loading || detail.loading;

  function findGame(event: FormEvent) {
    event.preventDefault();
    const id = Number(lookup);
    if (!/^\d+$/.test(lookup) || !Number.isInteger(id) || id <= 0 || id > 2_147_483_647) {
      setLookupError('Enter a positive MLB game ID.');
      return;
    }
    navigate({ ...route, game: id });
  }

  const healthLabel = route.demo
    ? 'Synthetic demonstration'
    : readiness.data?.status === 'ready'
      ? 'API ready'
      : readiness.data?.database === 'unavailable'
        ? 'Storage unavailable'
        : readiness.data
          ? 'Model artifact unavailable'
          : readiness.error
            ? 'API status unavailable'
            : 'Checking API';

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to forecasts
      </a>
      <header className="site-header">
        <div className="header-inner">
          <a className="brand" href="#main-content">
            <span className="brand-mark" aria-hidden="true">
              ◇
            </span>
            <span>
              MLB Game Predictor<small>THE PREGAME NOTEBOOK</small>
            </span>
          </a>
          <nav aria-label="Main navigation">
            <a href="#slate">Daily slate</a>
            <a href="?sandbox=1">Lineup sandbox</a>
            <a href="#model-notes">Model notes</a>
          </nav>
          <span
            className={`service-status ${route.demo ? 'demo-status' : readiness.data?.status === 'ready' ? 'ready' : ''}`}
          >
            <span aria-hidden="true" />
            {healthLabel}
          </span>
        </div>
      </header>
      <main id="main-content" className="page-shell" tabIndex={-1}>
        {route.demo && (
          <div className="demo-banner" role="note">
            <strong>DEMO · SYNTHETIC DATA</strong>
            <p>
              Illustrative forecasts, not genuine MLB predictions or ledger records. No API calls or
              database writes in this mode.
            </p>
            <button onClick={() => navigate({ date: today(), demo: false })}>
              Return to recorded forecasts <span aria-hidden="true">↗</span>
            </button>
          </div>
        )}
        <section className="intro">
          <div>
            <p className="eyebrow">BASEBALL, BEFORE THE FIRST PITCH</p>
            <h1>
              The pregame notebook<span>.</span>
            </h1>
            <p>
              Runs, probabilities, and the evidence behind them.
              <br className="desktop-break" /> A transparent view of the game ahead.
            </p>
          </div>
          <div className="intro-aside">
            <div className="field-mark" aria-hidden="true">
              <i />
              <span />
            </div>
            <p>
              CONFIRMED-LINEUP FORECASTS
              <br />
              <strong>Built for the uncertainty of baseball.</strong>
            </p>
          </div>
        </section>

        <section className="slate-toolbar" id="slate" aria-label="Date and forecast controls">
          <div className="date-controls">
            <button
              className="icon-button"
              aria-label="Previous date"
              disabled={route.date === '0001-01-01'}
              onClick={() =>
                navigate({ ...route, date: moveDate(route.date, -1), game: undefined })
              }
            >
              ←
            </button>
            <label className="date-label">
              Game date
              <input
                aria-label="Game date"
                type="date"
                value={route.date}
                min="0001-01-01"
                max="9999-12-31"
                onChange={(event) => {
                  if (validDate(event.target.value))
                    navigate({ ...route, date: event.target.value, game: undefined });
                }}
              />
            </label>
            <button
              className="icon-button"
              aria-label="Next date"
              disabled={route.date === '9999-12-31'}
              onClick={() => navigate({ ...route, date: moveDate(route.date, 1), game: undefined })}
            >
              →
            </button>
            <button
              className="text-button today-button"
              onClick={() => navigate({ ...route, date: today(), game: undefined })}
            >
              Today
            </button>
          </div>
          <div className="toolbar-actions">
            <span className="loaded-at">
              {slate.loadedAt ? `Loaded ${time(slate.loadedAt)}` : 'All times Central'}
            </span>
            <button
              className="outline-button"
              onClick={() => setRefresh((value) => value + 1)}
              disabled={isBusy}
            >
              <span aria-hidden="true">↻</span> {isBusy ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </section>
        <div className="date-caption">
          <h2>{prettyDate(route.date)}</h2>
          <span>All times Central · MLB official game dates</span>
        </div>
        {slate.error && (
          <div className="error-box" role="alert">
            <strong>
              {slate.data
                ? 'Refresh failed. Showing the previously loaded slate.'
                : 'The slate could not be loaded.'}
            </strong>
            <p>{slate.error}</p>
            <button className="text-button" onClick={() => setRefresh((v) => v + 1)}>
              Try again
            </button>
          </div>
        )}
        <div className="workspace">
          <aside className="slate-column" aria-label="Dated forecasts">
            <div className="slate-heading">
              <h3>{route.demo ? 'Demo slate' : 'Recorded forecasts'}</h3>
              <span>
                {slate.loading && !slate.data
                  ? '…'
                  : predictions.length.toString().padStart(2, '0')}
              </span>
            </div>
            <p className="slate-description">
              {route.demo
                ? 'Two illustrative records. No live performance claim.'
                : 'Official records from the accepted model. No forecast is generated by this page.'}
            </p>
            {slate.loading && !slate.data ? (
              <div className="loading-state" role="status">
                <span className="loading-dot" />
                Loading dated forecasts…
              </div>
            ) : predictions.length ? (
              <div className="game-list">
                {predictions.map((prediction) => (
                  <GameCard
                    key={prediction.game_pk}
                    prediction={prediction}
                    selected={selected === prediction.game_pk}
                    demo={route.demo}
                    onSelect={() => navigate({ ...route, game: prediction.game_pk })}
                  />
                ))}
              </div>
            ) : (
              !slate.error && (
                <div className="slate-empty">
                  <span className="empty-diamond" aria-hidden="true">
                    ◇
                  </span>
                  <h4>No forecasts recorded.</h4>
                  <p>
                    {route.demo
                      ? `This demo contains a slate for ${DEMO_DATE} only.`
                      : 'An empty ledger is not a forecast of no games. Games may be unrecorded, not yet eligible, or outside collection.'}
                  </p>
                </div>
              )
            )}
            <form className="game-lookup" onSubmit={findGame}>
              <label htmlFor="game-id">Find a retained game</label>
              <div>
                <input
                  id="game-id"
                  inputMode="numeric"
                  placeholder="MLB game ID"
                  value={lookup}
                  onChange={(e) => setLookup(e.target.value)}
                />
                <button type="submit" aria-label="Find game">
                  ↗
                </button>
              </div>
              {lookupError && <p role="alert">{lookupError}</p>}
              <p>
                {route.demo
                  ? 'Try 8000001, 8000002, or unrecorded 8000003.'
                  : 'Look up a game even when it has no official forecast.'}
              </p>
            </form>
            <div className="sidebar-note">
              <span className="mini-label">A NOTE ON TIMING</span>
              <p>
                The primary collection window is 20–40 minutes before the saved start. Late and
                backfilled records keep their own labels.
              </p>
            </div>
          </aside>
          <div id="game-detail" className="detail-column" tabIndex={-1} aria-label="Game detail">
            {detail.error && (
              <div className="error-box" role="alert">
                <strong>
                  {detail.data
                    ? 'Refresh failed. This is the previously loaded game record.'
                    : 'Game detail unavailable.'}
                </strong>
                <p>{detail.error}</p>
              </div>
            )}
            {(detail.loading && !detail.data) || (slate.loading && !slate.data && !route.game) ? (
              <section className="empty-detail" role="status">
                <span className="loading-dot" />
                <h3>Opening the notebook…</h3>
                <p>Loading the saved game record.</p>
              </section>
            ) : p ? (
              <>
                <div className="screen-reader-status sr-only" role="status">
                  Loaded {teamName('away', p)} at {teamName('home', p)}.
                </div>
                {p.game_date !== route.date && (
                  <div className="note-box">
                    <strong>This game belongs to {p.game_date}.</strong>
                    <p>
                      The date navigation remains on {route.date}. This lookup is shown separately.
                    </p>
                  </div>
                )}
                <Forecast key={`${mode}:${p.game_pk}`} prediction={p} demo={route.demo} />
              </>
            ) : detail.data?.prediction_status === 'not_recorded' ? (
              <section className="empty-detail">
                <p className="eyebrow">RETAINED GAME · {detail.data.game_pk}</p>
                <h2>No official forecast recorded.</h2>
                <p>
                  This game is known, but no accepted official prediction is retained. A missing
                  prediction is not a zero-run estimate.
                </p>
                {detail.data.latest_discovery && (
                  <p>
                    Latest discovery: {detail.data.latest_discovery.status} · Lineup:{' '}
                    {detail.data.latest_discovery.lineup_state.replaceAll('_', ' ')}.
                  </p>
                )}
              </section>
            ) : (
              !detail.error && (
                <section className="empty-detail">
                  <div className="empty-field" aria-hidden="true">
                    ◇
                  </div>
                  <p className="eyebrow">AN HONEST RECORD</p>
                  <h2>
                    {slate.error ? (
                      'Forecast records are unavailable.'
                    ) : (
                      <>
                        The notebook is open.
                        <br />
                        The ledger is empty.
                      </>
                    )}
                  </h2>
                  <p>
                    {slate.error
                      ? 'Forecast storage is currently unavailable. No sample data will be substituted.'
                      : 'There are no recorded forecasts to show for this date. Explore another date or review an explicitly synthetic demonstration.'}
                  </p>
                  <button
                    className="primary-button"
                    onClick={() => navigate({ date: DEMO_DATE, demo: true })}
                  >
                    Explore the demo <span aria-hidden="true">↗</span>
                  </button>
                  <small>No real forecast or performance claim is created.</small>
                </section>
              )
            )}
          </div>
        </div>

        <section id="model-notes" className="model-notes panel">
          <div className="section-top">
            <div>
              <p className="eyebrow">METHOD, NOT MYSTERY</p>
              <h2>The model notebook</h2>
            </div>
            <span className="pill">Retrospective development evidence</span>
          </div>
          {model.loading && !model.data ? (
            <p role="status">Loading model metadata…</p>
          ) : model.data ? (
            <>
              <p className="model-lead">
                A frozen pregame model. Clear assumptions. An auditable record.
              </p>
              <div className="model-grid">
                <div>
                  <span className="mini-label">MEAN FORECAST</span>
                  <p>{model.data.mean_model}</p>
                </div>
                <div>
                  <span className="mini-label">RUN DISTRIBUTION</span>
                  <p>{model.data.distribution}</p>
                </div>
                <div>
                  <span className="mini-label">WIN CALIBRATION</span>
                  <p>{model.data.calibration}</p>
                </div>
                <div>
                  <span className="mini-label">TRAINING HISTORY</span>
                  <p>
                    {model.data.training_start_season}–{model.data.training_end_season}
                  </p>
                </div>
              </div>
              <details className="data-disclosure">
                <summary>Versions, readiness, and known limitations</summary>
                <dl className="record-list">
                  <div>
                    <dt>Accepted model</dt>
                    <dd className="mono">{model.data.model_version}</dd>
                  </div>
                  <div>
                    <dt>Feature version</dt>
                    <dd className="mono">{model.data.feature_version}</dd>
                  </div>
                  <div>
                    <dt>Calibration version</dt>
                    <dd className="mono">{model.data.calibration_version}</dd>
                  </div>
                  <div>
                    <dt>Artifact</dt>
                    <dd>
                      {route.demo
                        ? 'Not checked in demo mode'
                        : model.data.artifact_status.replaceAll('_', ' ')}
                    </dd>
                  </div>
                </dl>
                {!route.demo && readiness.data?.status === 'not_ready' && (
                  <p>
                    Runtime readiness is incomplete. Database: {readiness.data.database}; artifact:{' '}
                    {readiness.data.artifact}. Saved records can remain readable without a local
                    model binary.
                  </p>
                )}
                <ul>
                  {model.data.known_limitations.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
                <p>
                  No game-specific reliability grade, causal factor attribution, or prospective
                  model success is claimed by this page.
                </p>
              </details>
            </>
          ) : (
            <p>
              Model metadata is unavailable. Existing forecast records keep their own saved
              versions.
            </p>
          )}
          {model.error && (
            <p className="inline-error" role="status">
              Model metadata refresh failed.{' '}
              {model.data ? 'Previously loaded notes remain visible.' : ''}
            </p>
          )}
        </section>
        <footer>
          <span>
            <strong>MLB Game Predictor</strong> · A transparent baseball forecasting project.
          </span>
          <span>Uncertainty belongs in the notebook.</span>
        </footer>
      </main>
    </>
  );
}

function GameCard({
  prediction: p,
  selected,
  demo,
  onSelect,
}: {
  prediction: Prediction;
  selected: boolean;
  demo: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`game-card ${selected ? 'selected' : ''}`}
      aria-pressed={selected}
      aria-controls="game-detail"
      onClick={onSelect}
    >
      <span className="card-kicker">
        {time(p.provenance.scheduled_start_time_utc)}
        <span>{demo ? 'DEMO' : p.provenance.prediction_kind.replaceAll('_', ' ')}</span>
      </span>
      <span className="card-team">
        <span>
          {teamName('away', p)}
          <small>AWAY</small>
        </span>
        <strong>{number(p.away.expected_runs)}</strong>
      </span>
      <span className="card-team">
        <span>
          {teamName('home', p)}
          <small>HOME</small>
        </span>
        <strong>{number(p.home.expected_runs)}</strong>
      </span>
      <span className="card-footer">
        <span>
          {p.confidence.favorite === 'even'
            ? 'Even matchup'
            : `${p.confidence.favorite === 'home' ? 'Home' : 'Away'} win ${pct(p.confidence.favorite_win_probability)}`}
        </span>
        <span>
          Expected runs <span aria-hidden="true">↗</span>
        </span>
      </span>
    </button>
  );
}
