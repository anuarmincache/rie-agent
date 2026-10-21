"""Plot a Rietveld fit from a .gpx: observed, calculated, background,
difference curve and Bragg tick marks. Usage:
    python tools/plot_refinement.py RUN.gpx out.png
"""
import sys, os
GSASII_PATH = os.environ.get("GSASII_PATH", os.path.expanduser("~/GSAS-II"))
sys.path.insert(0, GSASII_PATH)
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from GSASII import GSASIIscriptable as G2sc

def plot_fit(gpx_path, out_png):
    g = G2sc.G2Project(gpxfile=gpx_path)
    h = g.histogram(0)
    x = np.asarray(h.getdata("x"))
    yo = np.asarray(h.getdata("yobs"))
    yc = np.asarray(h.getdata("ycalc"))
    yb = np.asarray(h.getdata("background"))
    diff = yo - yc
    rv = g.data["Covariance"]["data"]["Rvals"]
    ticks = []
    for ph, rl in h.reflections().items():
        ref = rl.get("RefList")
        if ref is not None and len(ref):
            ticks.append(np.asarray(ref)[:, 5])
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(x, yo, ".", ms=2, label="observed")
    ax1.plot(x, yc, "-", lw=1, label="calculated")
    ax1.plot(x, yb, "-", lw=0.8, label="background")
    off = -0.08 * yo.max()
    ax1.plot(x, diff + off, "-", lw=0.8, color="gray", label="difference")
    for t in ticks:
        ax1.vlines(t, 1.6 * off, 1.1 * off, color="green", lw=0.7)
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_title(f"{os.path.basename(gpx_path)}  Rwp={float(rv['Rwp']):.2f}%  GOF={float(rv['GOF']):.2f}")
    ax1.set_ylabel("counts")
    ax2.plot(x, diff / np.sqrt(np.maximum(yo, 1)), "-", lw=0.6)
    ax2.axhline(0, color="k", lw=0.5)
    ax2.set_ylabel("(obs-calc)/esd")
    ax2.set_xlabel("2theta (deg)")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    print("saved:", out_png)

if __name__ == "__main__":
    plot_fit(sys.argv[1], sys.argv[2])
