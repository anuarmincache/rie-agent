"""Sprint 1: deterministic refinement validators.

Pure functions that read a GSAS-II project (.gpx) and return OK/FAIL with
reasons. The LLM agent never decides acceptance -- these functions do.

Usage:
    python validators.py results/Nd2p5_850.gpx [--prev-rwp 14.21]
"""
import sys, os, json, argparse
from dataclasses import dataclass, field

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from recipe import (
    FROZEN_AFTER_PROFILE, ORIGIN_ANCHOR, PROFILE_SHIFT_LIMIT,
    size_axial_is_refined,
)

@dataclass
class ValidationReport:
    checks: list = field(default_factory=list)
    def add(self, name, ok, detail=""):
        self.checks.append({"check": name, "status": "OK" if ok else "FAIL", "detail": detail})
    @property
    def ok(self):
        return all(c["status"] == "OK" for c in self.checks)

# physical plausibility bounds (typical for oxides)
UISO_MIN, UISO_MAX = 0.0001, 0.05     # A^2
OCC_MIN, OCC_MAX = 0.0, 1.0
CORR_WARN = 0.90                       # parameter correlation threshold
GOF_TARGET = 3.0                       # acceptable ceiling for lab XRD
RWP_WORSEN_TOL = 0.05                  # relative tolerance vs previous stage

def load_project(gpx_path):
    from GSASII import GSASIIscriptable as G2sc
    return G2sc.G2Project(gpxfile=gpx_path)

def check_rvals(gpx, rep):
    cov = gpx.data.get("Covariance", {}).get("data", {})
    rv = cov.get("Rvals", {})
    rwp, gof = rv.get("Rwp"), rv.get("GOF")
    rep.add("rwp_present", rwp is not None, f"Rwp={rwp}")
    if gof is not None:
        rep.add("gof_reasonable", gof <= GOF_TARGET, f"GOF={gof:.2f} (target <= {GOF_TARGET})")
    return rwp, gof

def check_thermal(gpx, rep):
    for ph in gpx.phases():
        for a in ph.atoms():
            u = a.uiso
            ok = UISO_MIN <= u <= UISO_MAX
            rep.add(f"uiso_{a.label}", ok, f"Uiso={u:.5f} A^2 (range {UISO_MIN}-{UISO_MAX})")

def check_occupancies(gpx, rep):
    for ph in gpx.phases():
        for a in ph.atoms():
            ok = OCC_MIN <= a.occupancy <= OCC_MAX
            rep.add(f"occ_{a.label}", ok, f"occ={a.occupancy:.4f}")

def check_correlations(gpx, rep):
    cov = gpx.data.get("Covariance", {}).get("data", {})
    vm, vl = cov.get("covMatrix"), cov.get("varyList")
    if vm is None or vl is None:
        rep.add("correlation_matrix", False, "covariance matrix not found")
        return
    vm = np.asarray(vm); d = np.sqrt(np.diag(vm)); n = len(vl)
    worst = []
    for i in range(n):
        for j in range(i+1, n):
            if d[i] > 0 and d[j] > 0:
                c = abs(vm[i, j] / (d[i] * d[j]))
                if c > CORR_WARN:
                    worst.append(f"{vl[i]} x {vl[j]} = {c:.2f}")
    rep.add("param_correlations", len(worst) == 0,
            "; ".join(worst) if worst else f"no |corr| > {CORR_WARN}")

def last_cycle_shift_over_esd(gpx):
    """|shift|/esd of the last cycle. Max shft/sig is the worst cycle, not the last."""
    cov = gpx.data.get("Covariance", {}).get("data", {})
    vm, vl = cov.get("covMatrix"), cov.get("varyList")
    shifts = (cov.get("Rvals") or {}).get("lastShifts")
    if vm is None or vl is None or not isinstance(shifts, dict):
        return None
    vm = np.asarray(vm, dtype=float)
    esd = np.sqrt(np.clip(np.diag(vm), 0, None))
    out = {}
    for i, name in enumerate(vl):
        if i >= len(esd) or esd[i] <= 0 or name not in shifts:
            continue
        try:
            out[name] = float(shifts[name]) / float(esd[i])
        except (TypeError, ValueError):
            continue
    return out

def check_convergence(gpx, rep):
    cov = gpx.data.get("Covariance", {}).get("data", {})
    rv = cov.get("Rvals", {})
    conv = rv.get("converged")
    sh = rv.get("Max shft/sig")
    rep.add("converged", bool(conv), f"converged={conv}, max shift/esd={sh}")
    svd0 = rv.get("SVD0", 0)
    rep.add("svd_free", svd0 == 0, f"SVD singularities={svd0}")
    ratios = last_cycle_shift_over_esd(gpx)
    if ratios is None:
        rep.add("profile_shifts", False, "last-cycle shifts unavailable")
        return
    bad = []
    for name, ratio in ratios.items():
        if name.split(":")[-1] in ("U", "W") and abs(ratio) > PROFILE_SHIFT_LIMIT:
            bad.append(f"{name}={ratio:.2f}")
    rep.add("profile_shifts", len(bad) == 0,
            "; ".join(bad) if bad else f"last-cycle |U,W shift/esd| <= {PROFILE_SHIFT_LIMIT}")

def check_locks(gpx, rep):
    """Bi1 is the polar origin. V, Y and SH/L stay frozen. Size does not ride with X."""
    hist = gpx.histogram(0)
    inst = hist.data["Instrument Parameters"][0]
    free = [k for k in FROZEN_AFTER_PROFILE
            if k in inst and isinstance(inst[k], list) and len(inst[k]) > 2 and bool(inst[k][2])]
    rep.add("frozen_profile", len(free) == 0,
            "free " + ", ".join(free) if free else "V, Y, SH/L frozen")
    seen_anchor = False
    for ph in gpx.phases():
        for atom in ph.atoms():
            flags = str(atom.refinement_flags)
            if atom.label == ORIGIN_ANCHOR:
                seen_anchor = True
                rep.add("bi1_origin", "X" not in flags, f"Bi1 flags={flags!r}")
            elif atom.label == "Nd1":
                rep.add("nd1_origin", "X" not in flags, f"Nd1 flags={flags!r}")
        if size_axial_is_refined(ph):
            x_on = "X" in inst and len(inst["X"]) > 2 and bool(inst["X"][2])
            rep.add("size_x_alias", not x_on,
                    "X refined with axial size" if x_on else "X frozen while axial size refines")
    if not seen_anchor:
        rep.add("bi1_origin", True, "no Bi1 in this project")

def validate(gpx_path, prev_rwp=None):
    gpx = load_project(gpx_path)
    rep = ValidationReport()
    rwp, gof = check_rvals(gpx, rep)
    check_thermal(gpx, rep)
    check_occupancies(gpx, rep)
    check_correlations(gpx, rep)
    check_convergence(gpx, rep)
    check_locks(gpx, rep)
    if prev_rwp is not None and rwp is not None:
        ok = rwp <= prev_rwp * (1 + RWP_WORSEN_TOL)
        rep.add("rwp_not_worse", ok, f"Rwp {prev_rwp:.2f} -> {rwp:.2f}")
    return rep

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gpx")
    ap.add_argument("--prev-rwp", type=float, default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    rep = validate(a.gpx, a.prev_rwp)
    for c in rep.checks:
        print(f"[{c['status']:>4}] {c['check']}: {c['detail']}")
    print(f"\nVERDICT: {'OK' if rep.ok else 'FAIL'}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"ok": rep.ok, "checks": rep.checks}, f, indent=2)
