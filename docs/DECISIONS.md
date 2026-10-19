# Architecture Decision Records

## ADR-001: GSAS-II as the refinement engine

Status: accepted
Decision: GSAS-II via GSASIIscriptable (Python API, no GUI required).
rie-agent calls GSAS-II as a dependency; GSAS-II is never modified.
Our repo is MIT; GSAS-II keeps its own license. The GUI remains useful
for visual inspection only.

## ADR-002: Deterministic validation, LLM planning

Status: accepted
Context: LLMs can minimize Rwp with physically absurd structures
(negative Biso, occupancies > 1, background absorbing peaks).
Decision: numerical state computed by GSAS-II; stage acceptance decided
by deterministic validators; the LLM only diagnoses and plans.
Consequences: auditable behavior; LLM swappable (local or API).

## ADR-003: Staged recipes as YAML state graphs

Status: accepted
Context: blind trial-and-error is slow (~1 h/sample) and diverges often.
Decision: refinement recipes are explicit YAML state graphs with
checkpoints and rollback. Domain knowledge (e.g. perovskites) lives in
config, keeping the core generic.

## ADR-004: Development inside WSL2, not Windows

Status: accepted
Context: GitHub Desktop failed with WSL paths; headless refinement,
cron, Docker and CI are Linux-first.
Decision: repo and conda env live in Ubuntu 24.04 (WSL2); git via
GitHub CLI. Windows keeps GSAS-II GUI and Blender only.

## ADR-005: Dual publication strategy

Status: accepted
Decision: (1) software paper at JOSS (Markdown, reviewed in the repo);
(2) science paper at J. Appl. Cryst. / Powder Diffraction (LaTeX, IUCr
template). Repo follows JOSS requirements from day one. Releases get
DOIs via Zenodo.

## ADR-006: Open-weight local LLM by default, paid API optional

Status: accepted
Decision: the agent ships with Ollama (local open-weight models) as the
default backend - zero cost, fully reproducible. A paid API
(Anthropic/OpenAI) can be configured by the user via environment
variables, but is never required.

## ADR-007: Trial isolation and distrust of stored Rwp

**Context.** While building the phase hunter (Sprint 2.5), GSAS-II's
`add_phase()` silently saved the project back to the *input* .gpx file,
contaminating the reference refinement with a candidate phase. The stored
Rwp in `Covariance/Rvals` remained stale (10.49) and masked the
contamination, so every downstream trial inherited a phantom phase.

**Decision.** (1) Every phase trial runs on a file copy; the input .gpx is
never opened for writing. (2) Acceptance metrics are recomputed from the
observed/calculated pattern arrays (`rwp_from_data`), never read from
stored Rvals after a trial. (3) Backups (`.good`) are made before any
hunter run. (4) Diverged trials (Rwp > 10x base) are flagged "diverged"
and rejected.

**Consequences.** Slightly more disk I/O per trial; in exchange, the
agent's decisions are auditable and the reference state is provably
immutable during hunting.
