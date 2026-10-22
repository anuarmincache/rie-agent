"""Nd 10% nominal occupancy on a copy of the R3c control.

Bi 0.90 and Nd 0.10 share (0, 0, 0). Coordinates stay fixed, occupancy is
not refined, and Nd Uiso is tied to Bi. The provisional instrument stays
frozen. results/nd10_controle.gpx is not modified.

    python tools/nd10_nominal.py
"""
import os
import shutil
import sys

GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.join(ROOT, "src"))

from GSASII import GSASIIscriptable as G2sc
from recipe import (
    FIXED_PROFILE, enforce_locks, freeze_instrument, gof_stored, rwp_from_data,
)
from validators import validate

SRC = os.path.join(ROOT, "results", "nd10_controle.gpx")
DST = os.path.join(ROOT, "results", "nd10_nominal.gpx")
RWP_LIMIT = 11.07

shutil.copy(SRC, DST)
gpx = G2sc.G2Project(gpxfile=DST)
phase = gpx.phase(0)
hist = gpx.histogram(0)

bi = phase.atom("Bi1")
bi.occupancy = 0.90
bi.refinement_flags = "U"
nd = phase.add_atom(0.0, 0.0, 0.0, "Nd+3", "Nd1", occ=0.10, uiso=float(bi.uiso))
nd.refinement_flags = "U"
nd.coordinates = (0.0, 0.0, 0.0)
freeze_instrument(hist, FIXED_PROFILE)
gpx.save()

labels = [atom.label for atom in phase.atoms()]
gpx.add_EquivConstr(
    (f"0::AUiso:{labels.index('Bi1')}", f"0::AUiso:{labels.index('Nd1')}")
)

gpx.data["Controls"]["data"]["max cyc"] = 8
gpx.do_refinements([{}])
gpx = G2sc.G2Project(gpxfile=DST)
enforce_locks(gpx.histogram(0), gpx.phase(0), fixed_instrument=True)
for atom in gpx.phase(0).atoms():
    if atom.label == "Nd1":
        atom.refinement_flags = "U"
gpx.save()

gpx = G2sc.G2Project(gpxfile=DST)
rwp = rwp_from_data(gpx)
gof = gof_stored(gpx)
print(f"Rwp={rwp:.3f}  GOF={gof:.3f}")
for atom in gpx.phase(0).atoms():
    print(
        f"  {atom.label:4} occ={atom.occupancy:.3f}  "
        f"Uiso={atom.uiso:.5f}  flags={atom.refinement_flags!r}  "
        f"xyz={tuple(round(v, 5) for v in atom.coordinates)}"
    )
report = validate(DST)
for check in report.checks:
    if check["status"] != "OK":
        print(f"  FAIL {check['check']}: {check['detail']}")
ok = report.ok and rwp is not None and rwp <= RWP_LIMIT
print(f"VERDICT: {'OK' if report.ok else 'FAIL'} | Rwp<={RWP_LIMIT}: {'MET' if ok else 'MISSED'}")
print(f"Saved: {DST}")
