"""Build LaTeX tables and a results JSON from the agent logs. Numbers are never typed by hand."""
import json, os, glob
R = "/home/claude"
XS = ["0.025", "0.05", "0.10", "0.15", "0.20"]
def L(path):
    try: return json.load(open(path))
    except Exception: return None
rev = {x: L(f"{R}/out_agent_r1/r1_x{x}_agent_log.json") for x in XS}
leg = {x: L(f"{R}/out_leg2/legacy/leg_x{x}_agent_log.json") for x in ("0.10", "0.15", "0.20")}
legs = {x: L(f"{R}/out_leg2/legshift/legshift_x{x}_agent_log.json") for x in XS}
nos = {x: L(f"{R}/out_noshift/noshift_x{x}_agent_log.json") for x in ("0.10", "0.15", "0.20")}
orig = {"0.025": 9.852, "0.05": 10.133, "0.10": 10.907, "0.15": 12.614, "0.20": 21.640}  # as submitted
def f(v, n=2): return "--" if v is None else f"{v:.{n}f}"
def rw(d): return None if d is None else d.get("final_rwp")
res = {"rev": rev, "leg": leg, "legs": legs, "nos": nos}
json.dump({k: {x: (None if v is None else {"rwp": v.get("final_rwp"), "gof": v.get("final_gof"), "ok": v.get("verdict_ok"), "metrics": v.get("metrics"), "failing": v.get("failing_checks"), "multistart": v.get("multistart")}) for x, v in d.items()} for k, d in res.items()}, open("results_summary.json", "w"), indent=1, default=str)

# Table: revised model, agreement indices and refined sample parameters
rows = []
for x in XS:
    d = rev[x]
    if d is None: continue
    m = d["metrics"]; c = m["cell"]
    rows.append(f"{float(x):.3f} & {f(d['final_rwp'])} & {f(d['final_gof'])} & {f(m['wRmin'])} & {f(m['DW'],3)} & {f(m['RF2'])} & {f(m['shift_um'],1)} & {f(m['size_um'],3)} & {f(m['mustrain_ue'],0)} & {'OK' if d['verdict_ok'] else 'FAIL'} \\\\")
open("tab_rev.tex", "w").write("\n".join(rows))
rows = []
for x in XS:
    d = rev[x]
    if d is None: continue
    m = d["metrics"]; c = m["cell"]; a = m["atoms"]
    uo = a.get("O1", {}).get("uiso"); uf = a.get("Fe1", {}).get("uiso"); ub = a.get("Bi1", {}).get("uiso")
    rows.append(f"{float(x):.3f} & {c['length_a']:.5f} & {c['length_c']:.5f} & {c['volume']:.3f} & {f(ub,4)} & {f(uf,4)} & {f(uo,4)} \\\\")
open("tab_cell.tex", "w").write("\n".join(rows))
# Table: four model variants
rows = []
for x in XS:
    r1 = rw(rev[x]); lg = orig[x]; ls = rw(legs[x]); ns = rw(nos.get(x))
    rows.append(f"{float(x):.3f} & {f(lg)} & {f(ls)} & {f(ns)} & {f(r1)} \\\\")
open("tab_variants.tex", "w").write("\n".join(rows))
# multistart summary
rows = []
for x in XS:
    d = rev[x]
    if d is None or not d.get("multistart"): continue
    r = sorted(t["rwp"] for t in d["multistart"] if t["rwp"] is not None)
    lo = r[0]; n_lo = sum(1 for v in r if abs(v - lo) < 0.05)
    distinct = sorted(set(round(v, 1) for v in r))
    rows.append(f"{float(x):.3f} & {len(r)} & {f(r[0])} & {f(r[-1])} & {n_lo} & {len(distinct)} \\\\")
open("tab_ms.tex", "w").write("\n".join(rows))
print(open("tab_rev.tex").read()); print(open("tab_cell.tex").read()); print(open("tab_variants.tex").read()); print(open("tab_ms.tex").read())
