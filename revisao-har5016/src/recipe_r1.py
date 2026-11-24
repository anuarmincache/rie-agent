"""Revised recipe (referee 1 of har5016): Bragg-Brentano instrument and sample model.

Instrument: Zero = 0, X = Y = 0, U, V, W and SH/L held at the transferred values;
none of them is refined. Sample: displacement ("Shift" in GSAS-II, micrometres at the
goniometer radius), isotropic crystallite size and isotropic microstrain are refined.
Site fractions are nominal and never refined. The staged loop and validator are those
of agent.py. Displacement, size and microstrain are started from a fixed grid and the
start with the lowest array Rwp is kept (see broadening_multistart).
"""
import os, shutil
import numpy as np

# Control experiment only: RIE_NO_SHIFT=1 keeps the sample displacement at zero.
NO_SHIFT = os.environ.get("RIE_NO_SHIFT") == "1"
from recipe import rwp_from_data, pin_origin, enable_md, BG_FINAL, PROFILE_CYCLES

R1_STAGES = [
    "scale_background", "lattice", "MULTISTART", "atomic_positions", "thermal",
    "background_18", "preferred_orientation", "size_mustrain",
]
R1_REMEDIATIONS = [
    "fix_correlated_params", "extra_cycles", "preferred_orientation", "background_18",
]
GONIO_RADIUS_MM = 185.0   # Shimadzu XRD-6000/6100 family scanning radius
GRID = [(s, m, h) for s in (0.1, 0.3, 1.0) for m in (1000.0, 4000.0) for h in (0.0, -100.0)]
HELD = ("U", "V", "W", "X", "Y", "Zero", "SH/L")


def hold_all(hist):
    inst = hist.data["Instrument Parameters"][0]
    for k in HELD:
        inst[k][2] = False


def setup_instrument(hist, gonio_radius=GONIO_RADIUS_MM):
    inst = hist.data["Instrument Parameters"][0]
    for k in ("Zero", "X", "Y"):
        inst[k][0] = inst[k][1] = 0.0
    hold_all(hist)
    hist.data["Sample Parameters"]["Gonio. radius"] = float(gonio_radius)


def apply_stage_r1(hist, phase, stage):
    if stage == "scale_background":
        hist.set_refinements({"Sample Parameters": ["Scale"],
                              "Background": {"no. coeffs": 6, "refine": True}})
    elif stage == "lattice":
        phase.set_refinements({"Cell": True})
    elif stage == "atomic_positions":
        phase.set_refinements({"Atoms": {"all": "X"}})
    elif stage == "thermal":
        phase.set_refinements({"Atoms": {"all": "XU"}})
    elif stage == "background_18":
        hist.set_refinements({"Background": {"no. coeffs": BG_FINAL, "refine": True}})
    elif stage == "preferred_orientation":
        enable_md(phase)
    elif stage == "size_mustrain":
        phase.set_HAP_refinements({"Size": {"type": "isotropic", "refine": True},
                                   "Mustrain": {"type": "isotropic", "refine": True}})
        hist.data["Sample Parameters"]["Shift"][1] = not NO_SHIFT
    else:
        raise ValueError("unknown stage: " + str(stage))
    pin_origin(phase)


def broadening_multistart(G2sc, path, outdir, label, grid=GRID):
    """Refine displacement, size and microstrain from each start; keep the lowest array Rwp.
    Returns the table of starts. All other flags are those of the checkpoint."""
    table, best = [], None
    for i, (size0, mus0, sh0) in enumerate(grid):
        tmp = os.path.join(outdir, "%s_ms%02d.gpx" % (label, i))
        shutil.copy(path, tmp)
        g = G2sc.G2Project(gpxfile=tmp)
        hist, phase = g.histogram(0), g.phase(0)
        hist.data["Sample Parameters"]["Shift"][0] = 0.0 if NO_SHIFT else float(sh0)
        hist.data["Sample Parameters"]["Shift"][1] = not NO_SHIFT
        phase.set_HAP_refinements({"Size": {"type": "isotropic", "refine": True},
                                   "Mustrain": {"type": "isotropic", "refine": True}})
        hap = list(phase.data["Histograms"].values())[0]
        hap["Size"][1][0] = float(size0)
        hap["Mustrain"][1][0] = float(mus0)
        g.data["Controls"]["data"]["max cyc"] = PROFILE_CYCLES
        try:
            g.do_refinements([{}])
            hold_all(g.histogram(0))
            g.save()
            rwp = rwp_from_data(G2sc.G2Project(gpxfile=tmp))
        except Exception:
            rwp = None
        table.append({"size0": size0, "mustrain0": mus0, "shift0": sh0, "rwp": rwp})
        if rwp is not None and (best is None or rwp < best[0]):
            best = (rwp, tmp)
    if best is not None:
        shutil.copy(best[1], path)
    for i in range(len(grid)):
        try:
            os.remove(os.path.join(outdir, "%s_ms%02d.gpx" % (label, i)))
        except OSError:
            pass
    return table


def collect_metrics(gpx):
    """Numbers reported in the paper tables, read from a finished project."""
    hist, phase = gpx.histogram(0), gpx.phase(0)
    cov = gpx.data["Covariance"]["data"]
    rv = cov["Rvals"]
    d = hist.data["data"][0]
    cell = phase.get_cell()
    hap = list(phase.data["Histograms"].values())[0]
    vary, sig, vals = cov["varyList"], cov["sig"], cov.get("variables")
    esd = {}
    for i, n in enumerate(vary):
        if any(t in n for t in ("Size", "Mustrain", "Shift")):
            esd[n] = [float(vals[i]) if vals is not None else None, float(sig[i])]
    return {
        "wRmin": float(d["wRmin"]), "DW": float(d["Durbin-Watson"]),
        "RF2": float(d.get("0:0:Rf^2", np.nan)),
        "cell": {k: float(v) for k, v in cell.items()},
        "shift_um": float(hist.data["Sample Parameters"]["Shift"][0]),
        "gonio_radius_mm": float(hist.data["Sample Parameters"]["Gonio. radius"]),
        "size_um": float(hap["Size"][1][0]), "mustrain_ue": float(hap["Mustrain"][1][0]),
        "md": float(hap["Pref.Ori."][1]),
        "atoms": {a.label: {"uiso": float(a.uiso), "occ": float(a.occupancy)} for a in phase.atoms()},
        "svd0": rv.get("SVD0"), "converged": bool(rv.get("converged")),
        "esd": esd,
    }
