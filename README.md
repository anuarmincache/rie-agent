<div align="center">

<img src="assets/rie-agent-banner.svg" alt="rie-agent — physics-guided Rietveld refinement" width="100%" />

<br />

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](docs/SETUP.md)
[![GSAS-II](https://img.shields.io/badge/Engine-GSAS--II-215C7A)](https://github.com/AdvancedPhotonSource/GSAS-II)
[![License: MIT](https://img.shields.io/badge/License-MIT-16A085)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20development-F59E0B)](docs/ROADMAP.md)
[![Roadmap](https://img.shields.io/badge/Roadmap-Sprint%203-5865F2)](docs/ROADMAP.md)

**A research-oriented agent for staged, physically validated Rietveld refinement.**

[Architecture](#architecture) · [Getting started](#getting-started) · [Development roadmap](docs/ROADMAP.md) · [Setup notes](docs/SETUP.md)

</div>

---

## Overview

**rie-agent** combines [GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) numerical refinement with a constrained planning layer. The refinement engine computes the parameters; deterministic checks evaluate whether a stage is acceptable. An optional local LLM proposes remediation actions but does **not** decide numerical validity.

The primary research context is Nd-substituted BiFeO₃ powder diffraction. The codebase is being developed and benchmarked; it is **not** a validated turnkey refinement service.

## Architecture

```text
Powder diffraction + CIF + instrument parameters
                     |
                     v
             GSAS-II refinement
                     |
                     v
         Deterministic validation
             /               \
          Accept             Reject
            |                   |
        Next stage       Restore checkpoint
                                |
                         Planner suggests
                         remediation action
                                |
                         Retry and validate
```

| Component | Responsibility | Source |
| --- | --- | --- |
| Lab recipe | Stage order and locks for the BiFeO₃ lab scan: Bi1 origin, profile terms, uniaxial size | [`src/recipe.py`](src/recipe.py) |
| Staged refinement | Scale/background, cell, profile, atomic positions and thermal parameters | [`src/refine_staged.py`](src/refine_staged.py) |
| Agent orchestration | Stage progression, checkpoint/rollback and remediation; local Ollama or rule-based fallback | [`src/agent.py`](src/agent.py) |
| Physical validation | Explicit checks on refinement quality and physical parameter constraints | [`src/validators.py`](src/validators.py) |
| Secondary-phase investigation | Residual-peak screening and isolated candidate-phase scale trials | [`src/phase_hunter.py`](src/phase_hunter.py) |

### Design principles

- **Physics before model judgment:** acceptance and rejection rely on explicit checks, not LLM-generated scores.
- **Traceable stages:** refinement progress and decisions are recorded for inspection.
- **Reversible experiments:** rejected trials can return to a prior accepted state.
- **Constrained AI:** optional Ollama planning selects from supported actions; rules provide a fallback.
- **Conservative phase screening:** candidate phases are trialed on copies of the project, with deterministic acceptance criteria.

## Getting started

Development environment documented for **Windows 11 + WSL2 / Ubuntu 24.04**, Conda, Python 3.12 and GSAS-II installed from source. Follow the [full setup guide](docs/SETUP.md) for binary and dependency details.

```bash
conda activate rie-agent
export GSASII_PATH="$HOME/GSAS-II"
python src/agent.py DATA.xye PHASE.cif INSTRUMENT.instprm --outdir results --label trial
```

For a rule-only run without Ollama, append `--no-llm`. Replace the example filenames with your own compatible diffraction, CIF and instrument files. This command is a development entry point, not a guarantee of convergence.

The Nd2.5 regression uses a provisional instrument transferred from the hand refinement in `results/agent_llm.gpx`. It is a transfer of that fit, not a Si or LaB₆ calibration. A filename containing `provisorio`, or the flag `--fixed-instrument`, holds U, V, W, X, Y, Zero and SH/L fixed while the sample parameters still refine.

```bash
python src/agent.py data/samples/Nd2p5_850.xye data/samples/BFO.cif \
  data/instrument/shimadzu_nd_provisorio.instprm \
  --outdir results --label nd2p5_regress --no-llm
```

That run finishes at array Rwp 9.85, GOF 1.78 and VERDICT OK.

For secondary-phase screening, see [`src/phase_hunter.py`](src/phase_hunter.py) and its usage documentation.

## Research scope and maturity

Current development centers on **Bi₁₋ₓNdₓFeO₃** and laboratory powder X-ray diffraction. Neutron powder diffraction is part of the broader intended scope. The [roadmap](docs/ROADMAP.md) marks staged refinement, validators, agent orchestration and secondary-phase screening as completed development sprints, with **benchmarking currently in progress**. Visualization, publication and release milestones remain planned.

## Repository guide

- [`src/`](src/) — refinement, orchestration, validation and phase screening
- [`data/`](data/) — research inputs and sample assets
- [`docs/SETUP.md`](docs/SETUP.md) — environment and installation notes
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architectural decisions
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — completed and planned work

## License and attribution

The repository is released under the [MIT License](LICENSE). **GSAS-II is a separate dependency** with its own terms. This project is an independent research tool built around its scripting interface.

<div align="center"><sub>Scientific computing · Powder diffraction · Reproducible refinement</sub></div>
