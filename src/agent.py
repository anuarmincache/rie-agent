"""Sprint 2: rie-agent orchestrator.

Autonomous refinement loop: staged pipeline + deterministic validators +
remediation actions chosen by a planner. The planner is an LLM (Ollama,
local) when available; otherwise a built-in rule-based fallback.
Deterministic validators always have the final say (accept/reject/rollback).

Usage:
    python agent.py DATA.xye PHASE.cif INSTPRM --outdir results --label RUN
    python agent.py ... --no-llm        # rules only, no Ollama needed
"""
import sys, os, json, shutil, argparse, datetime

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from GSASII import GSASIIscriptable as G2sc
from validators import validate

BASE_STAGES = ["scale_background", "lattice", "profile_uvw",
               "profile_xy", "atomic_positions", "thermal"]
REMEDIATIONS = ["fix_correlated_params", "preferred_orientation_md",
                "more_background", "refine_shl", "refine_zero"]
MAX_REMEDIATIONS = 8
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# ---------------- refinement primitives ----------------

def apply_stage(gpx, hist, phase, stage):
    if stage == "scale_background":
        hist.set_refinements({"Sample Parameters": ["Scale"],
                              "Background": {"no. coeffs": 6, "refine": True}})
    elif stage == "lattice":
        phase.set_refinements({"Cell": True})
    elif stage == "profile_uvw":
        hist.set_refinements({"Instrument Parameters": ["U", "V", "W"]})
    elif stage == "profile_xy":
        hist.set_refinements({"Instrument Parameters": ["U", "V", "W", "X", "Y"]})
    elif stage == "atomic_positions":
        phase.set_refinements({"Atoms": {"all": "X"}})
    elif stage == "thermal":
        phase.set_refinements({"Atoms": {"all": "XU"}})
    gpx.do_refinements(refinements=[{}])

def apply_remediation(gpx, hist, phase, action, report):
    if action == "fix_correlated_params":
        drops = set()
        for c in report["checks"]:
            if c["check"] == "param_correlations" and c["detail"]:
                for pair in c["detail"].split(";"):
                    names = [p.strip().split(":")[-1] for p in pair.split("=")[0].split("x")]
                    if len(names) == 2:
                        drops.add(names[1])
        keep = [p for p in ["U", "V", "W", "X", "Y", "SH/L"] if p not in drops]
        hist.set_refinements({"Instrument Parameters": keep})
        print(f"  fixed params: {sorted(drops)}; refining {keep}")
    elif action == "preferred_orientation_md":
        hname = list(phase.data["Histograms"].keys())[0]
        phase.data["Histograms"][hname]["Pref.Ori."][2] = True
        print("  enabled March-Dollase PO, axis [0,0,1]")
    elif action == "more_background":
        hist.set_refinements({"Background": {"no. coeffs": 12, "refine": True}})
        print("  background -> 12 Chebyshev terms")
    elif action == "refine_shl":
        hist.set_refinements({"Instrument Parameters": ["U", "V", "W", "X", "Y", "SH/L"]})
        print("  refining SH/L")
    elif action == "refine_zero":
        hist.set_refinements({"Instrument Parameters": ["Zero", "U", "V", "W", "X", "Y"]})
        print("  refining zero shift")
    gpx.do_refinements(refinements=[{}])

# ---------------- planners ----------------

def rule_planner(report, tried):
    """Deterministic fallback planner: map failing checks to actions."""
    fails = {c["check"]: c["detail"] for c in report["checks"] if c["status"] == "FAIL"}
    if "param_correlations" in fails and "fix_correlated_params" not in tried:
        return "fix_correlated_params"
    if "svd_free" in fails and "preferred_orientation_md" not in tried:
        return "preferred_orientation_md"
    if "gof_reasonable" in fails and "more_background" not in tried:
        return "more_background"
    for a in REMEDIATIONS:
        if a not in tried:
            return a
    return None

def llm_planner(report, tried, history):
    """Ask local Ollama for the next action. Returns None if unavailable."""
    import requests
    prompt = (
        "You are an expert in Rietveld refinement with GSAS-II.\n"
        "A refinement produced this validation report:\n"
        + json.dumps(report["checks"], indent=1)
        + "\nActions already tried: " + ", ".join(tried or ["none"])
        + "\nHistory: " + json.dumps(history[-4:])
        + "\nChoose exactly ONE next action from: " + ", ".join(REMEDIATIONS)
        + ". Reply with ONLY the action name."
    )
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate",
                          json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                          timeout=180)
        ans = r.json().get("response", "").strip().split()[0]
        return ans if ans in REMEDIATIONS else None
    except Exception as e:
        print(f"  (LLM unavailable: {e}; falling back to rules)")
        return None

def plan_next(report, tried, history, use_llm=True):
    if use_llm:
        a = llm_planner(report, tried, history)
        if a:
            print(f"  [planner: LLM/{OLLAMA_MODEL}] -> {a}")
            return a
    a = rule_planner(report, tried)
    print(f"  [planner: rules] -> {a}")
    return a

# ---------------- main loop ----------------

def get_rwp(gpx):
    return gpx.data.get("Covariance", {}).get("data", {}).get("Rvals", {}).get("Rwp")

def run_agent(data_file, cif_file, instprm, outdir, label="run", use_llm=True):
    os.makedirs(outdir, exist_ok=True)
    gpx_path = os.path.join(outdir, f"{label}.gpx")
    log = {"label": label, "started": datetime.datetime.now().isoformat(),
           "base_stages": [], "remediations": []}

    gpx = G2sc.G2Project(newgpx=gpx_path)
    hist = gpx.add_powder_histogram(data_file, instprm)
    phase = gpx.add_phase(cif_file, phasename="BiFeO3", histograms=[hist])
    hist.set_refinements({"Background": {"no. coeffs": 6, "refine": True}})

    # Phase 1: staged pipeline with checkpoints
    prev_rwp = None
    for stage in BASE_STAGES:
        ckpt = os.path.join(outdir, f"{label}_ckpt_{stage}.gpx")
        if os.path.exists(gpx_path):
            shutil.copy(gpx_path, ckpt)
        apply_stage(gpx, hist, phase, stage)
        gpx.save()
        rwp = get_rwp(gpx)
        rep = validate(gpx_path, prev_rwp=prev_rwp)
        ok_rwp = rwp is not None and (prev_rwp is None or rwp <= prev_rwp * 1.05)
        print(f"[stage] {stage}: Rwp={rwp:.2f}")
        log["base_stages"].append({"stage": stage, "Rwp": rwp, "accepted": ok_rwp})
        if not ok_rwp:
            print(f"  Rwp worsened ({prev_rwp} -> {rwp}); rolling back to checkpoint")
            shutil.copy(ckpt, gpx_path)
            gpx = G2sc.G2Project(gpxfile=gpx_path)
            hist, phase = gpx.histogram(0), gpx.phase(0)
        else:
            prev_rwp = rwp

    # Phase 2: remediation loop driven by validators + planner
    tried, history = [], []
    for it in range(MAX_REMEDIATIONS):
        gpx.save()
        rep = validate(gpx_path)
        n_fail = sum(1 for c in rep.checks if c["status"] == "FAIL")
        print(f"[validate] iteration {it}: {n_fail} failing checks")
        if rep.ok:
            print("VALIDATION OK - refinement accepted.")
            break
        action = plan_next({"checks": rep.checks}, tried, history, use_llm)
        if action is None or action in tried:
            print("  no new actions available; stopping.")
            break
        ckpt = os.path.join(outdir, f"{label}_ckpt_rem{it}.gpx")
        shutil.copy(gpx_path, ckpt)
        before = get_rwp(gpx)
        print(f"[remediate] {action}")
        apply_remediation(gpx, hist, phase, action, {"checks": rep.checks})
        gpx.save()
        after = get_rwp(gpx)
        improved = after is not None and after <= before * 1.02
        print(f"  Rwp {before:.2f} -> {after:.2f} ({'accepted' if improved else 'ROLLBACK'})")
        if not improved:
            shutil.copy(ckpt, gpx_path)
            gpx = G2sc.G2Project(gpxfile=gpx_path)
            hist, phase = gpx.histogram(0), gpx.phase(0)
        tried.append(action)
        history.append({"action": action, "rwp_before": before, "rwp_after": after,
                        "accepted": improved})
        log["remediations"] = history

    gpx.save()
    log["final_rwp"] = get_rwp(gpx)
    log["finished"] = datetime.datetime.now().isoformat()
    with open(os.path.join(outdir, f"{label}_agent_log.json"), "w") as f:
        json.dump(log, f, indent=2, default=str)
    print("Saved:", gpx_path, "| final Rwp:", round(log["final_rwp"], 2))
    return log

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data"); ap.add_argument("cif"); ap.add_argument("instprm")
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--label", default="run")
    ap.add_argument("--no-llm", action="store_true", help="rules only, no Ollama")
    a = ap.parse_args()
    run_agent(a.data, a.cif, a.instprm, a.outdir, a.label, use_llm=not a.no_llm)
