"""One-at-a-time sensitivity of the validator verdict to its thresholds.

Usage: python tools/threshold_sensitivity.py OUT.json label1=path1.gpx label2=path2.gpx ...
Re-scores finished projects; nothing is refined.
"""
import json, os, sys
GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import validators as V

GRID = {
    "GOF_TARGET": [2.0, 2.5, 3.0, 4.0, 5.0],
    "UISO_MIN": [0.0, 0.0001, 0.001, 0.002],
    "UISO_MAX": [0.02, 0.05, 0.10],
    "CORR_WARN": [0.80, 0.90, 0.95, 0.99],
    "PROFILE_SHIFT_LIMIT": [0.1, 0.2, 0.5, 1.0, 2.0],
}
DEFAULT = {k: getattr(V, k) for k in GRID}
runs = dict(a.split("=", 1) for a in sys.argv[2:])
out = {}
for label, path in runs.items():
    out[label] = {}
    for name, values in GRID.items():
        for val in values:
            for k, v in DEFAULT.items():
                setattr(V, k, v)
            setattr(V, name, val)
            rep = V.validate(path)
            out[label]["%s=%s" % (name, val)] = {
                "ok": bool(rep.ok),
                "fail": [c["check"] for c in rep.checks if c["status"] == "FAIL"],
            }
for k, v in DEFAULT.items():
    setattr(V, k, v)
json.dump(out, open(sys.argv[1], "w"), indent=1)
for label in out:
    print(label)
    for name, values in GRID.items():
        print("  %-20s %s" % (name, " ".join("%s:%s" % (val, "OK" if out[label]["%s=%s" % (name, val)]["ok"] else "F") for val in values)))
