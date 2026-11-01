import { useState } from 'react';
import type { Prediction } from './contracts';
import { number, pct, teamName, time } from './format';

export function Forecast({ prediction: p, demo }: { prediction: Prediction; demo: boolean }) {
  const [interval, setInterval] = useState<'80' | '95'>('80');
  const [offense, setOffense] = useState<'home' | 'away'>('home');
  const home = teamName('home', p),
    away = teamName('away', p);
  const quality = p.confidence.input_quality;
  return (
    <>
      <div className="detail-heading">
        <div>
          <p className="eyebrow">
            FORECAST NOTEBOOK <span> / {demo ? 'DEMO' : `MLB ${p.game_pk}`}</span>
          </p>
          <h2>
            {away} <span>at</span> {home}
          </h2>
          <p className="muted">
            {p.latest_discovery?.venue_name ?? 'Venue not retained'}{' '}
            <span aria-hidden="true"> · </span>
            Saved start {time(p.provenance.scheduled_start_time_utc, true)}
          </p>
        </div>
        <span className="pill">
          {demo
            ? 'Illustrative forecast'
            : p.observed_outcome
              ? 'Settled record'
              : 'Pregame record'}
        </span>
      </div>

      <section
        className="forecast-hero"
        aria-label="Expected runs and calibrated win probabilities"
      >
        <div className="hero-team">
          <p className="eyebrow">AWAY</p>
          <h3>{away}</h3>
          <strong className="run-number">{number(p.away.expected_runs)}</strong>
          <span>expected runs</span>
        </div>
        <div className="versus" aria-hidden="true">
          ◇
        </div>
        <div className="hero-team home">
          <p className="eyebrow">HOME</p>
          <h3>{home}</h3>
          <strong className="run-number">{number(p.home.expected_runs)}</strong>
          <span>expected runs</span>
        </div>
        <div className="win-strip">
          <div>
            <span>{away}</span>
            <strong>{pct(p.away_win_probability)}</strong>
          </div>
          <p>CALIBRATED WIN PROBABILITY</p>
          <div>
            <span>{home}</span>
            <strong>{pct(p.calibrated_home_win_probability)}</strong>
          </div>
          <div className="probability-track" aria-hidden="true">
            <span style={{ width: pct(p.away_win_probability) }} />
          </div>
        </div>
        <p className="hero-note">
          Expected runs are averages, not a predicted final score. Win probability includes the
          extra-inning approximation.
        </p>
      </section>

      <section className="panel range-panel" aria-labelledby="ranges-title">
        <div className="section-top">
          <div>
            <p className="eyebrow">THE RANGE OF OUTCOMES</p>
            <h3 id="ranges-title">Leave room for baseball.</h3>
          </div>
          <div className="segmented" role="group" aria-label="Run range level">
            {(['80', '95'] as const).map((level) => (
              <button
                key={level}
                aria-pressed={interval === level}
                onClick={() => setInterval(level)}
              >
                {level}% range
              </button>
            ))}
          </div>
        </div>
        <div className="range-grid">
          {(['away', 'home'] as const).map((side) => (
            <div key={side}>
              <span>{side === 'away' ? away : home}</span>
              <strong>
                {p.run_ranges[side][interval].lower}
                <span>—</span>
                {p.run_ranges[side][interval].upper}
                <small> runs</small>
              </strong>
              <p>Model probability within range: {pct(p.run_ranges[side][interval].model_mass)}</p>
            </div>
          ))}
        </div>
        <p className="caption">
          Uncensored, equal-tailed count ranges. The nominal level is not a measured guarantee of
          real-world coverage.
        </p>
      </section>

      <section className="panel" aria-labelledby="distribution-title">
        <div className="section-top">
          <div>
            <p className="eyebrow">EVERY RUN COUNTS</p>
            <h3 id="distribution-title">Run distributions</h3>
          </div>
          <div className="legend">
            <span className="away-dot" />
            Away <span className="home-dot" />
            Home
          </div>
        </div>
        <Distribution prediction={p} />
        <p className="caption">
          The final bucket is <strong>12 or more</strong> runs. It is not an exact score of 12.
        </p>
        <details className="data-disclosure">
          <summary>Read the probability table</summary>
          <div className="table-scroll">
            <table>
              <caption>Team run probabilities, including the censored 12+ bucket</caption>
              <thead>
                <tr>
                  <th scope="col">Runs</th>
                  <th scope="col">{away}</th>
                  <th scope="col">{home}</th>
                </tr>
              </thead>
              <tbody>
                {p.home.run_distribution.labels.map((label, i) => (
                  <tr key={label}>
                    <th scope="row">{label}</th>
                    <td>{pct(p.away.run_distribution.probabilities[i])}</td>
                    <td>{pct(p.home.run_distribution.probabilities[i])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="panel" aria-labelledby="evidence-title">
        <div className="section-top">
          <div>
            <p className="eyebrow">BEHIND THE FORECAST</p>
            <h3 id="evidence-title">Pregame input evidence</h3>
          </div>
          {p.explanation.status === 'available' && (
            <div className="segmented" role="group" aria-label="Offense input evidence">
              {(['away', 'home'] as const).map((side) => (
                <button key={side} aria-pressed={offense === side} onClick={() => setOffense(side)}>
                  {side === 'away' ? 'Away offense' : 'Home offense'}
                </button>
              ))}
            </div>
          )}
        </div>
        {p.explanation.status === 'not_retained' ? (
          <div className="note-box">
            <strong>Input evidence was not retained.</strong>
            <p>
              This forecast is still available, but its original inputs cannot be reconstructed
              honestly from later data.
            </p>
          </div>
        ) : (
          <>
            <p className="caption">
              {offense === 'home' ? home : away} offense. Pitching factors describe the{' '}
              <strong>opposing</strong> starter and bullpen. Fixed-order summaries, not causal
              effects or ranked run contributions.
            </p>
            <div className="factor-grid">
              {p.explanation.factors
                .filter((f) => f.offense_side === offense)
                .map((f) => (
                  <article className="factor" key={f.feature}>
                    <h4>{f.label}</h4>
                    <div className="factor-value">
                      {f.unit === 'rate' ? pct(f.model_value) : number(f.model_value, 2)}
                      <small>{f.unit === 'rate' ? 'stabilized rate' : f.unit}</small>
                    </div>
                    <p>
                      Raw: {f.unit === 'rate' ? pct(f.raw_value) : number(f.raw_value, 2)} ·{' '}
                      {f.sample_size === null
                        ? 'Exact sample count not retained'
                        : `${f.sample_size.toLocaleString()} prior ${f.sample_unit}`}
                    </p>
                    <details>
                      <summary>How to read this input</summary>
                      <p>{f.note}</p>
                    </details>
                  </article>
                ))}
            </div>
            <details className="data-disclosure">
              <summary>Captured lineup IDs and cutoff</summary>
              <p>
                Feature cutoff:{' '}
                {p.explanation.as_of ? time(p.explanation.as_of, true) : 'Not retained'}
              </p>
              <p>Away MLB player IDs: {p.explanation.away_lineup?.join(', ') ?? 'Not retained'}</p>
              <p>Home MLB player IDs: {p.explanation.home_lineup?.join(', ') ?? 'Not retained'}</p>
            </details>
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="confidence-title">
        <p className="eyebrow">CONFIDENCE, WITH CONTEXT</p>
        <h3 id="confidence-title">Probability is only part of the picture.</h3>
        <div className="confidence-grid">
          <article>
            <span className="mini-label">OUTCOME FORECAST</span>
            <strong>{pct(p.confidence.favorite_win_probability)}</strong>
            <p>
              {p.confidence.favorite === 'even'
                ? 'Even matchup'
                : `${p.confidence.favorite === 'home' ? home : away} win probability`}
              . This is not a reliability score.
            </p>
          </article>
          <article>
            <span className="mini-label">RECORDED INPUT QUALITY</span>
            <strong className="quality-word">
              {quality.status === 'limited'
                ? 'Limited inputs'
                : quality.status === 'unknown'
                  ? 'Unknown'
                  : 'No recorded limitations'}
            </strong>
            <p>
              {quality.fallback_counts
                ? `Fallback flags: away ${quality.fallback_counts.away}, home ${quality.fallback_counts.home}.`
                : 'Original input evidence is missing.'}{' '}
              No recorded limitations does not certify complete or current data.
            </p>
          </article>
        </div>
        {quality.recorded_warnings.length > 0 && (
          <p className="recorded-warnings">
            <strong>Recorded warnings:</strong>{' '}
            {quality.recorded_warnings.map((w) => w.replaceAll('_', ' ')).join(' · ')}
          </p>
        )}
        <details className="data-disclosure">
          <summary>Retrospective calibration evidence</summary>
          <p>
            {p.confidence.calibration.evaluated_games.toLocaleString()} games across{' '}
            {p.confidence.calibration.evaluation_seasons.join(', ')}. Reviewed development evidence;
            not prospective validation.
          </p>
          <dl className="metrics">
            <div>
              <dt>Brier score</dt>
              <dd>{number(p.confidence.calibration.brier_score, 5)}</dd>
            </div>
            <div>
              <dt>Log loss</dt>
              <dd>{number(p.confidence.calibration.log_loss, 5)}</dd>
            </div>
            <div>
              <dt>Expected calibration error</dt>
              <dd>{number(p.confidence.calibration.expected_calibration_error, 5)}</dd>
            </div>
          </dl>
          <p>{p.confidence.calibration.note}</p>
          <p>
            Game-specific reliability has not been estimated. There is no combined confidence grade.
          </p>
        </details>
      </section>

      <div className="detail-bottom-grid">
        <section className="panel" aria-labelledby="scores-title">
          <p className="eyebrow">JOINT SCORING CATEGORIES</p>
          <h3 id="scores-title">Likely score bins</h3>
          <table className="score-table">
            <caption className="sr-only">
              Independent scoring categories, not resolved final scores
            </caption>
            <thead>
              <tr>
                <th scope="col">Away</th>
                <th scope="col">Home</th>
                <th scope="col">Probability</th>
              </tr>
            </thead>
            <tbody>
              {p.most_likely_score_bins.map((score, i) => (
                <tr key={i}>
                  <td>{score.away_run_bucket}</td>
                  <td>{score.home_run_bucket}</td>
                  <td>{pct(score.probability)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="caption">
            Tied categories are possible. These are not resolved final scores; calibrated wins are
            calculated separately.
          </p>
        </section>
        <section className="panel" aria-labelledby="record-title">
          <p className="eyebrow">THE ORIGINAL RECORD</p>
          <h3 id="record-title">Timing & provenance</h3>
          <dl className="record-list">
            <div>
              <dt>Prediction recorded</dt>
              <dd>{time(p.provenance.prediction_timestamp, true)}</dd>
            </div>
            <div>
              <dt>Feature cutoff</dt>
              <dd>{time(p.provenance.feature_cutoff_timestamp, true)}</dd>
            </div>
            <div>
              <dt>Source retrieved</dt>
              <dd>{time(p.provenance.source_retrieved_at, true)}</dd>
            </div>
            <div>
              <dt>Before saved start</dt>
              <dd>{number(p.provenance.minutes_before_scheduled_start)} minutes</dd>
            </div>
            <div>
              <dt>Record class</dt>
              <dd>{p.provenance.prediction_kind.replaceAll('_', ' ')}</dd>
            </div>
            <div>
              <dt>Timing class</dt>
              <dd>{p.provenance.timing_classification.replaceAll('_', ' ')}</dd>
            </div>
            <div>
              <dt>Game date basis</dt>
              <dd>
                {p.date_basis === 'mlb_official_date'
                  ? 'Latest MLB official date'
                  : 'Saved start date, UTC fallback'}
              </dd>
            </div>
          </dl>
          <details className="data-disclosure">
            <summary>Versions & starter IDs</summary>
            <dl className="record-list">
              {(
                [
                  'model_version',
                  'feature_version',
                  'calibration_version',
                  'distribution_version',
                  'code_version',
                ] as const
              ).map((key) => (
                <div key={key}>
                  <dt>{key.replaceAll('_', ' ')}</dt>
                  <dd className="mono">{p.provenance[key]}</dd>
                </div>
              ))}
              <div>
                <dt>Away / home starter IDs</dt>
                <dd>
                  {p.provenance.away_starter_id ?? 'Not retained'} /{' '}
                  {p.provenance.home_starter_id ?? 'Not retained'}
                </dd>
              </div>
            </dl>
          </details>
        </section>
      </div>
      {p.observed_outcome && (
        <section className="panel settlement">
          <p className="eyebrow">OBSERVED OUTCOME · SEPARATE FROM THE FORECAST</p>
          <h3>
            {away} {p.observed_outcome.away_team_runs} — {home} {p.observed_outcome.home_team_runs}
          </h3>
          <p>
            {p.observed_outcome.completion_status ?? 'Outcome recorded'} · Retrieved{' '}
            {time(p.observed_outcome.observed_at, true)}. The saved forecast above has not been
            replaced by this result.
          </p>
        </section>
      )}
      {p.latest_discovery && (
        <p className="caption discovery-note">
          Latest discovery: {p.latest_discovery.status} · Retrieved{' '}
          {time(p.latest_discovery.source_retrieved_at, true)}. Schedule and team context can
          change; the saved forecast timing above is retained.
        </p>
      )}
    </>
  );
}

function Distribution({ prediction: p }: { prediction: Prediction }) {
  const maximum = Math.max(
    ...p.home.run_distribution.probabilities,
    ...p.away.run_distribution.probabilities,
    0.05,
  );
  const chartHeight = 150,
    baseline = 180,
    width = 650,
    left = 42,
    group = 44;
  return (
    <svg
      className="distribution-chart"
      viewBox={`0 0 ${width} 215`}
      role="img"
      aria-label="Away and home probability distributions for zero through 12 or more runs. Exact values are in the expandable probability table."
    >
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line
            x1={left}
            x2="622"
            y1={baseline - f * chartHeight}
            y2={baseline - f * chartHeight}
            stroke="#d9dfd8"
            strokeDasharray={f ? '3 4' : undefined}
          />
          <text x="32" y={baseline - f * chartHeight + 4} textAnchor="end">
            {Math.round(maximum * f * 100)}%
          </text>
        </g>
      ))}
      {p.home.run_distribution.labels.map((label, i) => (
        <g key={label}>
          <rect
            className="away-bar"
            x={left + i * group + 4}
            y={baseline - (p.away.run_distribution.probabilities[i] / maximum) * chartHeight}
            width="14"
            height={(p.away.run_distribution.probabilities[i] / maximum) * chartHeight}
          >
            <title>
              Away {label} runs: {pct(p.away.run_distribution.probabilities[i])}
            </title>
          </rect>
          <rect
            className="home-bar"
            x={left + i * group + 21}
            y={baseline - (p.home.run_distribution.probabilities[i] / maximum) * chartHeight}
            width="14"
            height={(p.home.run_distribution.probabilities[i] / maximum) * chartHeight}
          >
            <title>
              Home {label} runs: {pct(p.home.run_distribution.probabilities[i])}
            </title>
          </rect>
          <text x={left + i * group + 19} y="201" textAnchor="middle">
            {label}
          </text>
        </g>
      ))}
    </svg>
  );
}
