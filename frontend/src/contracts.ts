import { z } from 'zod';

const probability = z.number().finite().min(0).max(1);
const finite = z.number().finite();
const timestamp = z.iso.datetime({ offset: true });
const count = z.number().int().nonnegative();
const range = z
  .object({ lower: count, upper: count, nominal_mass: probability, model_mass: probability })
  .refine((v) => v.lower <= v.upper, 'Invalid run range');
const ranges = z.object({ '80': range, '95': range });
const distribution = z
  .object({
    probabilities: z.array(probability).length(13),
    labels: z.array(z.string()).length(13),
    terminal_bucket_lower_bound: z.literal(12),
    terminal_bucket_is_censored: z.literal(true),
  })
  .refine(
    (v) =>
      Math.abs(v.probabilities.reduce((a, b) => a + b, 0) - 1) < 1e-6 &&
      v.labels.every((label, i) => label === (i === 12 ? '12+' : String(i))),
    'Invalid run distribution',
  );
const team = z.object({ expected_runs: finite.nonnegative(), run_distribution: distribution });
const context = z.object({
  game_date: z.iso.date(),
  home_team_id: count,
  away_team_id: count,
  home_team_name: z.string(),
  away_team_name: z.string(),
  venue_name: z.string().nullable(),
  scheduled_start_time_utc: timestamp,
  status: z.string(),
  lineup_state: z.string(),
  source: z.string(),
  source_retrieved_at: timestamp,
});
const factor = z.object({
  offense_side: z.enum(['home', 'away']),
  feature: z.string(),
  label: z.string(),
  raw_value: finite,
  model_value: finite,
  unit: z.string(),
  sample_size: count.nullable(),
  sample_unit: z.string().nullable(),
  note: z.string(),
});
export const predictionSchema = z
  .object({
    record_id: count,
    game_pk: z.number().int().positive(),
    game_date: z.iso.date(),
    date_basis: z.enum(['mlb_official_date', 'scheduled_start_utc']),
    latest_discovery: context.nullable(),
    home: team,
    away: team,
    calibrated_home_win_probability: probability,
    raw_home_win_probability: probability,
    away_win_probability: probability,
    regulation_tie_probability: probability,
    extra_inning_home_win_probability: probability,
    dispersion: finite.nonnegative(),
    most_likely_score_bins: z.array(
      z.object({
        home_run_bucket: z.string().regex(/^(?:[0-9]|1[01]|12\+)$/),
        away_run_bucket: z.string().regex(/^(?:[0-9]|1[01]|12\+)$/),
        probability,
      }),
    ),
    data_quality_warnings: z.array(z.string()),
    provenance: z.object({
      prediction_timestamp: timestamp,
      scheduled_start_time_utc: timestamp,
      feature_cutoff_timestamp: timestamp,
      source_retrieved_at: timestamp,
      model_version: z.string(),
      feature_version: z.string(),
      calibration_version: z.string(),
      distribution_version: z.string(),
      code_version: z.string(),
      lineup_confirmation_state: z.string(),
      home_starter_id: count.nullable(),
      away_starter_id: count.nullable(),
      prediction_kind: z.string(),
      timing_classification: z.string(),
      minutes_before_scheduled_start: finite,
      is_official: z.literal(true),
    }),
    observed_outcome: z
      .object({
        home_team_runs: count,
        away_team_runs: count,
        completion_status: z.string().nullable(),
        observed_at: timestamp,
        actual_start_time_utc: timestamp.nullable(),
      })
      .nullable(),
    explanation: z.object({
      status: z.enum(['available', 'not_retained']),
      as_of: timestamp.nullable(),
      snapshot_version: z.string().nullable(),
      home_lineup: z.array(count).nullable(),
      away_lineup: z.array(count).nullable(),
      home_team_id: count.nullable(),
      away_team_id: count.nullable(),
      factors: z.array(factor),
      note: z.string(),
    }),
    confidence: z.object({
      favorite: z.enum(['home', 'away', 'even']),
      favorite_win_probability: probability,
      probability_margin_over_even: finite.min(0).max(0.5),
      note: z.string(),
      input_quality: z.object({
        status: z.enum(['unknown', 'limited', 'no_recorded_limitations']),
        fallback_counts: z.object({ home: count, away: count }).nullable(),
        recorded_warnings: z.array(z.string()),
        note: z.string(),
      }),
      calibration: z.object({
        scope: z.literal('retrospective_development'),
        evaluation_seasons: z.array(count),
        evaluated_games: count,
        brier_score: finite.nonnegative(),
        log_loss: finite.nonnegative(),
        expected_calibration_error: probability,
        local_reliability: z.literal('not_estimated'),
        source_report: z.string(),
        note: z.string(),
      }),
    }),
    run_ranges: z.object({ home: ranges, away: ranges, note: z.string() }),
  })
  .passthrough()
  .refine(
    (v) => Math.abs(v.calibrated_home_win_probability + v.away_win_probability - 1) < 1e-6,
    'Invalid complementary probabilities',
  );

export const slateSchema = z
  .object({
    date: z.iso.date(),
    model_version: z.string(),
    generated_at: timestamp,
    count,
    predictions: z.array(predictionSchema),
  })
  .refine(
    (v) => v.count === v.predictions.length && v.predictions.every((p) => p.game_date === v.date),
    'Inconsistent dated forecasts',
  );
export const detailSchema = z
  .object({
    game_pk: z.number().int().positive(),
    model_version: z.string(),
    prediction_status: z.enum(['available', 'not_recorded']),
    latest_discovery: context.nullable(),
    official_prediction: predictionSchema.nullable(),
  })
  .refine(
    (v) =>
      (v.prediction_status === 'available') === (v.official_prediction !== null) &&
      (!v.official_prediction || v.official_prediction.game_pk === v.game_pk),
    'Inconsistent game detail',
  );
export const modelSchema = z.object({
  model_version: z.string(),
  feature_version: z.string(),
  calibration_version: z.string(),
  distribution_version: z.string(),
  mean_model: z.string(),
  distribution: z.string(),
  calibration: z.string(),
  training_start_season: count,
  training_end_season: count,
  retrospective_evidence_only: z.boolean(),
  artifact_sha256_expected: z.string(),
  artifact_status: z.enum(['verified', 'missing', 'checksum_mismatch', 'unreadable']),
  known_limitations: z.array(z.string()),
});
export const readinessSchema = z.object({
  status: z.enum(['ready', 'not_ready']),
  database: z.enum(['ready', 'unavailable']),
  artifact: z.enum(['verified', 'missing', 'checksum_mismatch', 'unreadable']),
});
export type Prediction = z.infer<typeof predictionSchema>;
export type Slate = z.infer<typeof slateSchema>;
export type Detail = z.infer<typeof detailSchema>;
export type Model = z.infer<typeof modelSchema>;
export type Readiness = z.infer<typeof readinessSchema>;

const choiceSchema = z.object({ id: z.number().int().positive(), name: z.string() });
export const sandboxCatalogSchema = z.object({
  teams: z.array(choiceSchema),
  players: z.array(choiceSchema),
  venues: z.array(choiceSchema),
  latest_history_date: z.iso.date().nullable(),
  default_as_of: timestamp,
});
export const retainedLineupSchema = z.object({
  game_date: z.iso.date(),
  lineup: z.array(z.number().int().positive()).length(9),
  starter_id: z.number().int().positive(),
  venue_id: z.number().int().positive(),
});
export const sandboxInputsSchema = z.object({
  as_of: timestamp,
  home_team_id: z.number().int().positive(),
  away_team_id: z.number().int().positive(),
  venue_id: z.number().int().positive(),
  home_starter_id: z.number().int().positive(),
  away_starter_id: z.number().int().positive(),
  home_lineup: z.array(z.number().int().positive()).length(9),
  away_lineup: z.array(z.number().int().positive()).length(9),
});
export const sandboxResultSchema = z
  .object({
    kind: z.literal('hypothetical'),
    is_official: z.literal(false),
    saved: z.literal(false),
    model_version: z.string(),
    artifact_sha256: z.string(),
    generated_at: timestamp,
    inputs: sandboxInputsSchema,
    latest_history_date: z.iso.date().nullable(),
    home: team.extend({ run_ranges: ranges }),
    away: team.extend({ run_ranges: ranges }),
    calibrated_home_win_probability: probability,
    away_win_probability: probability,
    most_likely_score_bins: predictionSchema.shape.most_likely_score_bins,
    warnings: z.array(z.string()),
    explanation: predictionSchema.shape.explanation,
    confidence: predictionSchema.shape.confidence,
  })
  .refine((v) => Math.abs(v.calibrated_home_win_probability + v.away_win_probability - 1) < 1e-6);
export type SandboxInputs = z.infer<typeof sandboxInputsSchema>;
export type SandboxResult = z.infer<typeof sandboxResultSchema>;
