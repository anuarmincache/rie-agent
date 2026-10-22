"""Sprint 2: rie-agent orchestrator.

Autonomous refinement loop: staged pipeline + deterministic validators +
remediation actions chosen by a planner. The planner is an LLM (Ollama,
local) when available; otherwise a built-in rule-based fallback.
Deterministic validators always have the final say (accept/reject/rollback).

The numerical recipe and the locks live in recipe.py. The LLM may only
pick a name from that list. It cannot free Bi1, V, Y, SH/L, or instrument
X while axial size is refined.

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
from recipe import (
    STAGES, SAMPLE_STAGES, REMEDIATIONS, MAX_CYCLES, PROFILE_CYCLES, RWP_CEILING,
    apply_stage, enforce_locks, pin_origin, drop_correlated, reopen_zero,
    freeze_instrument, FIXED_PROFILE, rwp_from_data, gof_stored,
)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
MAX_REMEDIATIONS = 6


def set_cycles(gpx, n):
    gpx.data["Controls"]["data"]["max cyc"] = int(n)


def refine(gpx, fixed_instrument=False):
    """Refine, then re-apply the locks. The freeze happens after the cycle,
    so a stage that just turned a parameter on still gets that one cycle.
    With a fixed instrument, U, V, W, X, Y, Zero and SH/L stay off.
    """
    pin_origin(gpx.phase(0))
    gpx.do_refinements([{}])
    enforce_locks(gpx.histogram(0), gpx.phase(0), fixed_instrument=fixed_instrument)
    gpx.save()


def reload(path):
    gpx = G2sc.G2Project(gpxfile=path)
    return gpx, gpx.histogram(0), gpx.phase(0)


def apply_remediation(gpx, hist, phase, action, report, fixed_instrument=False):
    if action == "fix_correlated_params":
        frozen = drop_correlated(hist, report)
        print(f"  froze correlated params: {frozen or 'none'}")
    elif action == "extra_cycles":
        set_cycles(gpx, MAX_CYCLES * 2)
        print(f"  max cycles -> {MAX_CYCLES * 2}")
    elif action in ("preferred_orientation", "background_18", "uniaxial_size"):
        apply_stage(hist, phase, action)
        print(f"  applied {action}")
    else:
        raise ValueError("unknown remediation: " + str(action))
    refine(gpx, fixed_instrument=fixed_instrument)


def rule_planner(report, tried):
    """Map a failing check to one allowed action. Locks are not negotiable."""
    fails = {c["check"] for c in report["checks"] if c["status"] == "FAIL"}
    if fails & {"frozen_profile", "bi1_origin", "size_x_alias"}:
        return None
    if "param_correlations" in fails and "fix_correlated_params" not in tried:
        return "fix_correlated_params"
    if "profile_shifts" in fails and "extra_cycles" not in tried:
        return "extra_cycles"
    if "svd_free" in fails and "preferred_orientation" not in tried:
        return "preferred_orientation"
    for action in REMEDIATIONS:
        if action not in tried:
            return action
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
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=180,
        )
        ans = r.json().get("response", "").strip().split()[0]
        return ans if ans in REMEDIATIONS else None
    except Exception as e:
        print(f"  (LLM unavailable: {e}; falling back to rules)")
        return None


def plan_next(report, tried, history, use_llm=True):
    if use_llm:
        action = llm_planner(report, tried, history)
        if action and action not in tried:
            print(f"  [planner: LLM/{OLLAMA_MODEL}] -> {action}")
            return action
        if action:
            print(f"  [planner: LLM repeated '{action}'; consulting rules]")
    action = rule_planner(report, tried)
    print(f"  [planner: rules] -> {action}")
    return action


def run_agent(data_file, cif_file, instprm, outdir, label="run", use_llm=True,
              fixed_instrument=False):
    os.makedirs(outdir, exist_ok=True)
    fixed_instrument = bool(fixed_instrument) or (
        "provisorio" in os.path.basename(instprm).lower()
    )
    stages = SAMPLE_STAGES if fixed_instrument else STAGES
    gpx_path = os.path.join(outdir, f"{label}.gpx")
    log = {
        "label": label,
        "started": datetime.datetime.now().isoformat(),
        "base_stages": [],
        "remediations": [],
        "rwp_ceiling": RWP_CEILING,
        "fixed_instrument": fixed_instrument,
    }

    gpx = G2sc.G2Project(newgpx=gpx_path)
    hist = gpx.add_powder_histogram(data_file, instprm)
    phase = gpx.add_phase(cif_file, phasename="BiFeO3", histograms=[hist])
    set_cycles(gpx, MAX_CYCLES)
    if fixed_instrument:
        freeze_instrument(hist, FIXED_PROFILE)
    hist.set_refinements({"Background": {"no. coeffs": 6, "refine": True}})
    gpx.save()

    prev_rwp = None
    for stage in stages:
        ckpt = os.path.join(outdir, f"{label}_ckpt_{stage}.gpx")
        shutil.copy(gpx_path, ckpt)
        gpx, hist, phase = reload(gpx_path)
        set_cycles(gpx, PROFILE_CYCLES if stage == "profile" else MAX_CYCLES)
        apply_stage(hist, phase, stage)
        print(f"[stage] {stage}")
        refine(gpx, fixed_instrument=fixed_instrument)
        if stage == "asymmetry":
            gpx, hist, phase = reload(gpx_path)
            reopen_zero(hist)
            gpx.save()
        gpx, hist, phase = reload(gpx_path)
        rwp = rwp_from_data(gpx)
        strict = stage in ("asymmetry", "release_y")
        ok_rwp = rwp is not None and (prev_rwp is None or rwp <= prev_rwp * (1.0 if strict else 1.05))
        print(f"  Rwp={rwp:.2f}" if rwp is not None else "  Rwp=None")
        log["base_stages"].append({"stage": stage, "Rwp": rwp, "accepted": bool(ok_rwp)})
        if not ok_rwp:
            print(f"  Rwp worsened ({prev_rwp} -> {rwp}); rolling back")
            shutil.copy(ckpt, gpx_path)
            gpx, hist, phase = reload(gpx_path)
        else:
            prev_rwp = rwp

    tried, history = [], []
    verdict_ok = False
    for it in range(MAX_REMEDIATIONS):
        gpx, hist, phase = reload(gpx_path)
        rep = validate(gpx_path)
        n_fail = sum(1 for c in rep.checks if c["status"] == "FAIL")
        print(f"[validate] iteration {it}: {n_fail} failing checks")
        for c in rep.checks:
            if c["status"] == "FAIL":
                print(f"  FAIL {c['check']}: {c['detail']}")
        if rep.ok:
            verdict_ok = True
            print("VALIDATION OK - refinement accepted.")
            break
        action = plan_next({"checks": rep.checks}, tried, history, use_llm)
        if action is None or action in tried:
            print("  no new actions available; stopping.")
            break
        ckpt = os.path.join(outdir, f"{label}_ckpt_rem{it}.gpx")
        shutil.copy(gpx_path, ckpt)
        before = rwp_from_data(gpx)
        print(f"[remediate] {action}")
        apply_remediation(
            gpx, hist, phase, action, {"checks": rep.checks},
            fixed_instrument=fixed_instrument,
        )
        gpx, hist, phase = reload(gpx_path)
        after = rwp_from_data(gpx)
        improved = after is not None and before is not None and after <= before + 0.02
        print(f"  Rwp {before:.2f} -> {after:.2f} ({'accepted' if improved else 'ROLLBACK'})")
        if not improved:
            shutil.copy(ckpt, gpx_path)
            gpx, hist, phase = reload(gpx_path)
            after = before
        tried.append(action)
        history.append({
            "action": action,
            "rwp_before": None if before is None else float(before),
            "rwp_after": None if after is None else float(after),
            "accepted": bool(improved),
        })
        log["remediations"] = history

    gpx, hist, phase = reload(gpx_path)
    rep = validate(gpx_path)
    verdict_ok = rep.ok
    final_rwp = rwp_from_data(gpx)
    log["final_rwp"] = final_rwp
    log["final_gof"] = gof_stored(gpx)
    log["verdict_ok"] = bool(verdict_ok)
    log["meets_ceiling"] = final_rwp is not None and final_rwp <= RWP_CEILING and verdict_ok
    log["finished"] = datetime.datetime.now().isoformat()
    with open(os.path.join(outdir, f"{label}_agent_log.json"), "w") as f:
        json.dump(log, f, indent=2, default=str)
    print(
        f"Saved: {gpx_path} | Rwp={None if final_rwp is None else round(final_rwp, 2)} "
        f"| GOF={log['final_gof']} | VERDICT={'OK' if verdict_ok else 'FAIL'} "
        f"| ceiling {RWP_CEILING}: {'MET' if log['meets_ceiling'] else 'MISSED'}"
    )
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("cif")
    ap.add_argument("instprm")
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--label", default="run")
    ap.add_argument("--no-llm", action="store_true", help="rules only, no Ollama")
    ap.add_argument(
        "--fixed-instrument", action="store_true",
        help="do not refine U V W X Y Zero SH/L (also implied by *provisorio*.instprm)",
    )
    a = ap.parse_args()
    run_agent(
        a.data, a.cif, a.instprm, a.outdir, a.label,
        use_llm=not a.no_llm, fixed_instrument=a.fixed_instrument,
    )
