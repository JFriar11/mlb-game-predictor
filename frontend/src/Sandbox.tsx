import { useEffect, useRef, useState, type FormEvent } from 'react';
import { z } from 'zod';
import {
  sandboxCatalogSchema,
  sandboxResultSchema,
  retainedLineupSchema,
  type SandboxInputs,
  type SandboxResult,
} from './contracts';
import { number, pct } from './format';

type Catalog = z.infer<typeof sandboxCatalogSchema>;
type Choice = { id: number; name: string };
type Side = { team: string; starter: string; hitters: string[]; source: string };
const blank = (): Side => ({ team: '', starter: '', hitters: Array(9).fill(''), source: '' });
const label = (p: Choice) => `${p.name} (#${p.id})`;

async function call<T>(
  path: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v1/sandbox/${path}`, {
    method: body ? 'POST' : 'GET',
    signal,
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      response.status === 404 && path === 'catalog'
        ? 'The local lineup sandbox is not enabled. Start it with make sandbox.'
        : error?.error?.message || 'The local prediction service is unavailable.',
    );
  }
  const result = schema.safeParse(await response.json());
  if (!result.success)
    throw new Error('The sandbox response failed validation. No unverified result is displayed.');
  return result.data;
}

export function Sandbox() {
  const [catalog, setCatalog] = useState<Catalog>();
  const [away, setAway] = useState<Side>(blank);
  const [home, setHome] = useState<Side>(blank);
  const [date, setDate] = useState('');
  const [venue, setVenue] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SandboxResult>();
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    call('catalog', sandboxCatalogSchema, controller.signal)
      .then((data) => {
        setCatalog(data);
        setDate(data.default_as_of.slice(0, 10));
        setAway((v) => ({ ...v, team: String(data.teams[0]?.id || '') }));
        setHome((v) => ({ ...v, team: String(data.teams[1]?.id || '') }));
        setVenue(String(data.venues[0]?.id || ''));
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message || 'Cannot reach the local API.');
      });
    return () => {
      controller.abort();
      active.current?.abort();
    };
  }, []);
  function invalidate() {
    generation.current++;
    active.current?.abort();
    setBusy(false);
    setResult(undefined);
    setError('');
  }
  function edit(side: 'away' | 'home', value: Side) {
    invalidate();
    (side === 'away' ? setAway : setHome)({ ...value, source: '' });
  }
  function person(id: number) {
    const value = catalog?.players.find((p) => p.id === id);
    if (!value) throw new Error('A retained player is missing from the local player list.');
    return label(value);
  }
  async function load(side: 'away' | 'home') {
    invalidate();
    const serial = generation.current;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    const value = side === 'away' ? away : home;
    try {
      const seed = await call(
        `lineup?team_id=${value.team}&as_of=${encodeURIComponent(`${date}T00:00:00Z`)}`,
        retainedLineupSchema,
        controller.signal,
      );
      if (serial !== generation.current) return;
      (side === 'away' ? setAway : setHome)({
        ...value,
        starter: person(seed.starter_id),
        hitters: seed.lineup.map(person),
        source: `Retained starting lineup from ${seed.game_date}; editable, not a current roster.`,
      });
      if (side === 'home') setVenue(String(seed.venue_id));
    } catch (e) {
      if (serial === generation.current && !controller.signal.aborted)
        setError(e instanceof Error ? e.message : 'Could not load lineup.');
    } finally {
      if (serial === generation.current) setBusy(false);
    }
  }
  async function predict(event: FormEvent) {
    event.preventDefault();
    invalidate();
    const serial = generation.current;
    const controller = new AbortController();
    active.current = controller;
    const timer = setTimeout(() => controller.abort(), 120_000);
    try {
      const id = (value: string) => {
        const p = catalog?.players.find((p) => label(p) === value);
        if (!p)
          throw new Error('Choose each pitcher and all 18 hitters from the player suggestions.');
        return p.id;
      };
      const inputs: SandboxInputs = {
        as_of: `${date}T00:00:00Z`,
        home_team_id: Number(home.team),
        away_team_id: Number(away.team),
        venue_id: Number(venue),
        home_starter_id: id(home.starter),
        away_starter_id: id(away.starter),
        home_lineup: home.hitters.map(id),
        away_lineup: away.hitters.map(id),
      };
      if (inputs.home_team_id === inputs.away_team_id)
        throw new Error('Choose two different teams.');
      if (new Set([...inputs.home_lineup, ...inputs.away_lineup]).size !== 18)
        throw new Error('Choose 18 different hitters across the two lineups.');
      setBusy(true);
      const output = await call('predict', sandboxResultSchema, controller.signal, inputs);
      if (serial !== generation.current) return;
      if (JSON.stringify(output.inputs) !== JSON.stringify(inputs))
        throw new Error('The result does not match the submitted lineup.');
      setResult(output);
    } catch (e) {
      if (serial === generation.current)
        setError(
          controller.signal.aborted
            ? 'Prediction timed out. Try again after the current calculation finishes.'
            : e instanceof Error
              ? e.message
              : 'Cannot reach the local prediction service.',
        );
    } finally {
      clearTimeout(timer);
      if (serial === generation.current) setBusy(false);
    }
  }
  const name = (team: number) => catalog?.teams.find((t) => t.id === team)?.name || String(team);
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to lineup sandbox
      </a>
      <header className="site-header">
        <div className="header-inner">
          <a className="brand" href="/">
            <span className="brand-mark" aria-hidden="true">
              ◇
            </span>
            <span>
              MLB Game Predictor<small>THE PREGAME NOTEBOOK</small>
            </span>
          </a>
          <nav aria-label="Main navigation">
            <a href="/">Recorded forecasts</a>
            <a href="#sandbox-result">Prediction result</a>
          </nav>
          <span className="service-status demo-status">LOCAL · WHAT IF</span>
        </div>
      </header>
      <main id="main-content" className="page-shell" tabIndex={-1}>
        <section className="intro">
          <div>
            <p className="eyebrow">BASEBALL, EVEN IN THE OFFSEASON</p>
            <h1>
              Lineup sandbox<span>.</span>
            </h1>
            <p>Choose your matchup. Build the lineups. Explore the uncertainty.</p>
          </div>
        </section>
        <div className="note-box" role="note">
          <strong>HYPOTHETICAL · NOT AN OFFICIAL FORECAST</strong>
          <p>
            Uses the frozen model and local history. Results stay on this page and never enter the
            prospective ledger. No current roster or injury updates are fetched.
          </p>
        </div>
        {error && (
          <div className="error-box" role="alert">
            {error}
          </div>
        )}
        {!catalog ? (
          !error && <p role="status">Loading local teams and players…</p>
        ) : (
          <>
            <form onSubmit={predict} className="sandbox-form">
              <section className="panel sandbox-settings">
                <div>
                  <h2>Set the scene</h2>
                  <p>
                    Local history ends {catalog.latest_history_date || 'before any retained games'}.
                    The default cutoff follows the latest retained date. Same-date results are
                    excluded.
                  </p>
                </div>
                <label>
                  History cutoff (UTC date)
                  <input
                    type="date"
                    required
                    min="2026-01-01"
                    max={new Date().toISOString().slice(0, 10)}
                    value={date}
                    onChange={(e) => {
                      invalidate();
                      setDate(e.target.value);
                      setAway((v) => ({ ...v, source: '' }));
                      setHome((v) => ({ ...v, source: '' }));
                    }}
                  />
                </label>
                <label>
                  Ballpark
                  <select
                    required
                    value={venue}
                    onChange={(e) => {
                      invalidate();
                      setVenue(e.target.value);
                    }}
                  >
                    {catalog.venues.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </label>
              </section>
              <div className="sandbox-lineups">
                {(['away', 'home'] as const).map((side) => {
                  const value = side === 'away' ? away : home;
                  return (
                    <fieldset className="panel" key={side}>
                      <legend>{side === 'away' ? 'Away lineup' : 'Home lineup'}</legend>
                      <label>
                        {side === 'away' ? 'Away team' : 'Home team'}
                        <select
                          required
                          value={value.team}
                          onChange={(e) => edit(side, { ...blank(), team: e.target.value })}
                        >
                          {catalog.teams.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        className="outline-button"
                        disabled={busy || !date}
                        onClick={() => load(side)}
                      >
                        Load {side} retained lineup
                      </button>
                      <p className="sandbox-source">
                        {value.source ||
                          'Type a player name and choose a suggestion. Custom combinations are allowed.'}
                      </p>
                      <label>
                        {side === 'away' ? 'Away starting pitcher' : 'Home starting pitcher'}
                        <input
                          required
                          list="sandbox-players"
                          value={value.starter}
                          onChange={(e) => edit(side, { ...value, starter: e.target.value })}
                          placeholder="Search pitcher name"
                          autoComplete="off"
                        />
                      </label>
                      <ol className="sandbox-batters">
                        {value.hitters.map((h, i) => (
                          <li key={i}>
                            <label>
                              <span className="sr-only">
                                {side} hitter {i + 1}
                              </span>
                              <input
                                required
                                list="sandbox-players"
                                value={h}
                                onChange={(e) =>
                                  edit(side, {
                                    ...value,
                                    hitters: value.hitters.map((old, index) =>
                                      index === i ? e.target.value : old,
                                    ),
                                  })
                                }
                                placeholder={`Hitter ${i + 1} · search name`}
                                autoComplete="off"
                              />
                            </label>
                          </li>
                        ))}
                      </ol>
                    </fieldset>
                  );
                })}
              </div>
              <datalist id="sandbox-players">
                {catalog.players.map((p) => (
                  <option key={p.id} value={label(p)} />
                ))}
              </datalist>
              <div className="sandbox-submit">
                <button className="primary-button" type="submit" disabled={busy}>
                  {busy ? 'Working with local history…' : 'Predict this matchup'}{' '}
                  <span aria-hidden="true">↗</span>
                </button>
                <p>All nine hitters matter. Reordering the same nine does not affect this model.</p>
              </div>
            </form>
            <div id="sandbox-result" aria-live="polite" aria-busy={busy}>
              {busy && (
                <p role="status">Reading local history and preparing your hypothetical matchup…</p>
              )}
              {result && (
                <section className="panel sandbox-output">
                  <p className="eyebrow">HYPOTHETICAL RESULT · NOT SAVED</p>
                  <h2>
                    {name(result.inputs.away_team_id)} at {name(result.inputs.home_team_id)}
                  </h2>
                  <p>
                    History cutoff: {result.inputs.as_of.slice(0, 10)} UTC · Latest eligible game:{' '}
                    {result.latest_history_date || 'none'}
                  </p>
                  <div className="sandbox-lineups">
                    {(['away', 'home'] as const).map((side) => {
                      const forecast = result[side];
                      const win =
                        side === 'home'
                          ? result.calibrated_home_win_probability
                          : result.away_win_probability;
                      return (
                        <section key={side}>
                          <h3>
                            {side === 'home' ? 'Home' : 'Away'} ·{' '}
                            {name(result.inputs[`${side}_team_id`])}
                          </h3>
                          <p className="sandbox-runs">
                            {number(forecast.expected_runs)} <small>expected runs</small>
                          </p>
                          <p>
                            <strong>{pct(win)} win probability</strong>
                          </p>
                          <p>
                            80% run range: {forecast.run_ranges['80'].lower}–
                            {forecast.run_ranges['80'].upper}
                            <br />
                            95% run range: {forecast.run_ranges['95'].lower}–
                            {forecast.run_ranges['95'].upper}
                          </p>
                          <details>
                            <summary>{side === 'home' ? 'Home' : 'Away'} run distribution</summary>
                            <table className="sandbox-distribution">
                              <thead>
                                <tr>
                                  <th>Runs</th>
                                  <th>Probability</th>
                                </tr>
                              </thead>
                              <tbody>
                                {forecast.run_distribution.probabilities.map((p, i) => (
                                  <tr key={i}>
                                    <th>{i === 12 ? '12+' : i}</th>
                                    <td>
                                      <div className="sandbox-probability">
                                        <span style={{ width: `${p * 100}%` }} />
                                      </div>
                                      {pct(p)}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            <p>
                              12+ includes all scores of 12 or more. Run ranges use uncensored count
                              quantiles, not measured coverage.
                            </p>
                          </details>
                        </section>
                      );
                    })}
                  </div>
                  <h3>Most likely score combinations</h3>
                  <p>
                    Away–home:{' '}
                    {result.most_likely_score_bins
                      .map(
                        (s) => `${s.away_run_bucket}–${s.home_run_bucket} (${pct(s.probability)})`,
                      )
                      .join(' · ')}
                  </p>
                  <h3>Input quality and confidence</h3>
                  <p>{result.confidence.note}</p>
                  <p>{result.confidence.input_quality.note}</p>
                  <ul>
                    {result.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                  <details>
                    <summary>Baseball inputs behind this result</summary>
                    <p>{result.explanation.note}</p>
                    <div className="sandbox-table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Offense</th>
                            <th>Input</th>
                            <th>Raw</th>
                            <th>Model</th>
                            <th>History</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.explanation.factors.map((f) => (
                            <tr key={`${f.offense_side}-${f.feature}`}>
                              <td>{f.offense_side}</td>
                              <th>{f.label}</th>
                              <td>{number(f.raw_value)}</td>
                              <td>{number(f.model_value)}</td>
                              <td>
                                {f.sample_size ?? '—'} {f.sample_unit}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                  <p className="sandbox-source">
                    Model: {result.model_version}. Calibration evidence is retrospective, not
                    validation of custom lineups. Editing an input clears this result.
                  </p>
                </section>
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
