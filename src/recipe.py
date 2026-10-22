"""Lab Bragg-Brentano recipe for BiFeO3 (Nd2.5, Cu Ka).

The numbers and the locks come from the validated Nd2.5 refinement
(Rwp 9.84). Domain knowledge stays here; the agent loop stays generic.

Locks, learned by failed refinements:
- Bi1 coordinates stay fixed. R3c is polar along c, so refining every z
  leaves the origin free and the Hessian singular.
- V and Y are refined in the profile stage, then frozen. SH/L is refined
  for one cycle with Zero held, then frozen. Left free together they
  correlate past 0.90.
- Axial crystallite size along [001] is refined only with instrument X
  frozen. Equatorial size sits on the GSAS-II ceiling (10 um) and is not
  refined. Size and X together correlate at 0.93.
- Uniaxial microstrain, sample shift, transparency and surface roughness
  did not pay 0.05 in Rwp. They are not in this recipe.
"""
import numpy as np

ORIGIN_ANCHOR = "Bi1"
ND_SITE = "Nd1"
FROZEN_AFTER_PROFILE = ("V", "Y", "SH/L")
# Held when the instprm already carries the Nd2.5 hand refinement.
# X and Y are included because the validated size model was refined
# against those held values. They are not a Si/LaB6 calibration.
FIXED_PROFILE = ("U", "V", "W", "X", "Y", "Zero", "SH/L")
BG_FINAL = 18
SIZE_AXIS = (0, 0, 1)
SIZE_EQUATORIAL_UM = 10.0
PO_AXIS = (0, 0, 1)
# Ceiling for a from-scratch run: 1% above the hand-validated Rwp 9.836.
RWP_CEILING = 9.94
# Last-cycle |shift|/esd. U and W above this means the profile is still walking.
PROFILE_SHIFT_LIMIT = 1.0
MAX_CYCLES = 8
PROFILE_CYCLES = 15

STAGES = [
    "scale_background",
    "lattice",
    "profile",
    "asymmetry",
    "atomic_positions",
    "thermal",
    "background_18",
    "preferred_orientation",
    "uniaxial_size",
    "release_y",
]

SAMPLE_STAGES = [
    "scale_background",
    "lattice",
    "atomic_positions",
    "thermal",
    "background_18",
    "preferred_orientation",
    "uniaxial_size",
]

REMEDIATIONS = [
    "fix_correlated_params",
    "extra_cycles",
    "preferred_orientation",
    "background_18",
    "uniaxial_size",
]


def rwp_from_data(gpx):
    """Rwp from the pattern arrays. Stored Covariance Rwp can be stale."""
    hist = gpx.histogram(0)
    yo = np.asarray(hist.getdata("yobs"), dtype=float)
    yc = np.asarray(hist.getdata("ycalc"), dtype=float)
    w = np.asarray(hist.getdata("yweight"), dtype=float)
    denom = np.sum(w * yo ** 2)
    if denom <= 0:
        return None
    return 100.0 * float(np.sqrt(np.sum(w * (yo - yc) ** 2) / denom))


def gof_stored(gpx):
    rv = gpx.data.get("Covariance", {}).get("data", {}).get("Rvals", {})
    gof = rv.get("GOF")
    return None if gof is None else float(gof)


def _inst(hist):
    return hist.data["Instrument Parameters"][0]


def freeze_instrument(hist, keys):
    inst = _inst(hist)
    for key in keys:
        if key in inst and isinstance(inst[key], list) and len(inst[key]) > 2:
            inst[key][2] = False


def pin_origin(phase):
    """Drop the X flag on the polar-axis anchor and on Nd sharing that site."""
    for atom in phase.atoms():
        if atom.label not in (ORIGIN_ANCHOR, ND_SITE):
            continue
        kept = "".join(c for c in str(atom.refinement_flags) if c not in "X ")
        atom.refinement_flags = kept if kept else " "


def set_nominal_nd(phase, fraction):
    """Place Nd on the Bi site at a fixed fraction. Occupancy is not refined.

    Bi and Nd stay at (0, 0, 0). The caller ties the two Uiso values.
    """
    x = float(fraction)
    if not 0.0 < x < 1.0:
        raise ValueError("Nd fraction must be between 0 and 1, got %s" % fraction)
    bi = phase.atom(ORIGIN_ANCHOR)
    if bi is None:
        raise ValueError("phase has no Bi1 site")
    bi.occupancy = 1.0 - x
    bi.coordinates = (0.0, 0.0, 0.0)
    bi.refinement_flags = "U"
    nd = phase.atom(ND_SITE)
    if nd is None:
        nd = phase.add_atom(0.0, 0.0, 0.0, "Nd+3", ND_SITE, occ=x, uiso=float(bi.uiso))
    nd.occupancy = x
    nd.coordinates = (0.0, 0.0, 0.0)
    nd.uiso = float(bi.uiso)
    nd.refinement_flags = "U"
    return nd


def hold_negative_uiso(phase, floor=0.005):
    """Stop refining Uiso values that went negative. Set them to a small positive floor."""
    held = []
    for atom in phase.atoms():
        if float(atom.uiso) >= 0.0001:
            continue
        atom.uiso = float(floor)
        kept = "".join(c for c in str(atom.refinement_flags) if c != "U")
        atom.refinement_flags = kept if kept.strip() else " "
        held.append(atom.label)
    return held


def size_axial_is_refined(phase):
    for hap in phase.data["Histograms"].values():
        size = hap.get("Size")
        if not size or size[0] != "uniaxial":
            continue
        flags = size[2]
        if len(flags) > 1 and bool(flags[1]):
            return True
    return False


def enforce_locks(hist, phase, fixed_instrument=False):
    """Flags that must be off at the end of every stage."""
    if fixed_instrument:
        freeze_instrument(hist, FIXED_PROFILE)
    else:
        freeze_instrument(hist, FROZEN_AFTER_PROFILE)
        if size_axial_is_refined(phase):
            freeze_instrument(hist, ("X",))
    pin_origin(phase)


def enable_md(phase, axis=PO_AXIS):
    phase.set_HAP_refinements({"Pref.Ori.": True})
    for hap in phase.data["Histograms"].values():
        po = hap["Pref.Ori."]
        po[0] = "MD"
        po[2] = True
        po[3] = [int(axis[0]), int(axis[1]), int(axis[2])]


def enable_uniaxial_size(hist, phase):
    """Equatorial size fixed at the GSAS-II ceiling. Refine the axial term only."""
    freeze_instrument(hist, ("X",))
    already = size_axial_is_refined(phase)
    for ph in (phase,):
        ph.set_HAP_refinements({
            "Size": {
                "type": "uniaxial",
                "direction": list(SIZE_AXIS),
                "refine": False,
                "LGmix": {"value": 1.0, "refine": False},
            }
        })
        for hap in ph.data["Histograms"].values():
            size = hap["Size"]
            size[1][2] = 1.0
            if not already:
                size[1][0] = float(SIZE_EQUATORIAL_UM)
                size[1][1] = 1.0
            size[2][0] = False
            size[2][1] = True
            size[2][2] = False
            size[3] = [int(SIZE_AXIS[0]), int(SIZE_AXIS[1]), int(SIZE_AXIS[2])]
    freeze_instrument(hist, ("X",))


def apply_stage(hist, phase, stage):
    """Turn on the flags for one stage. Does not run the refinement."""
    if stage == "scale_background":
        hist.set_refinements({
            "Sample Parameters": ["Scale"],
            "Background": {"no. coeffs": 6, "refine": True},
        })
    elif stage == "lattice":
        phase.set_refinements({"Cell": True})
    elif stage == "profile":
        # One block, long enough to reach the Caglioti basin. V and Y are
        # frozen by enforce_locks after this stage.
        hist.set_refinements({
            "Instrument Parameters": ["U", "V", "W", "X", "Y", "Zero"],
        })
    elif stage == "asymmetry":
        # SH/L correlates with Zero, so Zero is held for this cycle only.
        # The caller turns Zero back on after the refinement.
        freeze_instrument(hist, ("Zero",))
        hist.set_refinements({"Instrument Parameters": ["SH/L"]})
    elif stage == "release_y":
        # X is already frozen by uniaxial size, so Y can move once.
        hist.set_refinements({"Instrument Parameters": ["Y"]})
    elif stage == "atomic_positions":
        phase.set_refinements({"Atoms": {"all": "X"}})
    elif stage == "thermal":
        phase.set_refinements({"Atoms": {"all": "XU"}})
    elif stage == "background_18":
        hist.set_refinements({"Background": {"no. coeffs": BG_FINAL, "refine": True}})
    elif stage in ("preferred_orientation", "preferred_orientation_md"):
        enable_md(phase)
    elif stage == "uniaxial_size":
        enable_uniaxial_size(hist, phase)
    elif stage == "extra_cycles":
        pass
    elif stage == "fix_correlated_params":
        pass
    else:
        raise ValueError("unknown stage: " + str(stage))
    pin_origin(phase)


def reopen_zero(hist):
    hist.set_refinements({"Instrument Parameters": ["Zero"]})


def drop_correlated(hist, report):
    """Turn off the second name of each correlated pair. Never re-enable locks."""
    drops = set()
    for check in report.get("checks", []):
        if check.get("check") != "param_correlations" or check.get("status") != "FAIL":
            continue
        for pair in (check.get("detail") or "").split(";"):
            left = pair.split("=")[0]
            parts = [p.strip() for p in left.split(" x ")]
            if len(parts) == 2:
                drops.add(parts[1].split(":")[-1])
    inst = _inst(hist)
    frozen = []
    for name in sorted(drops):
        if name in FROZEN_AFTER_PROFILE:
            continue
        if name in inst and isinstance(inst[name], list) and len(inst[name]) > 2:
            inst[name][2] = False
            frozen.append(name)
    return frozen
