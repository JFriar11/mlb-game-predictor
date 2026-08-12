# Sprint 5.5 Downstream Pitching-State Ablation

**Completed:** 2026-08-12  
**Baseline:** immutable `sprint3_5_v1`  
**Components:** existing `sprint5_v1`  
**Decision:** promote none; create no new version

## Fixed protocol

Before evaluation, Sprint 5.5 fixed eleven additions: expected starter outs; expected
starter pitches; both; starter rest/workload/history; recent bullpen workload; reliever
availability counts; available-reliever quality; expected bullpen outs; a compact starter
group; a compact bullpen group; and both compact groups. The accepted Poisson-loss
histogram gradient booster and rolling origins (train prior seasons, evaluate 2022–2025)
were unchanged. Poisson deviance was the sole promotion metric.

Slice thresholds were also fixed: short starter projection under 15 outs, high bullpen
workload at least 50 pitches over the prior three days, and low starter history under five
starts. The workload split proved imbalanced (18,935 high versus 503 low), which limits
interpretation but was not retuned after inspection.

## Overall results

| Addition | MAE | RMSE | Bias | Poisson deviance | Count NLL | Deviance change |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 2.4488 | 3.1304 | -0.0387 | 2.27647 | 2.64698 | — |
| Expected starter outs | 2.4507 | 3.1303 | -0.0333 | 2.27590 | 2.64670 | -0.00057 |
| Expected starter pitches | 2.4506 | 3.1302 | -0.0353 | 2.27563 | 2.64656 | -0.00084 |
| Starter outs + pitches | 2.4503 | 3.1302 | -0.0297 | 2.27577 | 2.64663 | -0.00070 |
| Starter rest/workload/history | 2.4512 | 3.1320 | -0.0388 | 2.27877 | 2.64813 | +0.00230 |
| Bullpen recent workload | 2.4507 | 3.1299 | -0.0347 | 2.27605 | 2.64677 | -0.00042 |
| Reliever availability counts | 2.4419 | 3.1350 | -0.1167 | 2.28534 | 2.65142 | +0.00887 |
| Available-reliever quality | 2.4488 | 3.1282 | -0.0201 | **2.27310** | **2.64530** | **-0.00337** |
| Expected bullpen outs | 2.4540 | 3.1325 | -0.0217 | 2.27900 | 2.64825 | +0.00254 |
| Compact starter group | 2.4500 | 3.1308 | -0.0307 | 2.27688 | 2.64719 | +0.00041 |
| Compact bullpen group | 2.4448 | 3.1295 | -0.0663 | 2.27669 | 2.64709 | +0.00022 |
| Both compact groups | 2.4420 | 3.1300 | -0.0826 | 2.27758 | 2.64754 | +0.00112 |

Small negative changes for isolated starter/workload features are not treated as clear
improvements. Every logical compact group worsened the primary metric.

## Season stability

Available-reliever quality changed Poisson deviance versus baseline by approximately:

- 2022: `-0.01924`
- 2023: `+0.00150`
- 2024: `+0.00194`
- 2025: `+0.00232`

Thus its combined gain is concentrated in the earliest evaluation origin and does not
replicate across later seasons. It is not promoted.

## Slice findings for the leading candidate

Available-reliever quality improved Poisson deviance within every requested combined
slice versus baseline:

- Long/short starter projections: `-0.00410` / `-0.00126`
- High/low bullpen workload: `-0.00200` / `-0.05516`
- High/low starter history: `-0.00158` / `-0.01745`
- Away/home offense: `-0.00589` / `-0.00085`

The low-workload slice contains only 503 rows and must not drive promotion. Away-offense
and long-outing effects are larger, but season instability remains the governing result.

## Decision and limitations

No Sprint 5 feature is promoted into the run model and no new feature/model version is
created. `sprint3_5_v1` remains the accepted run-model baseline. Expected length, workload,
availability, and quality fields remain useful component outputs. Available-reliever
quality is the only credible candidate for confirmation on prospective or newly locked
data.

All 2021–2025 results remain repeatedly reviewed retrospective development evidence.
Historical role and availability fields remain workload proxies without transactions,
injuries, warm-up status, or manager declarations.

## Reproduction

```bash
make sprint5-5-audit
```

Artifacts are written under ignored `data/processed/sprint5_5/`. The command performs no
raw ingestion and does not rebuild or tune Sprint 5 component models.
