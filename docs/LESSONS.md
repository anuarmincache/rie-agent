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

## 2026-10-22 - Polar axis origin degeneracy (R3c)
- Symptom: soft SVD singularity on z-shifts; R3c is polar, origin along c is
  not fixed by symmetry, so refining all z coordinates is degenerate.
- Fix: freeze Bi1 coordinates (flags "U"), pinning the origin at Bi z = 0.
- Result: VERDICT OK, Rwp 10.48, GOF 1.89, SVD0=0, max shift/esd 0.26.
- Encoded in: pending promotion to agent.py remediation table.

## 2026-10-21 — March-Dollase [101] not adopted
**Symptom:** Five-axis PO scan left MD coeff 1.091 on [1,0,1] with stored Rwp 10.27, but the project was not converged (max shift/esd 24, mostly U and W).
**Action:** Copied try_po.gpx onto the baseline, ran validators, then re-refined that copy for more cycles and again with the MD coefficient held fixed.
**Result:** Raw [101] file VERDICT FAIL. After more cycles, VERDICT OK but Rwp 10.328 -> 10.278 (gain 0.0495) and U still moved by ~2.5 esd. no gain, rejected
**Rule for the agent:** Do not adopt a preferred-orientation axis on chi2 alone; require VERDICT OK and a last-cycle shift that is not carried by U or W.

## 2026-10-21 — Stale .good backup
**Symptom:** results/agent_llm.gpx.good was older than the validated baseline (Rwp 10.49, SVD0=1, Bi1 still flagged XU, background not at 18 coefficients, V/Y/SH/L free).
**Action:** Refused to restore it after the failed PO copy. Restored results/agent_llm.gpx.bak_pre_po, which is the converged baseline (Rwp 10.328, GOF 1.86, VERDICT OK).
**Result:** Baseline preserved. The .good file was replaced only after a later trial passed validators.
**Rule for the agent:** A file named .good is not authoritative; restore it only if Bi1 has no X flag, V/Y/SH/L are frozen, and validators print VERDICT OK.

## 2026-10-21 — Uniaxial microstrain [001]
**Symptom:** Texture had explained only ~0.06 in Rwp. Isotropic Mustrain was still the unused default (1000, not refined).
**Action:** On a copy, set HAP Mustrain to uniaxial along [0,0,1] and refined equatorial and axial terms, first with every other flag cleared, then together with the already free set. Also tried isotropic Mustrain with the free set.
**Result:** Rwp 10.328 -> 10.348 (frozen) and 10.349 (free); no gain, rejected. Isotropic Mustrain gained 0.01 and correlated with instrument X at 0.93 (VERDICT FAIL).
**Rule for the agent:** Do not turn on uniaxial microstrain for this Nd2.5 scan unless the array Rwp drops by at least 0.05 with VERDICT OK; the profile already absorbs that broadening.

## 2026-10-21 — Uniaxial crystallite size [001], instrument X frozen
**Symptom:** Refining uniaxial size with X free dropped array Rwp to 9.90 but failed validators (Size;a x X = 0.93) and Size;i ran to a nonsense shift/esd. Equatorial size also sat on a ceiling.
**Action:** Froze instrument X. Refined only the axial size along [0,0,1]. Held the equatorial size fixed. A scan of that fixed value (2, 5, 10, 20, 50 um) was clamped by GSAS-II to 10 um.
**Result:** Rwp 10.328 -> 9.836, GOF 1.86 -> 1.77, axial size 0.281(7) um, equatorial size 10 um (not refined), SVD0=0, VERDICT OK. Adopted.
**Rule for the agent:** For lab Bragg-Brentano BiFeO3, refine uniaxial size along [001] only with instrument X frozen and the equatorial size held at the 10 um ceiling; never refine Size and X together.

## 2026-10-21 — Sample shift, transparency, surface roughness
**Symptom:** Residual GOF was still above 1 after the profile and 18-term background were already refined.
**Action:** On copies, refined Shift alone, Transparency alone, and SurfRoughA+B alone, with every other flag cleared.
**Result:** Shift and Transparency: no gain, rejected (delta Rwp about 0). SurfRoughA/B: VERDICT FAIL (100% correlation, SVD0=1).
**Rule for the agent:** Do not refine Bragg-Brentano Shift, Transparency, or the surface-roughness pair on this histogram; Zero and the background already cover them.

## 2026-10-21 — Locks promoted into the agent
**Symptom:** agent.py still freed every atomic coordinate, refined V with W and SH/L with Zero, read the stored Rwp, and had no size action.
**Action:** The lab recipe and the locks now live in src/recipe.py. Stages freeze Bi1 coordinates, freeze V and Y after the profile block, refine SH/L only with Zero held, then refine uniaxial size along [001] with equatorial size fixed and instrument X frozen. Acceptance uses Rwp from the pattern arrays. validators.py rejects a free Bi1, a free V/Y/SH/L, size refined together with X, and a last-cycle U or W shift/esd above 1.
**Result:** `python src/agent.py` on Nd2p5_850.xye, BFO.cif and cuka_lab.instprm with `--no-llm --label nd2p5_auto` finishes at array Rwp 10.40, GOF 1.87, VERDICT OK. The hand-tuned project remains at Rwp 9.84. Same locks, a different profile minimum.
**Rule for the agent:** Run that Nd2.5 command before any new sample. Do not hand the agent a sample when that command fails VERDICT OK.

## 2026-10-21 — Provisional instrument from the hand refinement
**Symptom:** The from-scratch agent and the hand project land in different profile minima (Rwp 10.40 vs 9.84). There is no Si or LaB6 scan in the repo.
**Action:** Wrote `data/instrument/shimadzu_nd_provisorio.instprm` from the refined values in `results/agent_llm.gpx` (Zero, U, V, W, X, Y, SH/L). A name containing `provisorio` makes the agent skip the profile stages and hold those parameters fixed. Sample stages still run: scale, cell, coordinates with Bi1 pinned, Uiso, 18-term background, March-Dollase [001], uniaxial size [001].
**Result:** `--label nd2p5_regress --no-llm` finishes at array Rwp 9.85, GOF 1.78, VERDICT OK, under the ceiling 9.94.
**Rule for the agent:** Use this instprm for the next composition. It is a transfer of the Nd2.5 hand fit, not a certified instrument calibration. X and Y stay in the file because the size model was refined against them.

