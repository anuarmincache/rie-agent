"""Free U, V, W and SH/L on top of a finished protocol_r1 project (Zero=0, X=Y=0 stay fixed).
Copies the project, refines up to 30 cycles, reports array Rwp and the profile values.
Usage: python tools/polish_free.py IN.gpx OUT.gpx
"""
import os, shutil, sys
GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from GSASII import GSASIIscriptable as G2sc
from recipe import rwp_from_data
shutil.copy(sys.argv[1], sys.argv[2])
g = G2sc.G2Project(gpxfile=sys.argv[2])
h = g.histogram(0)
before = rwp_from_data(g)
inst = h.data["Instrument Parameters"][0]
for k in ("U", "V", "W", "SH/L"):
    inst[k][2] = True
g.data["Controls"]["data"]["max cyc"] = 30
g.do_refinements([{}])
g.save()
g = G2sc.G2Project(gpxfile=sys.argv[2])
h = g.histogram(0)
inst = h.data["Instrument Parameters"][0]
rv = g.data["Covariance"]["data"]["Rvals"]
print("POLISH before=%.3f after=%.3f GOF=%.3f SVD0=%s" % (before, rwp_from_data(g), rv["GOF"], rv.get("SVD0")),
      {k: round(inst[k][1], 4) for k in ("U", "V", "W", "SH/L")})
