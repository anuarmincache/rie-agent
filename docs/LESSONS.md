# Lessons learned (agent experience log)

Each entry records a failure mode, the fix that worked, and where it is
encoded in code. The agent's remediation table should grow from this log.

## 2026-10-18 - Input .gpx contamination via add_phase
- Symptom: phase-hunter trials inherited phantom phases; stored Rwp stale.
- Cause: GSAS-II add_phase() saves the project; the input was opened directly.
- Fix: trials run on file copies; input never opened for writing.
- Encoded in: src/phase_hunter.py (try_add_phase), ADR-007.

## 2026-10-18 - Stale stored Rwp after diverged refinement
- Symptom: Covariance Rvals did not reflect the actual pattern.
- Fix: recompute Rwp from yobs/ycalc arrays (rwp_from_data).
- Encoded in: src/phase_hunter.py, ADR-007.

## 2026-10-18 - Background flag index
- Symptom: background vanished or stayed on when poking raw indices.
- Cause: Background[0] layout = [function, flag, coeffs...]; index 1 = flag.
- Fix: use official API (dict-form clear_refinements).
- Encoded in: src/phase_hunter.py.

## 2026-10-18 - Diverged scale-only trial
- Symptom: candidate scale hits 1e-12, Rwp astronomically large.
- Fix: Rwp > 10x base = "diverged", reject.
- Encoded in: src/phase_hunter.py hunt().

## 2026-10-22 - Correlated instrument/profile parameters
- Symptom: |corr| > 0.90 for V-W, X-Y, SH/L-Zero; SVD singularity; no convergence.
- Fix: freeze V, Y, SH/L; keep U, W, X, Zero free.
- Encoded in: pending promotion to agent.py remediation table.
