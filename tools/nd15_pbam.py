"""Nd 15% test: one Pbam perovskite, cell taken from the refined R3c metric.

The room-temperature phase reported for Bi0.85Nd0.15FeO3 is the antipolar
PbZrO3 type, not the Pnma tilt of NdFeO3. Metric, Z = 8:

    a = a_hex
    b = 2 * a_hex
    c = c_hex / sqrt(3)

Fractional coordinates are the 10 K PbZrO3 Pbam positions (Pb on 4g and 4h,
Zr on 8i). The cell is not the PbZrO3 cell. Occupancy is nominal and fixed:
Bi 0.85, Nd 0.15 on each A site. This does not replace results/nd15_auto.gpx.
"""
import math
import os
import shutil
import sys

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from GSASII import GSASIIscriptable as G2sc
from recipe import (
    BG_FINAL, FIXED_PROFILE, MAX_CYCLES,
    enable_md, enable_uniaxial_size, freeze_instrument,
    hold_negative_uiso, rwp_from_data, gof_stored,
)
from validators import validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R3C_GPX = os.path.join(ROOT, "results", "nd15_auto.gpx")
DATA = os.path.join(ROOT, "data", "samples", "Nd15_850.xye")
INST = os.path.join(ROOT, "data", "instrument", "shimadzu_nd_provisorio.instprm")
OUT = os.path.join(ROOT, "results", "nd15_pbam.gpx")
ND_FRACTION = 0.15
SIZE_AXIS = [0, 1, 0]
# 10 K PbZrO3, Pbam. O2 is the 4h site (z = 1/2).
SITES = [
    ("Bi1", "Bi+3", (0.6991, 0.1228, 0.0000), 1.0 - ND_FRACTION, 0.008),
    ("Nd1", "Nd+3", (0.6991, 0.1228, 0.0000), ND_FRACTION, 0.008),
    ("Bi2", "Bi+3", (0.7056, 0.1294, 0.5000), 1.0 - ND_FRACTION, 0.008),
    ("Nd2", "Nd+3", (0.7056, 0.1294, 0.5000), ND_FRACTION, 0.008),
    ("Fe1", "Fe+3", (0.2414, 0.1248, 0.2404), 1.0, 0.008),
    ("O1", "O-2", (0.2756, 0.1560, 0.0000), 1.0, 0.01),
    ("O2", "O-2", (0.3011, 0.0956, 0.5000), 1.0, 0.01),
    ("O3", "O-2", (0.0317, 0.2622, 0.2798), 1.0, 0.01),
    ("O4", "O-2", (0.0000, 0.5000, 0.2056), 1.0, 0.01),
    ("O5", "O-2", (0.0000, 0.0000, 0.2293), 1.0, 0.01),
]
EXPECTED_MULT = {
    "Bi1": 4, "Nd1": 4, "Bi2": 4, "Nd2": 4, "Fe1": 8,
    "O1": 4, "O2": 4, "O3": 8, "O4": 4, "O5": 4,
}
PAIRS = ((0, 1), (2, 3))


def set_cycles(gpx, n):
    gpx.data["Controls"]["data"]["max cyc"] = int(n)


def refine(gpx):
    freeze_instrument(gpx.histogram(0), FIXED_PROFILE)
    gpx.do_refinements([{}])
    gpx.save()
    fresh = G2sc.G2Project(gpxfile=gpx.filename)
    freeze_instrument(fresh.histogram(0), FIXED_PROFILE)
    fresh.save()
    return fresh


def r3c_metric():
    src = G2sc.G2Project(gpxfile=R3C_GPX)
    cell = src.phase(0).get_cell()
    return float(cell["length_a"]), float(cell["length_c"]), rwp_from_data(src)


def pbam_cell(a_h, c_h):
    return a_h, 2.0 * a_h, c_h / math.sqrt(3.0)


def tie(gpx, kind):
    """Equate Nd to the Bi on the same site. Call only once those parameters vary."""
    for i, j in PAIRS:
        if kind == "U":
            gpx.add_EquivConstr(("0::AUiso:%d" % i, "0::AUiso:%d" % j))
        else:
            for axis in ("x", "y", "z"):
                gpx.add_EquivConstr((
                    "0::dA%s:%d" % (axis, i),
                    "0::dA%s:%d" % (axis, j),
                ))
    return G2sc.G2Project(gpxfile=gpx.filename)


def build(a, b, c):
    if os.path.exists(OUT):
        os.remove(OUT)
    gpx = G2sc.G2Project(newgpx=OUT)
    hist = gpx.add_powder_histogram(DATA, INST)
    freeze_instrument(hist, FIXED_PROFILE)
    phase = gpx.add_phase(
        phasename="Bi0.85Nd0.15FeO3",
        spacegroup="P b a m",
        cell=[a, b, c, 90.0, 90.0, 90.0],
        histograms=[hist],
    )
    for label, element, xyz, occ, uiso in SITES:
        phase.add_atom(xyz[0], xyz[1], xyz[2], element, label, occ=occ, uiso=uiso)
    gpx.save()
    return G2sc.G2Project(gpxfile=OUT)


def atom_flags(phase, thermal):
    flag = "XU" if thermal else "X"
    for atom in phase.atoms():
        atom.refinement_flags = flag


def report_model(gpx, title):
    phase = gpx.phase(0)
    cell = phase.get_cell()
    print(title)
    print(
        "  a=%.5f b=%.5f c=%.5f V=%.3f V/Z=%.3f"
        % (cell["length_a"], cell["length_b"], cell["length_c"],
           cell["volume"], cell["volume"] / 8.0)
    )
    for atom in phase.atoms():
        x, y, z = atom.coordinates
        print(
            "  %s %s mult=%s occ=%.3f xyz=(%.4f, %.4f, %.4f) U=%.5f flags=%r"
            % (atom.label, atom.type, atom.mult, atom.occupancy, x, y, z,
               atom.uiso, atom.refinement_flags)
        )


def run_stages(gpx):
    hist = gpx.histogram(0)
    set_cycles(gpx, MAX_CYCLES)
    hist.set_refinements({
        "Sample Parameters": ["Scale"],
        "Background": {"no. coeffs": 6, "refine": True},
    })
    stages = [
        ("scale_background", None),
        ("lattice", "cell"),
        ("atomic_positions", "X"),
        ("thermal", "U"),
        ("background_18", "bg"),
        ("preferred_orientation", "po"),
        ("uniaxial_size", "size"),
    ]
    prev = None
    for name, kind in stages:
        backup = OUT + ".bak_" + name
        gpx.save()
        shutil.copy(OUT, backup)
        gpx = G2sc.G2Project(gpxfile=OUT)
        hist = gpx.histogram(0)
        phase = gpx.phase(0)
        cycles = {"cell": 15, "X": 12, "U": 12}.get(kind, MAX_CYCLES)
        set_cycles(gpx, cycles)
        if kind == "cell":
            phase.set_refinements({"Cell": True})
        elif kind == "X":
            atom_flags(phase, thermal=False)
            gpx.save()
            gpx = tie(gpx, "xyz")
            hist = gpx.histogram(0)
            phase = gpx.phase(0)
        elif kind == "U":
            atom_flags(phase, thermal=True)
            gpx.save()
            gpx = tie(gpx, "xyz")
            gpx = tie(gpx, "U")
            hist = gpx.histogram(0)
            phase = gpx.phase(0)
        elif kind == "bg":
            hist.set_refinements({"Background": {"no. coeffs": BG_FINAL, "refine": True}})
        elif kind == "po":
            enable_md(phase)
            for hap in phase.data["Histograms"].values():
                hap["Pref.Ori."][3] = list(SIZE_AXIS)
        elif kind == "size":
            enable_uniaxial_size(hist, phase)
            for hap in phase.data["Histograms"].values():
                hap["Size"][3] = list(SIZE_AXIS)
        freeze_instrument(hist, FIXED_PROFILE)
        print("[stage] %s cycles=%d" % (name, cycles))
        gpx = refine(gpx)
        rwp = rwp_from_data(gpx)
        cell = gpx.phase(0).get_cell()
        ok = rwp is not None and (prev is None or rwp <= prev * 1.05) and (
            prev is None or rwp < 10.0 * prev
        )
        print(
            "  Rwp=%s cell a=%.4f b=%.4f c=%.4f"
            % ("None" if rwp is None else "%.3f" % rwp,
               cell["length_a"], cell["length_b"], cell["length_c"])
        )
        if not ok:
            print("  rolled back")
            shutil.copy(backup, OUT)
            gpx = G2sc.G2Project(gpxfile=OUT)
        else:
            prev = rwp
    return gpx, prev


def main():
    a_h, c_h, reference = r3c_metric()
    a, b, c = pbam_cell(a_h, c_h)
    print("R3c reference a=%.5f c=%.5f array Rwp=%.3f" % (a_h, c_h, reference))
    print("Pbam start a=%.5f b=%.5f c=%.5f V=%.3f" % (a, b, c, a * b * c))
    gpx = build(a, b, c)
    report_model(gpx, "before refinement")
    bad = [
        atom.label for atom in gpx.phase(0).atoms()
        if atom.mult != EXPECTED_MULT.get(atom.label)
    ]
    if bad:
        raise SystemExit("unexpected multiplicity: %s" % ", ".join(bad))
    gpx, rwp = run_stages(gpx)
    report_model(gpx, "after recipe")
    held = hold_negative_uiso(gpx.phase(0))
    print("hold_negative_uiso: %s" % (", ".join(held) or "none"))
    if held:
        before = rwp
        gpx = refine(gpx)
        rwp = rwp_from_data(gpx)
        print("  after hold Rwp=%.3f (before %.3f)" % (rwp, before))
        report_model(gpx, "after hold")
    rep = validate(OUT)
    print("validators:")
    for check in rep.checks:
        print("  [%s] %s: %s" % (check["status"], check["check"], check["detail"]))
    print(
        "Saved: %s | Rwp=%.3f | GOF=%s | R3c array Rwp=%.3f"
        % (OUT, rwp, gof_stored(gpx), reference)
    )


if __name__ == "__main__":
    main()
