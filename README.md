# rie-agent

Autonomous Rietveld refinement agent built on GSAS-II.

An LLM-orchestrated pipeline that performs staged Rietveld refinement with
**deterministic physical validation** at every step: numerical refinement is
computed by GSAS-II (via `GSASIIscriptable`), while acceptance/rejection of
each stage is decided by explicit physical criteria — not by the language
model. The agent plans, executes, validates, and rolls back until the
refinement converges to a physically meaningful optimum.

Primary use case: Nd-doped BiFeO3 multiferroic perovskites (XRD and neutron
powder diffraction), with a generic, recipe-driven design applicable to any
crystalline phase.

## Key design principles

- **Deterministic validation over LLM judgment** — Rwp/GOF thresholds,
  Biso ranges, occupancy bounds, and divergence detection are hard checks.
- **Staged refinement recipes** (scale -> background -> lattice -> profile ->
  positions -> thermal) defined as YAML state graphs, not blind trial-and-error.
- **Checkpoint/rollback** — every accepted stage is a checkpoint; divergence
  triggers automatic rollback to the last stable state.
- **Full trajectory logging** — every agent decision is recorded.

## Project status

Early development. See `docs/ROADMAP.md`.

## Repository layout

    src/            agent source code (gsas bridge, validators, orchestrator)
    data/samples/   example diffraction data, CIFs, instrument files
    data/results/   refinement outputs (.gpx, logs) - not versioned
    notebooks/      exploration and demo notebooks
    docs/           setup log, roadmap, architecture decisions
    paper/          JOSS paper (Markdown) and full article (LaTeX) - upcoming

## Requirements

- Linux (developed on Ubuntu 24.04 / WSL2)
- Conda env `rie-agent`: python=3.12, numpy=2.2 (conda-forge)
- GSAS-II from source (see `docs/SETUP.md`)

## License

MIT (this repository). GSAS-II is a separate dependency distributed
under its own license (free for academic use).
