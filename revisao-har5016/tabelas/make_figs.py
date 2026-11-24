import json, os, sys
GSASII_PATH = os.environ.get("GSASII_PATH")
sys.path.insert(0, GSASII_PATH)
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from GSASII import GSASIIscriptable as G2sc
R = "/home/claude"
XS = ["0.025", "0.05", "0.10", "0.15", "0.20"]
def rwp(path):
    try: return json.load(open(path))["final_rwp"]
    except Exception: return None
orig = [9.852, 10.133, 10.907, 12.614, 21.640]
legs = [rwp(f"{R}/out_leg2/legshift/legshift_x{x}_agent_log.json") for x in XS]
nos = [rwp(f"{R}/out_noshift/noshift_x{x}_agent_log.json") for x in XS]
rev = [rwp(f"{R}/out_agent_r1/r1_x{x}_agent_log.json") for x in XS]
xv = [float(x) * 100 for x in XS]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(figsize=(5.6, 3.4))
def line(y, label, color, marker, ls="-"):
    pts = [(a, b) for a, b in zip(xv, y) if b is not None]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], ls, marker=marker, color=color, label=label, lw=1.4, ms=5)
line(orig, "A  transferred profile and zero, no displacement", "#444444", "o")
line(nos, "C  Zero = 0, size + microstrain, no displacement", "#d55e00", "s", "--")
line(legs, "B  transferred profile and zero, displacement refined", "#0072b2", "^")
line(rev, "D  Zero = 0, size + microstrain, displacement refined", "#009e73", "D")
ax.set_xlabel("Nominal Nd content $x$ (%)"); ax.set_ylabel("Array $R_{wp}$ (%)")
ax.set_xticks(xv); ax.set_xticklabels(["2.5", "5", "10", "15", "20"])
ax.set_ylim(8, 28)
ax.legend(frameon=False, fontsize=7.2, loc="upper left")
fig.tight_layout(); fig.savefig("figuras/rwp-variants.pdf"); plt.close(fig)

def curves(path):
    g = G2sc.G2Project(gpxfile=path)
    h = g.histogram(0)
    x = np.asarray(h.getdata("x")); yo = np.asarray(h.getdata("yobs")); yc = np.asarray(h.getdata("ycalc"))
    return x, yo, yc
panels = [("A  transferred profile and zero (array $R_{wp}$ %.2f)" % orig[4], f"{R}/out_leg2/legacy/leg_x0.20.gpx"),
          ("D  displacement refined (array $R_{wp}$ %.2f)" % rev[4], f"{R}/out_agent_r1/r1_x0.20.gpx")]
fig, axs = plt.subplots(2, 1, figsize=(5.6, 4.4), sharex=True, sharey=True)
for ax, (title, p) in zip(axs, panels):
    x, yo, yc = curves(p)
    m = (x >= 20) & (x <= 46)
    ax.plot(x[m], yo[m], color="#444444", lw=0.6, label="observed")
    ax.plot(x[m], yc[m], color="#d55e00", lw=0.6, label="calculated")
    ax.plot(x[m], (yo - yc)[m] - 1500, color="#0072b2", lw=0.6, label="difference")
    ax.set_title(title, fontsize=8, loc="left")
    ax.set_ylabel("Counts")
axs[1].set_xlabel(r"2$\theta$ (deg)")
axs[0].legend(frameon=False, fontsize=7, ncol=3, loc="upper right")
fig.tight_layout(); fig.savefig("figuras/diff-20-legacy-vs-revised.pdf"); plt.close(fig)
print("figs ok", rev, legs, nos)
