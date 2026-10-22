"""Nd 15% test: one Pnma perovskite, cell taken from the refined R3c metric.

Not the NdFeO3 end-member lattice, and not a second phase on top of R3c.
Hexagonal a and c from results/nd15_auto.gpx become an untilted Pnma cell
with the same volume per formula unit (R3c Z=6, Pnma Z=4):

    a = c = a_hex
    b = c_hex / sqrt(3)

Fractional coordinates are the NdFeO3 tilt (COD 2003124). Occupancy is
nominal and fixed: Bi 0.85, Nd 0.15 on the A site. Nd coordinates and
Uiso are constrained to Bi. The instrument stays the provisional one.
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
OUT = os.path.join(ROOT, "results", "nd15_pnma.gpx")
# NdFeO3 (COD 2003124) axial ratio, scaled later onto the Nd15 volume.
ENDO_A, ENDO_B, ENDO_C = 5.5887, 7.7619, 5.4489

# COD 2003124 fractional coordinates. The lattice below replaces that CIF cell.
A_XYZ = (0.04907, 0.25000, -0.01088)
FE_XYZ = (0.00000, 0.00000, 0.50000)
O1_XYZ = (0.4760, 0.25000, 0.0866)
O2_XYZ = (-0.2949, -0.0459, 0.2955)
ND_FRACTION = 0.15
SIZE_AXIS = [0, 1, 0]


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
    a_h = float(cell["length_a"])
    c_h = float(cell["length_c"])
    reference = rwp_from_data(src)
    return a_h, c_h, reference


def pnma_cell(a_h, c_h, strained):
    """Untilted R3c metric, or the NdFeO3 shape scaled to that volume."""
    a = a_h
    b = c_h / math.sqrt(3.0)
    c = a_h
    if not strained:
        return a, b, c
    target = a * b * c
    scale = (target / (ENDO_A * ENDO_B * ENDO_C)) ** (1.0 / 3.0)
    return ENDO_A * scale, ENDO_B * scale, ENDO_C * scale


def build(a, b, c, out_path):
    if os.path.exists(out_path):
        os.remove(out_path)
    gpx = G2sc.G2Project(newgpx=out_path)
    hist = gpx.add_powder_histogram(DATA, INST)
    freeze_instrument(hist, FIXED_PROFILE)
    phase = gpx.add_phase(
        phasename="Bi0.85Nd0.15FeO3",
        spacegroup="P n m a",
        cell=[a, b, c, 90.0, 90.0, 90.0],
        histograms=[hist],
    )
    phase.add_atom(*A_XYZ, "Bi+3", "Bi1", occ=1.0 - ND_FRACTION, uiso=0.008)
    phase.add_atom(*A_XYZ, "Nd+3", "Nd1", occ=ND_FRACTION, uiso=0.008)
    phase.add_atom(*FE_XYZ, "Fe+3", "Fe1", occ=1.0, uiso=0.008)
    phase.add_atom(*O1_XYZ, "O-2", "O1", occ=1.0, uiso=0.01)
    phase.add_atom(*O2_XYZ, "O-2", "O2", occ=1.0, uiso=0.01)
    gpx.save()
    # Same site: Nd moves with Bi. Occupancy is not a refined flag.
    gpx.add_EquivConstr(("0::dAx:0", "0::dAx:1"))
    gpx.add_EquivConstr(("0::dAy:0", "0::dAy:1"))
    gpx.add_EquivConstr(("0::dAz:0", "0::dAz:1"))
    return G2sc.G2Project(gpxfile=out_path)


def atom_flags(phase, thermal):
    flag = "XU" if thermal else "X"
    for atom in phase.atoms():
        if atom.label == "Fe1":
            atom.refinement_flags = "U" if thermal else " "
        else:
            atom.refinement_flags = flag


def report_model(gpx, title):
    phase = gpx.phase(0)
    cell = phase.get_cell()
    print(title)
    print(
        "  a=%.5f b=%.5f c=%.5f V=%.3f"
        % (cell["length_a"], cell["length_b"], cell["length_c"], cell["volume"])
    )
    for atom in phase.atoms():
        x, y, z = atom.coordinates
        print(
            "  %s %s occ=%.3f xyz=(%.4f, %.4f, %.4f) U=%.5f flags=%r"
            % (atom.label, atom.type, atom.occupancy, x, y, z, atom.uiso, atom.refinement_flags)
        )


def run_stages(gpx, out_path):
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
        backup = out_path + ".bak_" + name
        gpx.save()
        shutil.copy(out_path, backup)
        gpx = G2sc.G2Project(gpxfile=out_path)
        hist = gpx.histogram(0)
        phase = gpx.phase(0)
        set_cycles(gpx, 20 if kind == "cell" else MAX_CYCLES)
        if kind == "cell":
            phase.set_refinements({"Cell": True})
        elif kind == "X":
            atom_flags(phase, thermal=False)
        elif kind == "U":
            atom_flags(phase, thermal=True)
            gpx.save()
            # Added here: an earlier Uiso equivalence is dropped while U is still fixed.
            gpx.add_EquivConstr(("0::AUiso:0", "0::AUiso:1"))
            gpx = G2sc.G2Project(gpxfile=out_path)
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
        print("[stage] %s" % name)
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
            shutil.copy(backup, out_path)
            gpx = G2sc.G2Project(gpxfile=out_path)
        else:
            prev = rwp
    return gpx, prev


def one_run(a_h, c_h, reference, strained, out_path):
    a, b, c = pnma_cell(a_h, c_h, strained)
    print(
        "Pnma start a=%.5f b=%.5f c=%.5f V=%.3f strained=%s"
        % (a, b, c, a * b * c, strained)
    )
    gpx = build(a, b, c, out_path)
    report_model(gpx, "before refinement")
    gpx, rwp = run_stages(gpx, out_path)
    report_model(gpx, "after recipe")
    held_labels = hold_negative_uiso(gpx.phase(0))
    print("hold_negative_uiso: %s" % (", ".join(held_labels) or "none"))
    if held_labels:
        before = rwp
        gpx = refine(gpx)
        rwp = rwp_from_data(gpx)
        print("  after hold Rwp=%.3f (before %.3f)" % (rwp, before))
        report_model(gpx, "after hold")
    rep = validate(out_path)
    print("validators:")
    for check in rep.checks:
        print("  [%s] %s: %s" % (check["status"], check["check"], check["detail"]))
    gof = gof_stored(gpx)
    print(
        "Saved: %s | Rwp=%.3f | GOF=%s | R3c array Rwp=%.3f"
        % (out_path, rwp, gof, reference)
    )


def main():
    a_h, c_h, reference = r3c_metric()
    print("R3c reference a=%.5f c=%.5f array Rwp=%.3f" % (a_h, c_h, reference))
    strained = "--strain" in sys.argv
    out_path = os.path.join(ROOT, "results", "nd15_pnma_strain.gpx" if strained else "nd15_pnma.gpx")
    one_run(a_h, c_h, reference, strained, out_path)


if __name__ == "__main__":
    main()
