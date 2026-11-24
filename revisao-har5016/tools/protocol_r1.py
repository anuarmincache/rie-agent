"""Alternative refinement protocol following referee 1 (har5016).

Instrument profile: Zero = 0 and X = Y = 0 (not refined), U, V, W, SH/L held at the
transferred values or refined on request. Sample displacement is always refined.
Crystallite size and microstrain are refined as sample parameters. Site fractions are
nominal and never refined. Same acceptance rule per stage as src/agent.py (5% relative).

Usage:
  python tools/protocol_r1.py DATA.xye BFO.cif INSTPRM OUTDIR LABEL --nd 0.10 \
      [--a-site nominal|pure] [--size iso|axial] [--uvw hold|refine] [--no-disp]
"""
import argparse, json, os, shutil, sys

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import numpy as np
from GSASII import GSASIIscriptable as G2sc
from recipe import (rwp_from_data, gof_stored, pin_origin, set_nominal_nd, enable_md,
                    BG_FINAL, MAX_CYCLES, PROFILE_CYCLES)
from agent import tie_nd_uiso
from validators import validate


def set_inst(hist, key, value, flag):
    inst = hist.data["Instrument Parameters"][0]
    inst[key][0] = float(value)
    inst[key][1] = float(value)
    inst[key][2] = bool(flag)


def hold_instrument(hist, keys=("U", "V", "W", "X", "Y", "Zero", "SH/L")):
    inst = hist.data["Instrument Parameters"][0]
    for k in keys:
        inst[k][2] = False


def reload(path):
    g = G2sc.G2Project(gpxfile=path)
    return g, g.histogram(0), g.phase(0)


def apply_stage(hist, phase, stage, a):
    if stage == "scale_background":
        hist.set_refinements({"Sample Parameters": ["Scale"],
                              "Background": {"no. coeffs": 6, "refine": True}})
    elif stage == "lattice":
        phase.set_refinements({"Cell": True})
    elif stage == "uvw":
        hist.set_refinements({"Instrument Parameters": ["U", "V", "W", "SH/L"]})
    elif stage == "displacement":
        hist.data["Sample Parameters"]["Shift"][1] = True
    elif stage == "atomic_positions":
        phase.set_refinements({"Atoms": {"all": "X"}})
    elif stage == "thermal":
        phase.set_refinements({"Atoms": {"all": "XU"}})
    elif stage == "background_18":
        hist.set_refinements({"Background": {"no. coeffs": BG_FINAL, "refine": True}})
    elif stage == "preferred_orientation":
        enable_md(phase)
    elif stage in ("size_mustrain", "size_mustrain_2"):
        if a.size == "iso":
            phase.set_HAP_refinements({"Size": {"type": "isotropic", "refine": True},
                                       "Mustrain": {"type": "isotropic", "refine": True}})
        else:
            phase.set_HAP_refinements({"Size": {"type": "uniaxial", "direction": [0, 0, 1],
                                                "refine": True},
                                       "Mustrain": {"type": "isotropic", "refine": True}})
    else:
        raise ValueError(stage)
    pin_origin(phase)


def broadening_multistart(path, a, grid):
    """Refine sample displacement, size and microstrain from a grid of starting values
    (all other flags as at the checkpoint). Keep the start with the lowest array Rwp."""
    results = []
    best = None
    for i, (size0, mus0, sh0) in enumerate(grid):
        tmp = os.path.join(a.outdir, "%s_ms%02d.gpx" % (a.label, i))
        shutil.copy(path, tmp)
        g, hist, phase = reload(tmp)
        hist.data["Sample Parameters"]["Shift"][0] = 0.0 if a.no_disp else float(sh0)
        hist.data["Sample Parameters"]["Shift"][1] = not a.no_disp
        phase.set_HAP_refinements({"Size": {"type": "isotropic", "refine": True},
                                   "Mustrain": {"type": "isotropic", "refine": True}})
        hap = list(phase.data["Histograms"].values())[0]
        hap["Size"][1][0] = float(size0)
        hap["Mustrain"][1][0] = float(mus0)
        g.data["Controls"]["data"]["max cyc"] = PROFILE_CYCLES
        try:
            g.do_refinements([{}])
            hold_instrument(g.histogram(0))
            g.save()
            g, hist, phase = reload(tmp)
            rwp = rwp_from_data(g)
        except Exception as exc:
            rwp = None
        results.append({"size0": size0, "mustrain0": mus0, "shift0": sh0, "rwp": rwp})
        print("  [multistart %02d] size0=%.2f mus0=%d shift0=%d -> Rwp=%s" % (
            i, size0, mus0, sh0, None if rwp is None else "%.3f" % rwp))
        if rwp is not None and (best is None or rwp < best[0]):
            best = (rwp, tmp)
    shutil.copy(best[1], path)
    for i in range(len(grid)):
        try:
            os.remove(os.path.join(a.outdir, "%s_ms%02d.gpx" % (a.label, i)))
        except OSError:
            pass
    return results


GRID = [(s, m, h) for s in (0.1, 0.3, 1.0) for m in (1000.0, 4000.0) for h in (0.0, -100.0)]



def run(a):
    os.makedirs(a.outdir, exist_ok=True)
    path = os.path.join(a.outdir, a.label + ".gpx")
    g = G2sc.G2Project(newgpx=path)
    hist = g.add_powder_histogram(a.data, a.instprm)
    phase = g.add_phase(a.cif, phasename="BiFeO3", histograms=[hist])
    g.data["Controls"]["data"]["max cyc"] = MAX_CYCLES
    set_inst(hist, "Zero", 0.0, False)
    set_inst(hist, "X", 0.0, False)
    set_inst(hist, "Y", 0.0, False)
    hold_instrument(hist)
    if a.a_site == "nominal" and a.nd:
        set_nominal_nd(phase, a.nd)
        g.save()
        tie_nd_uiso(g, g.phase(0))
    hist.set_refinements({"Background": {"no. coeffs": 6, "refine": True}})
    g.save()
    stages = ["scale_background", "lattice"]
    if a.uvw == "refine":
        stages.append("uvw")
    if a.multistart:
        stages.append("MULTISTART")
    else:
        if not a.no_disp:
            stages.append("displacement")
        stages.append("size_mustrain")
    stages += ["atomic_positions", "thermal", "background_18",
               "preferred_orientation", "size_mustrain_2"]
    ms_table = None
    prev, log = None, []
    for st in stages:
        if st == "MULTISTART":
            ms_table = broadening_multistart(path, a, GRID)
            g, hist, phase = reload(path)
            prev = rwp_from_data(g)
            print("[stage] %-22s Rwp=%.3f" % ("multistart(best of %d)" % len(GRID), prev))
            log.append({"stage": st, "Rwp": prev, "accepted": True})
            continue
        ck = os.path.join(a.outdir, "%s_ckpt_%s.gpx" % (a.label, st))
        shutil.copy(path, ck)
        g, hist, phase = reload(path)
        g.data["Controls"]["data"]["max cyc"] = PROFILE_CYCLES if st in ("uvw", "size_mustrain") else MAX_CYCLES
        apply_stage(hist, phase, st, a)
        pin_origin(g.phase(0))
        try:
            g.do_refinements([{}])
        except Exception as exc:
            print("  stage %s raised %s; rolled back" % (st, exc))
            shutil.copy(ck, path)
            log.append({"stage": st, "error": str(exc)})
            continue
        hold_instrument(g.histogram(0), ("X", "Y", "Zero", "SH/L") + (("U", "V", "W") if st == "uvw" else ()))
        g.save()
        g, hist, phase = reload(path)
        rwp = rwp_from_data(g)
        ok = rwp is not None and (prev is None or rwp <= prev * 1.05)
        print("[stage] %-22s Rwp=%.3f %s" % (st, rwp, "" if ok else "ROLLBACK"))
        log.append({"stage": st, "Rwp": rwp, "accepted": bool(ok)})
        if ok:
            prev = rwp
        else:
            shutil.copy(ck, path)
    g, hist, phase = reload(path)
    # final refinement pass so covariance matches the saved state
    g.do_refinements([{}])
    g.save()
    g, hist, phase = reload(path)
    cov = g.data["Covariance"]["data"]
    rv = cov["Rvals"]
    d = hist.data["data"][0]
    cell = phase.get_cell()
    vary, sig = cov["varyList"], cov["sig"]
    vals = cov.get("variables")
    est = {}
    for i, n in enumerate(vary):
        if any(t in n for t in ("Size", "Mustrain", "Shift", "AUiso", "MD", "dAz", "dAx", "dAy", "Back;0")):
            v = float(vals[i]) if vals is not None and len(vals) > i else float("nan")
            est[n] = [v, float(sig[i])]
    atoms = {at.label: {"uiso": float(at.uiso), "occ": float(at.occupancy)} for at in phase.atoms()}
    hap = list(phase.data["Histograms"].values())[0]
    rep = validate(path)
    out = {
        "label": a.label, "nd": a.nd, "a_site": a.a_site, "size": a.size, "uvw": a.uvw,
        "rwp_array": rwp_from_data(g), "rwp_gsas": float(rv["Rwp"]), "gof": float(rv["GOF"]),
        "wRmin": float(d["wRmin"]), "DW": float(d["Durbin-Watson"]),
        "cell": {k: float(v) for k, v in cell.items()} if isinstance(cell, dict) else [float(x) for x in cell],
        "shift_um": float(hist.data["Sample Parameters"]["Shift"][0]),
        "size_hap": [str(hap["Size"][0]), [float(x) for x in hap["Size"][1]]],
        "mustrain_hap": [str(hap["Mustrain"][0]), [float(x) for x in hap["Mustrain"][1]]],
        "md": float(hap["Pref.Ori."][1]),
        "atoms": atoms, "svd0": rv.get("SVD0"), "converged": bool(rv.get("converged")),
        "stages": log, "verdict_ok": bool(rep.ok),
        "failing": [c for c in rep.checks if c["status"] == "FAIL"],
        "est": est, "multistart": ms_table,
        "RF2": float(d.get("0:0:Rf^2", np.nan)), "RF": float(d.get("0:0:Rf", np.nan)),
    }
    with open(os.path.join(a.outdir, a.label + "_metrics.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("DONE %s Rwp=%.3f GOF=%.3f DW=%.3f dispX=%.2f verdict=%s" % (
        a.label, out["rwp_array"], out["gof"], out["DW"], out["shift_um"], "OK" if rep.ok else "FAIL"))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data"); ap.add_argument("cif"); ap.add_argument("instprm")
    ap.add_argument("outdir"); ap.add_argument("label")
    ap.add_argument("--nd", type=float, default=None)
    ap.add_argument("--a-site", dest="a_site", default="nominal", choices=["nominal", "pure"])
    ap.add_argument("--size", default="iso", choices=["iso", "axial"])
    ap.add_argument("--uvw", default="hold", choices=["hold", "refine"])
    ap.add_argument("--no-disp", dest="no_disp", action="store_true")
    ap.add_argument("--multistart", action="store_true")
    run(ap.parse_args())
