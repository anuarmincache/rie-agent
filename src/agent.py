"""Sprint 2: rie-agent orchestrator.

Autonomous refinement loop: staged pipeline + deterministic validators +
remediation actions chosen by a planner. The planner is local Ollama when
it is reachable; otherwise a rule fallback. Validators accept or roll back.
The model may only return a name from the action menu. It cannot free Bi1,
Nd1, the frozen profile, or instrument X while axial size is refined.

The Nd fraction comes from --nd or from the data filename (Nd10, Nd2p5).
It is not guessed by the model. nominal_nd is offered only when that
fraction is known. Secondary phases are offered one CIF at a time and
kept only when array Rwp drops by at least 0.20.

Usage:
    python agent.py DATA.xye PHASE.cif INSTPRM --outdir results --label RUN
    python agent.py ... --nd 0.15          # Ollama decides among the menu
    python agent.py ... --no-llm           # rules only, for the Nd2.5 regression
"""
import sys, os, re, json, glob, shutil, argparse, datetime

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from GSASII import GSASIIscriptable as G2sc
from validators import validate
from recipe import (
    STAGES, SAMPLE_STAGES, REMEDIATIONS, MAX_CYCLES, PROFILE_CYCLES, RWP_CEILING,
    apply_stage, enforce_locks, pin_origin, drop_correlated, reopen_zero,
    freeze_instrument, FIXED_PROFILE, set_nominal_nd, hold_negative_uiso,
    rwp_from_data, gof_stored,
)
from phase_hunter import MIN_RWP_GAIN, try_add_phase

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
MAX_REMEDIATIONS = 10
PHASE_LIBRARY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "phases"
)
MEMORY_NAME = "run_memory.json"


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


def nd_fraction_from_name(path):
    """Read a percent from names such as Nd10, Nd2p5, Nd7,5. Cobalt files return None."""
    name = os.path.basename(path)
    if re.search(r"Co", name, re.I):
        return None
    if re.search(r"Nd2p5", name, re.I):
        return 0.025
    match = re.search(r"Nd\s*([0-9]+)(?:[.,]([0-9]+))?\s*%?", name, re.I)
    if not match:
        return None
    whole = match.group(1)
    frac = match.group(2)
    percent = float(whole if frac is None else "%s.%s" % (whole, frac))
    if percent <= 0 or percent >= 100:
        return None
    return percent / 100.0


def action_menu(nd_fraction, library):
    """Names the planner is allowed to return. Locks are not on this list."""
    actions = []
    if nd_fraction is not None:
        actions.append("nominal_nd")
    actions.append("hold_negative_uiso")
    actions.extend(REMEDIATIONS)
    if os.path.isdir(library):
        for cif in sorted(glob.glob(os.path.join(library, "*.cif"))):
            actions.append("phase_" + os.path.splitext(os.path.basename(cif))[0])
    return actions


def load_memory(path):
    if not os.path.isfile(path):
        return []
    with open(path) as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else []


def remember_run(path, record):
    """Replace any row with the same label and append this run."""
    rows = [row for row in load_memory(path) if row.get("label") != record.get("label")]
    rows.append(record)
    with open(path, "w") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")


def memory_brief(rows, nd_fraction, limit=6):
    """Short text of the nearest finished runs, for the planner."""
    if not rows:
        return "No earlier runs are recorded."

    def distance(row):
        other = row.get("nd_fraction")
        if nd_fraction is None or other is None:
            return 1.0
        return abs(float(other) - float(nd_fraction))

    lines = []
    for row in sorted(rows, key=distance)[:limit]:
        kept = [item.get("action", item) if isinstance(item, dict) else item
                for item in (row.get("kept_actions") or [])]
        rejected = [item.get("action", item) if isinstance(item, dict) else item
                    for item in (row.get("rejected_actions") or [])]
        lines.append(
            "nd=%s label=%s Rwp=%s verdict=%s kept=%s rejected=%s note=%s"
            % (
                row.get("nd_fraction"),
                row.get("label"),
                row.get("rwp"),
                "OK" if row.get("verdict_ok") else "FAIL",
                ", ".join(kept) or "none",
                ", ".join(rejected) or "none",
                row.get("note") or "",
            )
        )
    return "\n".join(lines)


def tie_nd_uiso(gpx, phase):
    """One equivalence: Nd Uiso equals Bi Uiso. Skipped when it already exists."""
    labels = [atom.label for atom in phase.atoms()]
    if "Bi1" not in labels or "Nd1" not in labels:
        return
    bi_i, nd_i = labels.index("Bi1"), labels.index("Nd1")
    blob = str(gpx.data.get("Constraints", {}).get("data", {}).get("Phase", []))
    if ("AUiso:%d" % bi_i) in blob and ("AUiso:%d" % nd_i) in blob:
        return
    gpx.add_EquivConstr(("0::AUiso:%d" % bi_i, "0::AUiso:%d" % nd_i))


def apply_nominal_nd(gpx, phase, nd_fraction):
    set_nominal_nd(phase, nd_fraction)
    gpx.save()
    tie_nd_uiso(gpx, gpx.phase(0))
    print("  nominal Nd fraction %.3f" % nd_fraction)


def apply_phase_trial(gpx_path, action, workdir, before_rwp):
    """Scale-only trial of one library CIF. Copy it over the project only on a real gain."""
    stem = action[len("phase_"):]
    cif = os.path.join(PHASE_LIBRARY, stem + ".cif")
    if not os.path.isfile(cif):
        print("  missing CIF for %s" % action)
        return
    os.makedirs(workdir, exist_ok=True)
    try:
        trial, _, scale = try_add_phase(gpx_path, cif, workdir, "agent")
        fresh = G2sc.G2Project(gpxfile=trial)
        after = rwp_from_data(fresh)
    except Exception as exc:
        print("  %s failed: %s" % (stem, exc))
        return
    gain = None if after is None or before_rwp is None else before_rwp - after
    keep = (
        gain is not None and gain >= MIN_RWP_GAIN and scale > 0
        and after < 10.0 * before_rwp
    )
    print(
        "  %s: Rwp %s -> %s gain %s scale %.4g -> %s"
        % (stem, before_rwp, after, None if gain is None else round(gain, 3), scale,
           "KEPT" if keep else "rejected")
    )
    if keep:
        shutil.copy(trial, gpx_path)


def apply_remediation(gpx, hist, phase, action, report, fixed_instrument=False,
                      nd_fraction=None, gpx_path=None, workdir=None, before_rwp=None):
    if action == "nominal_nd":
        apply_nominal_nd(gpx, phase, nd_fraction)
        gpx, hist, phase = reload(gpx.filename)
    elif action == "hold_negative_uiso":
        held = hold_negative_uiso(phase)
        print("  held negative Uiso: %s" % (", ".join(held) or "none"))
    elif action == "fix_correlated_params":
        frozen = drop_correlated(hist, report)
        print("  froze correlated params: %s" % (frozen or "none"))
    elif action == "extra_cycles":
        set_cycles(gpx, MAX_CYCLES * 2)
        print("  max cycles -> %d" % (MAX_CYCLES * 2))
    elif action in ("preferred_orientation", "background_18", "uniaxial_size"):
        apply_stage(hist, phase, action)
        print("  applied %s" % action)
    elif action.startswith("phase_"):
        apply_phase_trial(gpx_path, action, workdir, before_rwp)
        return
    else:
        raise ValueError("unknown remediation: " + str(action))
    refine(gpx, fixed_instrument=fixed_instrument)


def rule_planner(report, tried, menu):
    """Map a failing check to one allowed action. Locks are not negotiable."""
    fails = {c["check"] for c in report["checks"] if c["status"] == "FAIL"}
    if fails & {"frozen_profile", "bi1_origin", "nd1_origin", "size_x_alias"}:
        return None
    uiso_fail = any(name.startswith("uiso_") for name in fails)
    if uiso_fail and "nominal_nd" in menu and "nominal_nd" not in tried:
        return "nominal_nd"
    if uiso_fail and "hold_negative_uiso" not in tried:
        return "hold_negative_uiso"
    if "param_correlations" in fails and "fix_correlated_params" not in tried:
        return "fix_correlated_params"
    if "profile_shifts" in fails and "extra_cycles" not in tried:
        return "extra_cycles"
    if "svd_free" in fails and "preferred_orientation" not in tried:
        return "preferred_orientation"
    for action in menu:
        if action not in tried:
            return action
    return None


def _clean_action(text, menu):
    if not text:
        return None
    token = text.strip().split()[0].strip(".,;\"'`")
    return token if token in menu else None


def llm_planner(report, tried, history, menu, nd_fraction, memory_text):
    """Ask local Ollama for the next action. Returns None if unavailable."""
    import requests
    nd_line = (
        "Nd fraction on the Bi site is %.3f. nominal_nd sets Bi=%.3f and Nd=%.3f, "
        "freezes both coordinates, and ties Nd Uiso to Bi. The ion name is Nd+3.\n"
        % (nd_fraction, 1.0 - nd_fraction, nd_fraction)
        if nd_fraction is not None else
        "Nd fraction is unknown. nominal_nd is not allowed.\n"
    )
    prompt = (
        "You are the planner of a GSAS-II Rietveld agent for Nd-doped BiFeO3.\n"
        "You do not refine numbers yourself. You pick one allowed action.\n"
        "You must not free Bi1 or Nd1 coordinates, occupancy, V, Y, SH/L, or instrument X.\n"
        + nd_line
        + "Earlier runs, nearest composition first:\n"
        + memory_text
        + "\nPrefer an action that was kept on a nearby composition.\n"
        "Do not repeat an action that was rejected on a nearby composition unless the Rwp is much worse than those runs.\n"
        "If any uiso_ check FAILs and nominal_nd has not been tried, choose nominal_nd.\n"
        "If a uiso_ check still FAILs after that, choose hold_negative_uiso.\n"
        "Choose a phase_ action only when no uiso_ check is failing.\n"
        "A phase_ action is kept by the program only if Rwp drops by at least 0.20.\n"
        "The NdFeO3 Pnma CIF is the end-member cell. It diverged at Nd 0.10.\n"
        "Validation report:\n"
        + json.dumps(report["checks"], indent=1)
        + "\nActions already tried in this run: " + ", ".join(tried or ["none"])
        + "\nThis run: " + json.dumps(history[-4:])
        + "\nChoose exactly ONE action from: " + ", ".join(menu)
        + "\nReply with ONLY the action name."
    )
    try:
        response = requests.post(
            "%s/api/generate" % OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=180,
        )
        response.raise_for_status()
        text = response.json().get("response", "")
        return _clean_action(text, menu)
    except Exception as exc:
        print("  (LLM unavailable: %s; falling back to rules)" % exc)
        return None


def plan_next(report, tried, history, menu, nd_fraction, memory_text, use_llm=True):
    if use_llm:
        action = llm_planner(report, tried, history, menu, nd_fraction, memory_text)
        if action and action not in tried:
            print("  [planner: LLM/%s] -> %s" % (OLLAMA_MODEL, action))
            return action
        if action:
            print("  [planner: LLM repeated '%s'; consulting rules]" % action)
    action = rule_planner(report, tried, menu)
    print("  [planner: rules] -> %s" % action)
    return action


def run_agent(data_file, cif_file, instprm, outdir, label="run", use_llm=True,
              fixed_instrument=False, nd_fraction=None):
    os.makedirs(outdir, exist_ok=True)
    if nd_fraction is None:
        nd_fraction = nd_fraction_from_name(data_file)
    nd_fraction = None if nd_fraction is None else float(nd_fraction)
    fixed_instrument = bool(fixed_instrument) or (
        "provisorio" in os.path.basename(instprm).lower()
    )
    stages = SAMPLE_STAGES if fixed_instrument else STAGES
    menu = action_menu(nd_fraction, PHASE_LIBRARY)
    # The 9.94 bar is the Nd2.5 hand fit. Other compositions are not scored against it.
    use_ceiling = nd_fraction is not None and abs(nd_fraction - 0.025) < 1e-6
    gpx_path = os.path.join(outdir, f"{label}.gpx")
    log = {
        "label": label,
        "started": datetime.datetime.now().isoformat(),
        "base_stages": [],
        "remediations": [],
        "nd_fraction": nd_fraction,
        "use_llm": bool(use_llm),
        "action_menu": menu,
        "rwp_ceiling": RWP_CEILING if use_ceiling else None,
        "fixed_instrument": fixed_instrument,
    }
    print(
        "planner=%s nd=%s actions=%d"
        % ("ollama/" + OLLAMA_MODEL if use_llm else "rules", nd_fraction, len(menu))
    )

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
    hunt_dir = os.path.join(outdir, label + "_hunt")
    memory_file = os.path.join(outdir, MEMORY_NAME)
    prior = load_memory(memory_file)
    memory_text = memory_brief(prior, nd_fraction)
    print("memory: %d earlier runs" % len(prior))
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
        action = plan_next(
            {"checks": rep.checks}, tried, history, menu, nd_fraction,
            memory_text, use_llm,
        )
        if action is None or action in tried:
            print("  no new actions available; stopping.")
            break
        ckpt = os.path.join(outdir, f"{label}_ckpt_rem{it}.gpx")
        shutil.copy(gpx_path, ckpt)
        before = rwp_from_data(gpx)
        print(f"[remediate] {action}")
        apply_remediation(
            gpx, hist, phase, action, {"checks": rep.checks},
            fixed_instrument=fixed_instrument, nd_fraction=nd_fraction,
            gpx_path=gpx_path, workdir=hunt_dir, before_rwp=before,
        )
        gpx, hist, phase = reload(gpx_path)
        after = rwp_from_data(gpx)
        phase_action = action.startswith("phase_")
        if phase_action:
            improved = (
                after is not None and before is not None and before - after >= MIN_RWP_GAIN
            )
        else:
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
    log["meets_ceiling"] = (
        bool(verdict_ok) if not use_ceiling
        else final_rwp is not None and final_rwp <= RWP_CEILING and verdict_ok
    )
    log["finished"] = datetime.datetime.now().isoformat()
    with open(os.path.join(outdir, f"{label}_agent_log.json"), "w") as f:
        json.dump(log, f, indent=2, default=str)
    kept = [item["action"] for item in history if item.get("accepted")]
    rejected = [item["action"] for item in history if not item.get("accepted")]
    remember_run(memory_file, {
        "label": label,
        "nd_fraction": nd_fraction,
        "rwp": None if final_rwp is None else round(float(final_rwp), 3),
        "gof": None if log["final_gof"] is None else round(float(log["final_gof"]), 3),
        "verdict_ok": bool(verdict_ok),
        "kept_actions": kept,
        "rejected_actions": rejected,
        "note": "",
    })
    ceiling_txt = (
        " | ceiling %.2f: %s" % (RWP_CEILING, "MET" if log["meets_ceiling"] else "MISSED")
        if use_ceiling else ""
    )
    print(
        "Saved: %s | Rwp=%s | GOF=%s | VERDICT=%s%s"
        % (
            gpx_path,
            None if final_rwp is None else round(final_rwp, 2),
            log["final_gof"],
            "OK" if verdict_ok else "FAIL",
            ceiling_txt,
        )
    )
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("cif")
    ap.add_argument("instprm")
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--label", default="run")
    ap.add_argument("--nd", type=float, default=None, help="Nd fraction on the Bi site, e.g. 0.15")
    ap.add_argument("--no-llm", action="store_true", help="rules only, no Ollama")
    ap.add_argument(
        "--fixed-instrument", action="store_true",
        help="do not refine U V W X Y Zero SH/L (also implied by *provisorio*.instprm)",
    )
    a = ap.parse_args()
    run_agent(
        a.data, a.cif, a.instprm, a.outdir, a.label,
        use_llm=not a.no_llm, fixed_instrument=a.fixed_instrument,
        nd_fraction=a.nd,
    )
