"""Sprint 0: staged Rietveld refinement pipeline (no LLM agent yet).

Runs the classic staged recipe via GSASIIscriptable and logs quality
metrics (Rwp, GOF) after every stage. This is the deterministic engine
that the future agent will orchestrate.

Usage:
    python refine_staged.py DATA.xye PHASE.cif INSTPRM --outdir DIR --label RUN
"""
import sys, os, json, argparse, datetime

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
from GSASII import GSASIIscriptable as G2sc

STAGES = [
    ("1_scale_background", "scale factor + background (Chebyshev, 6 terms)"),
    ("2_lattice",          "lattice parameters"),
    ("3_profile_uvw",      "profile U, V, W (Caglioti)"),
    ("4_profile_xy",       "profile X, Y (size/strain)"),
    ("5_atomic_positions", "atomic fractional coordinates"),
    ("6_thermal",          "isotropic atomic displacement parameters"),
]

def run_pipeline(data_file, cif_file, instprm, outdir, label="run"):
    os.makedirs(outdir, exist_ok=True)
    log = {"label": label, "started": datetime.datetime.now().isoformat(),
           "inputs": {"data": data_file, "cif": cif_file, "instprm": instprm},
           "stages": []}
    gpx_path = os.path.join(outdir, f"{label}.gpx")
    gpx = G2sc.G2Project(newgpx=gpx_path)
    hist = gpx.add_powder_histogram(data_file, instprm)
    phase = gpx.add_phase(cif_file, phasename="BiFeO3", histograms=[hist])

    hist.set_refinements({"Background": {"no. coeffs": 6, "refine": True}})

    def get_rvals():
        cov = gpx.data.get("Covariance", {}).get("data", {})
        return cov.get("Rvals", {})

    def snapshot(stage_id, desc):
        gpx.save()
        rv = get_rvals()
        entry = {"stage": stage_id, "description": desc,
                 "Rwp": rv.get("Rwp"), "GOF": rv.get("GOF"),
                 "converged": rv.get("Converged")}
        log["stages"].append(entry)
        print(f"[{stage_id}] {desc}: Rwp={rv.get('Rwp')}, GOF={rv.get('GOF')}")

    for sid, desc in STAGES:
        if sid == "1_scale_background":
            hist.set_refinements({"Sample Parameters": ["Scale"],
                                  "Background": {"no. coeffs": 6, "refine": True}})
        elif sid == "2_lattice":
            phase.set_refinements({"Cell": True})
        elif sid == "3_profile_uvw":
            hist.set_refinements({"Instrument Parameters": ["U", "V", "W"]})
        elif sid == "4_profile_xy":
            hist.set_refinements({"Instrument Parameters": ["U", "V", "W", "X", "Y"]})
        elif sid == "5_atomic_positions":
            phase.set_refinements({"Atoms": {"all": "X"}})
        elif sid == "6_thermal":
            phase.set_refinements({"Atoms": {"all": "XU"}})
        gpx.do_refinements(refinements=[{}])
        snapshot(sid, desc)

    log["finished"] = datetime.datetime.now().isoformat()
    with open(os.path.join(outdir, f"{label}_log.json"), "w") as f:
        json.dump(log, f, indent=2)
    print("Saved:", gpx_path)
    return log

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data"); ap.add_argument("cif"); ap.add_argument("instprm")
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--label", default="run")
    a = ap.parse_args()
    run_pipeline(a.data, a.cif, a.instprm, a.outdir, a.label)
