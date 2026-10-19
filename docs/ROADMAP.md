# Roadmap

Development plan for rie-agent, organized in sprints.
Golden rule: **deterministic pipeline first, LLM agent last**.

## Sprint 0 - Headless staged refinement (no AI)  [DONE]

Scripted Rietveld refinement via GSASIIscriptable:
- Input: diffraction data (.xye/.gss), phase .cif, instrument .instprm
- Classic staged recipe: scale -> background -> lattice -> profile ->
  atomic positions -> thermal parameters
- Log Rwp, GOF and key parameters after every stage
- Target sample: Nd-doped BiFeO3 (lab XRD first, neutrons later)

Done when: one command refines a sample end-to-end and writes a
stage-by-stage quality report.

## Sprint 1 - Deterministic validators  [DONE]

Pure functions: refinement state -> OK/FAIL + reason.
- Rwp/GOF thresholds and trend (worsening = fail)
- Biso within physically reasonable range
- Occupancies within [0, 1]
- Divergence detection (covariance, parameter shifts vs esd)
- Phase-specific checks (Bi-Fe-O secondary phases: Bi25FeO40, Bi2Fe4O9)

## Sprint 2 - LLM agent  [DONE]

Orchestrator (LangGraph) deciding the next stage given state + trajectory,
with automatic rollback on validator failure. LLM for diagnosis/planning
only - never for numeric decisions. Local models via Ollama by default
(open source); paid API as an optional user-configured backend.

## Sprint 2.5 - Secondary phase hunter  [DONE]
- Bragg-masked residual peak detection
- Isolated scale-only phase trials (input .gpx immutable)
- Deterministic acceptance: Rwp gain >= 0.20, positive scale, diverged rejected
- Validated on Nd2.5 sample: library phases correctly rejected

## Sprint 3 - Benchmarks  <- CURRENT

- Full battery on Bi1-xNdxFeO3 series (multiple x)
- Public reference datasets
- Comparison against manual expert refinement (baseline)

## Sprint 4 - Visualization module (Blender)

render_structure.py: refined CIF -> publication-quality PNG/animation
via Blender bpy. Antiferromagnetic spin-cycloid visualization for BiFeO3.

## Sprint 5 - JOSS paper + v1.0 release

- paper/joss/paper.md + paper.bib
- GitHub release v1.0, Zenodo DOI, CITATION.cff
- CI: automated refinement smoke test + PDF builds

## Sprint 6 - Full article (J. Appl. Cryst. or Powder Diffraction)

Complete science paper in LaTeX (paper/jac/, IUCr template):
agent architecture, validation framework, BiFeO3:Nd case study.
Figures generated programmatically (matplotlib + Blender renders).
