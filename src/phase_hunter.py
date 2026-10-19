"""Sprint 2.5: secondary phase hunter.

Detects unexplained peaks in the refinement residual and, when found,
tries adding candidate phases from a local CIF library, accepting only
physically meaningful improvements (deterministic validation decides).

Usage:
    python phase_hunter.py RUN.gpx --library data/phases/ --outdir results
"""
import sys, os, json, glob, shutil, argparse

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from GSASII import GSASIIscriptable as G2sc

PEAK_SIGMA = 3.0        # residual peak detection threshold (x noise)
MIN_RWP_GAIN = 0.20     # minimum absolute Rwp improvement to accept a phase

def find_unexplained_peaks(gpx):
    """Return 2theta positions of significant peaks in (obs - calc)."""
    hist = gpx.histogram(0)
    x = np.asarray(hist.getdata("x"))
    res = np.asarray(hist.getdata("residual"))
    k = 51
    noise = np.array([res[max(0,i-k):i+k].std() for i in range(len(res))])
    noise = np.maximum(noise, 1e-6)
    score = res / noise
    from scipy.signal import find_peaks
    idx, _ = find_peaks(score, height=PEAK_SIGMA, distance=25)
    idx = [i for i in idx if res[i] > 0]
    return [(round(float(x[i]), 3), round(float(score[i]), 1)) for i in idx]

def get_rwp(gpx):
    return gpx.data.get("Covariance", {}).get("data", {}).get("Rvals", {}).get("Rwp")

def try_add_phase(gpx_path, cif_path, workdir, tag):
    """Add phase, refine its scale + cell, return (gpx_path, rwp)."""
    gpx = G2sc.G2Project(gpxfile=gpx_path)
    hist = gpx.histogram(0)
    name = os.path.splitext(os.path.basename(cif_path))[0]
    phase = gpx.add_phase(cif_path, phasename=name, histograms=[hist])
    hist.set_refinements({"Sample Parameters": ["Scale"]})
    phase.set_refinements({"Cell": True})
    gpx.do_refinements(refinements=[{}])
    out = os.path.join(workdir, f"try_{tag}_{name}.gpx")
    gpx.filename = out
    gpx.save()
    return out, get_rwp(gpx)

def hunt(gpx_path, library_dir, outdir):
    os.makedirs(outdir, exist_ok=True)
    report = {"input_gpx": gpx_path, "unexplained_peaks": [],
              "candidates_tried": [], "accepted_phases": []}
    gpx = G2sc.G2Project(gpxfile=gpx_path)
    base_rwp = get_rwp(gpx)
    report["base_rwp"] = base_rwp

    peaks = find_unexplained_peaks(gpx)
    report["unexplained_peaks"] = peaks
    print(f"base Rwp={base_rwp:.2f}; unexplained peaks: {len(peaks)}")
    for tt, s in peaks:
        print(f"  peak at 2theta={tt} deg (score {s})")
    if not peaks:
        print("No unexplained peaks: residual is clean.")
        return report

    cifs = sorted(glob.glob(os.path.join(library_dir, "*.cif")))
    print(f"phase library: {[os.path.basename(c) for c in cifs]}")
    current, current_rwp = gpx_path, base_rwp
    for cif in cifs:
        name = os.path.splitext(os.path.basename(cif))[0]
        try:
            trial, rwp = try_add_phase(current, cif, outdir, "hunt")
        except Exception as e:
            print(f"  {name}: FAILED to refine ({e})")
            report["candidates_tried"].append({"phase": name, "status": "error", "error": str(e)})
            continue
        gain = current_rwp - rwp
        verdict = gain >= MIN_RWP_GAIN
        print(f"  {name}: Rwp {current_rwp:.2f} -> {rwp:.2f} (gain {gain:+.2f}) "
              f"-> {'ACCEPTED' if verdict else 'rejected'}")
        report["candidates_tried"].append({"phase": name, "rwp_after": rwp,
                                           "gain": float(gain), "accepted": verdict})
        if verdict:
            current, current_rwp = trial, rwp
            report["accepted_phases"].append(name)

    report["final_gpx"] = current
    report["final_rwp"] = float(current_rwp)
    out = os.path.join(outdir, "phase_hunt_report.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print("Saved:", out, "| final Rwp:", round(current_rwp, 2))
    return report

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gpx")
    ap.add_argument("--library", default="data/phases")
    ap.add_argument("--outdir", default="results")
    a = ap.parse_args()
    hunt(a.gpx, a.library, a.outdir)
