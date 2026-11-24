"""Sprint 0: staged Rietveld refinement pipeline (no LLM agent yet).

Same locks and stage order as the agent (see recipe.py). This command
only runs the stages. It does not roll back and it does not call the planner.

Usage:
    python refine_staged.py DATA.xye PHASE.cif INSTPRM --outdir DIR --label RUN
"""
import sys, os, json, argparse, datetime

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from GSASII import GSASIIscriptable as G2sc
from recipe import STAGES, MAX_CYCLES, apply_stage, enforce_locks, reopen_zero, rwp_from_data, gof_stored

STAGE_HELP = {
    "scale_background": "scale + 6 Chebyshev terms",
    "lattice": "lattice parameters",
    "profile": "U, V, W, X, Y, Zero; then V and Y are frozen",
    "asymmetry": "SH/L with Zero held, then Zero restored",
    "atomic_positions": "coordinates except Bi1 (polar origin)",
    "thermal": "Uiso, Bi1 included, Bi1 xyz still fixed",
    "background_18": "background raised to 18 Chebyshev terms",
    "preferred_orientation": "March-Dollase along [001]",
    "uniaxial_size": "axial size along [001], equatorial fixed, X frozen",
    "release_y": "one cycle of Y with X already frozen, then Y frozen again",
}


def run_pipeline(data_file, cif_file, instprm, outdir, label="run"):
    os.makedirs(outdir, exist_ok=True)
    log = {
        "label": label,
        "started": datetime.datetime.now().isoformat(),
        "inputs": {"data": data_file, "cif": cif_file, "instprm": instprm},
        "stages": [],
    }
    gpx_path = os.path.join(outdir, f"{label}.gpx")
    gpx = G2sc.G2Project(newgpx=gpx_path)
    hist = gpx.add_powder_histogram(data_file, instprm)
    phase = gpx.add_phase(cif_file, phasename="BiFeO3", histograms=[hist])
    gpx.data["Controls"]["data"]["max cyc"] = MAX_CYCLES
    gpx.save()

    for stage in STAGES:
        gpx = G2sc.G2Project(gpxfile=gpx_path)
        hist, phase = gpx.histogram(0), gpx.phase(0)
        apply_stage(hist, phase, stage)
        gpx.do_refinements([{}])
        enforce_locks(gpx.histogram(0), gpx.phase(0))
        if stage == "asymmetry":
            reopen_zero(gpx.histogram(0))
        gpx.save()
        gpx = G2sc.G2Project(gpxfile=gpx_path)
        entry = {
            "stage": stage,
            "description": STAGE_HELP.get(stage, stage),
            "Rwp": rwp_from_data(gpx),
            "GOF": gof_stored(gpx),
        }
        log["stages"].append(entry)
        print(f"[{stage}] {entry['description']}: Rwp={entry['Rwp']}, GOF={entry['GOF']}")

    log["finished"] = datetime.datetime.now().isoformat()
    with open(os.path.join(outdir, f"{label}_log.json"), "w") as f:
        json.dump(log, f, indent=2)
    print("Saved:", gpx_path)
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("cif")
    ap.add_argument("instprm")
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--label", default="run")
    a = ap.parse_args()
    run_pipeline(a.data, a.cif, a.instprm, a.outdir, a.label)
