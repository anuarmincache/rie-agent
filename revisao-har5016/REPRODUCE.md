# Revision of har5016 (J. Appl. Cryst.): new refinements

Date of the runs: 2026-11-24. Instrument: Shimadzu XRD-6100, Bragg-Brentano, goniometer radius 185 mm, glass holder.

## Environment
- GSAS-II: main branch, commit `46b3d7b541d344f9506848c37b35737b1a87ddac` (14 Nov 2026), with its prebuilt binaries.
- Python 3.12.3, NumPy 2.2.6, `--no-llm` (rule-based planner) in every run.
- The commit used in the first submission (262382a8) could not be fetched. The recipe A numbers of the first version were reproduced with this installation to within 0.003 in array Rwp.

## Recipes (names as in the paper)
| Recipe | Log prefix | Description |
|---|---|---|
| A | `leg_` | Transferred profile and Zero, no displacement (first version). |
| B | `legshift_` | Recipe A plus refined sample displacement. |
| C | `noshift_` | Zero = 0, X = Y = 0, size and microstrain refined, displacement held at 0. |
| D | `r1_` | Zero = 0, X = Y = 0, size, microstrain and displacement refined, 12 starts. |

Recipe C was run only at x = 0.10, 0.15 and 0.20. Recipe A at x = 0.025 and 0.05 is `base25_` and `base_Nd5_` (no Nd in the model). `base_Nd10/15/20_` repeat recipe A with the installation above. The recipe A column of the paper's Table 2 holds the values as submitted (hard-coded in `tabelas/make_tables.py`: 9.852, 10.133, 10.907, 12.614, 21.640). The reruns give 9.852, 10.133, 10.908, 12.612 and 21.638.

## Commands
`runs_todos.sh` collects the shell scripts used. The core call for recipe D is
`python src/agent.py data/samples/<pattern>.xye data/samples/BFO.cif data/instrument/shimadzu_nd_provisorio.instprm --outdir OUT --label r1_x<x> --nd <x> --no-llm --protocol r1 --gonio-radius 185`.
Free-profile test: `tools/polish_free.py`. Validator sensitivity: `tools/threshold_sensitivity.py`.
Tables and figures: `tabelas/make_tables.py`, `tabelas/make_figs.py` (they read the logs and projects).

## Changes in the code
- `src/recipe_r1.py` (new): recipe D, 12-start search, metrics.
- `src/agent.py`: `--protocol`, `--gonio-radius`; the Bi/Nd Uiso tie is now saved (`gpx.save()`), which fixed a loss of the constraint on reload. The first-version numbers are unchanged by this fix.
- `src/validators.py`: the size and microstrain correlation is reported and does not block acceptance.
- `src/recipe.py`: optional `displacement` stage.
