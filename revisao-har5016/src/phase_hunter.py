"""Sprint 2.5: secondary phase hunter (v4).

Detects unexplained peaks in the refinement residual (excluding positions
near Bragg reflections of known phases) and tries adding candidate phases
from a local CIF library. Each trial is a copy of the input project: the
source .gpx is never overwritten. All existing refinement flags are cleared
via the GSASIIscriptable API (dict-form clear_refinements / clear_HAP_refinements)
and only the new phase scale is refined, starting from a small fraction of
the main phase scale. Deterministic checks decide acceptance (Rwp gain,
positive scale).

Usage:
    python phase_hunter.py RUN.gpx --library data/phases/ --outdir results
"""
import sys, os, json, glob, argparse, shutil

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.signal import find_peaks
from GSASII import GSASIIscriptable as G2sc

PEAK_SIGMA = 3.0        # residual peak detection threshold (x local noise)
BRAGG_TOL = 0.15        # deg 2theta: mask peaks this close to known reflections
MIN_RWP_GAIN = 0.20     # minimum absolute Rwp improvement to accept a phase
NEW_PHASE_SCALE = 0.01  # initial scale = 1% of the main phase scale

# every HAP flag block we want OFF during a phase trial
HAP_ALL = {"Scale": True, "Pref.Ori.": True, "Size": True,
           "Mustrain": True, "HStrain": True, "Extinction": True}

def get_rwp(gpx):
    return gpx.data.get("Covariance", {}).get("data", {}).get("Rvals", {}).get("Rwp")

def rwp_from_data(gpx):
    """Rwp computed directly from the observed/calculated pattern arrays."""
    h = gpx.histogram(0)
    yo = np.asarray(h.getdata("yobs"), dtype=float)
    yc = np.asarray(h.getdata("ycalc"), dtype=float)
    try:
        w = np.asarray(h.getdata("weight"), dtype=float)
        if len(w) != len(yo) or not np.any(w > 0):
            raise ValueError
    except Exception:
        w = 1.0 / np.maximum(yo, 1.0)  # counting-statistics weights
    return 100.0 * float(np.sqrt(np.sum(w * (yo - yc) ** 2) / np.sum(w * yo ** 2)))

def known_bragg_positions(gpx):
    """2theta positions of calculated reflections of all current phases.

    Powder RefList column 5 is 2theta; column 6 when the phase is 3+1 superspace.
    """
    pos = []
    for h in gpx.histograms():
        for ph, rl in h.reflections().items():
            ref = rl.get("RefList")
            if ref is None or len(ref) == 0:
                continue
            ref = np.asarray(ref, dtype=float)
            col = 6 if rl.get("Super") else 5
            if ref.ndim != 2 or ref.shape[1] <= col:
                continue
            pos.extend(ref[:, col].tolist())
    return np.asarray(sorted(pos), dtype=float) if pos else np.array([])

def find_unexplained_peaks(gpx):
    """Significant positive residual peaks NOT near known Bragg positions."""
    hist = gpx.histogram(0)
    x = np.asarray(hist.getdata("x"))
    res = np.asarray(hist.getdata("residual"))
    k = 51
    noise = np.array([res[max(0, i - k):i + k].std() for i in range(len(res))])
    noise = np.maximum(noise, 1e-6)
    score = res / noise
    idx, _ = find_peaks(score, height=PEAK_SIGMA, distance=25)
    idx = [i for i in idx if res[i] > 0]
    bragg = known_bragg_positions(gpx)
    out = []
    for i in idx:
        if len(bragg) and np.min(np.abs(bragg - x[i])) < BRAGG_TOL:
            continue  # profile/intensity misfit of a known phase, not a new phase
        out.append((round(float(x[i]), 3), round(float(score[i]), 1)))
    return out, bragg

def freeze_phase(phase, hname, refine_scale=False):
    """Clear cell, atom and HAP flags via the GSASIIscriptable API.

    Optionally leaves this phase scale flag ON afterwards.
    """
    phase.clear_refinements({"Cell": True})
    for a in phase.atoms():
        a.refinement_flags = " "
    phase.clear_HAP_refinements(HAP_ALL)
    if refine_scale:
        phase.data["Histograms"][hname]["Scale"][1] = True

def try_add_phase(gpx_path, cif_path, workdir, tag):
    """Copy the project, add the phase, refine ONLY its scale.

    add_phase() and refine() save to the project filename, so the trial is
    a file copy: the input .gpx is left unchanged. All existing refinement
    flags are cleared via the GSASIIscriptable API; the new phase enters
    with a small scale and only that scale is refined.
    Returns (trial_path, rwp, scale).
    """
    name = os.path.splitext(os.path.basename(cif_path))[0]
    trial = os.path.join(workdir, f"try_{tag}_{name}.gpx")
    shutil.copy(gpx_path, trial)
    gpx = G2sc.G2Project(gpxfile=trial)
    hist = gpx.histogram(0)
    hname = hist.name
    inst_keys = [k for k in ("U", "V", "W", "X", "Y", "Z", "Zero", "SH/L")
                 if k in hist.data["Instrument Parameters"][0]]
    # Background must be the last key: GSAS-II returns right after it
    hist.clear_refinements({"Sample Parameters": ["Scale"],
                            "Instrument Parameters": inst_keys,
                            "Background": True})
    main_scale = 0.0
    for ph in gpx.phases():
        freeze_phase(ph, hname, refine_scale=False)
        main_scale = max(main_scale, float(ph.data["Histograms"][hname]["Scale"][0]))
    phase = gpx.add_phase(cif_path, phasename=name, histograms=[hist], fmthint="CIF")
    sc = phase.data["Histograms"][hname]["Scale"]
    sc[0] = (main_scale or 1.0) * NEW_PHASE_SCALE
    freeze_phase(phase, hname, refine_scale=True)  # ONLY the new scale stays on
    gpx.do_refinements(refinements=[{}])
    del gpx
    fresh = G2sc.G2Project(gpxfile=trial)  # reopen saved trial: no stale state
    scale = float(fresh.phase(name).data["Histograms"][hname]["Scale"][0])
    return trial, rwp_from_data(fresh), scale

def hunt(gpx_path, library_dir, outdir):
    os.makedirs(outdir, exist_ok=True)
    report = {"input_gpx": gpx_path, "unexplained_peaks": [],
              "candidates_tried": [], "accepted_phases": []}
    gpx = G2sc.G2Project(gpxfile=gpx_path)
    base_rwp = get_rwp(gpx)
    report["base_rwp"] = base_rwp
    if base_rwp is None:
        print("No Rwp in the project; refine it before hunting phases.")
        return report

    peaks, bragg = find_unexplained_peaks(gpx)
    report["unexplained_peaks"] = peaks
    report["n_known_reflections"] = int(len(bragg))
    print(f"base Rwp={base_rwp:.2f}; known reflections={len(bragg)}; "
          f"unexplained peaks (Bragg-masked): {len(peaks)}")
    if len(bragg) == 0:
        print("  warning: reflection list is empty, Bragg mask is off")
    for tt, s in peaks:
        print(f"  peak at 2theta={tt} deg (score {s})")
    if not peaks:
        print("No unexplained peaks: residual is clean.")
        report["final_gpx"] = gpx_path
        report["final_rwp"] = float(base_rwp)
        _write_report(report, outdir)
        return report

    cifs = sorted(glob.glob(os.path.join(library_dir, "*.cif")))
    print(f"phase library: {[os.path.basename(c) for c in cifs]}")
    current, current_rwp = gpx_path, base_rwp
    for cif in cifs:
        name = os.path.splitext(os.path.basename(cif))[0]
        try:
            trial, rwp, scale = try_add_phase(current, cif, outdir, "hunt")
        except Exception as e:
            print(f"  {name}: FAILED to refine ({e})")
            report["candidates_tried"].append({"phase": name, "status": "error", "error": str(e)})
            continue
        if rwp is None:
            print(f"  {name}: refinement failed numerically -> rejected")
            report["candidates_tried"].append({"phase": name, "status": "failed", "scale": scale})
            continue
        if rwp > 10 * current_rwp:
            print(f"  {name}: trial diverged (unphysical Rwp) -> rejected")
            report["candidates_tried"].append({"phase": name, "status": "diverged",
                                               "scale": float(scale), "accepted": False})
            continue
        gain = current_rwp - rwp
        scale_ok = scale > 0
        verdict = bool(scale_ok and gain >= MIN_RWP_GAIN)
        why = "ACCEPTED" if verdict else "rejected"
        if not scale_ok:
            why = "rejected (negative scale)"
        print(f"  {name}: Rwp {current_rwp:.2f} -> {rwp:.2f} (gain {gain:+.2f}) "
              f"scale={scale:.4g} -> {why}")
        report["candidates_tried"].append({
            "phase": name, "rwp_after": float(rwp), "gain": float(gain),
            "scale": float(scale), "accepted": verdict})
        if verdict:
            current, current_rwp = trial, rwp
            report["accepted_phases"].append(name)

    report["final_gpx"] = current
    report["final_rwp"] = float(current_rwp)
    _write_report(report, outdir)
    print("Saved:", os.path.join(outdir, "phase_hunt_report.json"),
          "| final Rwp:", round(current_rwp, 2))
    return report

def _write_report(report, outdir):
    out = os.path.join(outdir, "phase_hunt_report.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gpx")
    ap.add_argument("--library", default="data/phases")
    ap.add_argument("--outdir", default="results")
    a = ap.parse_args()
    hunt(a.gpx, a.library, a.outdir)