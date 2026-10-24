#!/usr/bin/env python3
"""Evertonians prybar handle, v0.5 -- clean rewrite (Oct 2026).

Geometry is FROZEN at v0.5.3. The v0.5.4 pass tidied the code only
(grouped constants, clearer sections, argparse CLI); no formula,
constant or mesh-generation step changed. The v0.5.5 pass adds
MISSING / SHORTENED FINGER support (amputee and nub hands):

  * a null entry in finger_lengths = finger NOT PRESENT: that
    finger's groove and the ridges beside it are omitted, and its
    width/thickness/web entries are filled from the fingers that
    ARE present (row spacing is preserved);
  * a null thumb_length = no thumb: the thumb channel is omitted
    (thumb_breadth may then be null too);
  * per-finger ranges widened for nubs (width 5-30, length 5-115,
    thickness 4-30 mm; thumb length 8-105, breadth 8-36 mm); a
    web_spaces entry may be null when a neighbouring finger is
    missing;
  * a fully intact hand rebuilds BYTE-IDENTICALLY to v0.5.4: every
    new path is a no-op when all four fingers and the thumb are
    present.

Every value the generator fills is recorded in the params JSON under
_provenance.v055_fills.

The sculpted body is the validated v0.4.4 right-hand model (verified
feature-for-feature against the published v0.4.4 STL). Since v0.4.4:
  * the bar stub ("the nub") comes out of the THUMB side -- the end
    where the thumb imprint and the index groove sit -- and the
    rounded cap closes the pinkie end;
  * the thumb channel sits ON TOP, ROTATED 15 degrees about its own
    midpoint: rear end at 105 deg, midpoint at 90 deg, tip end at
    75 deg (tip toward the palm flank).

    x = 0        flat stub face (start of the prying piece, thumb side)
    x = 12..22   stub -> body blend
    x = 24..82   palm swell on the +Y flank; finger grooves x = 33..144
                 (index nearest the stub, pinkie nearest the cap)
    x = 147..171 rounded cap (dome), apex at the far end
    theta: 0 = +Y palm flank, 90 = +Z top (thumb channel midpoint),
            270 = -Z underside (fingers)

Usage:
    python3 grip_generator_v05.py hand.json [-o OUTDIR] [--name NAME]
                                            [--palm-side right|left]
Outputs NAME.stl (binary), NAME_params.json, NAME_preview.svg, and prints
a stats JSON (watertight, volume, feature audit) to stdout.
No dependencies. Python 3 only.
"""

import argparse
import json
import math
import os
import struct

# ---------------------------------------------------------------------------
# Tunables. Every number that shapes the handle lives in K.
#   calibrated = from the clay-imprint analysis; photo = from the user's
#   grip photos; default = sensible default, confirm with a bracket print.
# ---------------------------------------------------------------------------
K = {
    # -- core cross-section (superellipse, tapered along the grip) --------
    "K_DIAM":        0.70,   # calibrated: core diameter = K_DIAM x grip_diameter_inside
    "WT":            1.08,   # default: cross-section width/thickness ratio
    "N_EXP":         2.40,   # default: superellipse exponent
    "TAPER_REAR":    1.06,   # default: flare at the stub end of the grip
    "TAPER_FRONT":   0.97,   # default: slim taper at the cap end

    # -- finger grooves (underside) ----------------------------------------
    "K_DEPTH":       0.11,   # calibrated: groove depth = K_DEPTH x finger_thickness
    "K_WEB":         0.70,   # default: inter-finger gap = K_WEB x web_space
    "K_RIDGE":       0.025,  # user halved 3x: ridge bump = K_RIDGE x web_space
    "K_CURL":        0.10,   # photo: fingertip drift = K_CURL x finger_length
    "K_WTAPER":      0.25,   # default: groove narrows toward the fingertip
    "K_WRAP":        0.62,   # default: wrap angle (rad) = K_WRAP x length / r_core
    "K_WRAP_MIN":    100.0,  # deg, physical clip on groove wrap
    "K_WRAP_MAX":    165.0,  # deg, physical clip on groove wrap
    "K_ROOT":        20.0,   # deg below the palm flank where grooves start
    "K_FALL":        20.0,   # deg: angular fade past the fingertip landing
    "K_EDGE":        0.12,   # default: feature edge blend x mean finger width

    # -- thumb channel (top) -----------------------------------------------
    "K_THUMB_W":     1.04,   # calibrated: channel width vs thumb_breadth
    "K_THUMB_D":     0.15,   # default: channel depth basis (thumb_thickness)
    "K_THUMB_TAPER": 0.35,   # default: channel narrows toward the tip
    "K_THUMB_ANGLE": 90.0,   # deg: channel MIDPOINT (dead top)
    "K_THUMB_TILT":  -15.0,  # user Oct 2026: the channel ROTATES about its
                             # midpoint, it does not shift (sign corrected
                             # by user on v0.5.2): rear end at ANGLE-TILT,
                             # tip end at ANGLE+TILT -> rear 105, tip 75 deg.
                             # Flip the sign to reverse the rotation.

    # -- palm swell ----------------------------------------------------------
    "K_SWELL":       0.03,   # default: swell height = K_SWELL x hand_breadth
    "SWELL_ARC":     55.0,   # default: swell half-width in theta (deg)
    "SWELL_RAMP":    6.0,    # v0.4.4-fit: swell axial ramp length (mm)
    "K_PALM":        0.55,   # default: swell extent = K_PALM x palm_length

    # -- ends: bar stub, blend, dome cap --------------------------------------
    "STUB_K":        0.40,   # default: stub radius = STUB_K x r_core
    "STUB_LEN":      12.0,   # mm, bar stub length
    "BLEND":         10.0,   # mm, body -> stub blend length
    "DOME_K":        1.25,   # default: cap length = DOME_K x r_core
    "THUMB_LEN_K":   0.65,   # default: channel length vs thumb_length

    # -- mesh resolution -------------------------------------------------------
    "N_THETA":       160,    # facets per ring
    "DOME_STEPS":    20,     # dome stations
    "BODY_STEP":     0.8,    # mm, body station spacing
    "BLEND_STEPS":   9,      # blend stations
    "STUB_STEP":     1.5,    # mm, stub station spacing
}

FINGERS = ["index", "middle", "ring", "pinkie"]

# Required inputs and loose adult-plausibility ranges (mm).
REQUIRED = {
    "hand_length": (140, 235), "hand_breadth": (60, 115),
    "palm_length": (80, 130), "grip_diameter_inside": (30, 85),
    "thumb_length": (8, 105), "thumb_breadth": (8, 36),  # null = no thumb
}
PER_FINGER = {
    # v0.5.5: null entries are allowed in the lists (filled from the
    # measured fingers); a null finger_lengths entry = no finger.
    "finger_widths": (5, 30), "finger_lengths": (5, 115),
    "finger_thicknesses": (4, 30),
}
WEB_RANGE = (0, 25)

# Where every measurement the user provides is used (input wiring audit).
WIRING = {
    "hand_length":          "handle-length bound (handle must fit within it)",
    "hand_breadth":         "palm swell height (K_SWELL)",
    "palm_length":          "palm swell extent along the handle (K_PALM)",
    "grip_diameter_inside": "core diameter (K_DIAM x 0.5)",
    "thumb_length":         "thumb channel length (THUMB_LEN_K); null = no thumb channel",
    "thumb_breadth":        "thumb channel width (K_THUMB_W)",
    "thumb_thickness":      "thumb channel depth basis (K_THUMB_D), optional",
    "palm_depth":           "optional, unused in v0.5 (kept for compatibility)",
    "finger_widths":        "groove size, spacing and positions",
    "finger_lengths":       "groove wrap angles (K_WRAP) and curl drift (K_CURL); null = no groove",
    "finger_thicknesses":   "groove depths (K_DEPTH)",
    "web_spaces":           "inter-finger gaps (K_WEB) and ridge heights (K_RIDGE)",
}


# ---------------------------------------------------------------------------
# Small math helpers
# ---------------------------------------------------------------------------
def clamp01(u):
    return min(max(u, 0.0), 1.0)


def smooth01(u):
    """Quintic smoothstep (C2-continuous, flat at both ends)."""
    u = clamp01(u)
    return u * u * u * (10.0 - 15.0 * u + 6.0 * u * u)


def wrap180(deg):
    """Map an angle (deg) into [-180, 180)."""
    return (deg + 180.0) % 360.0 - 180.0


def lerp(a, b, t):
    return a + (b - a) * t


def raised_cos(delta_deg, half_deg):
    """Raised-cosine bump: 1 at 0, 0 beyond half_deg, smooth at both."""
    if abs(delta_deg) >= half_deg:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * delta_deg / half_deg))


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------
def load_hand(path):
    """Load and validate hand.json -> (values, provenance)."""
    with open(path) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("hand JSON must be an object")

    def four(key, lo, hi):
        """A single number counts for all four fingers. v0.5.5: a null
        entry = value not available (filled from the measured fingers);
        a null finger_lengths entry = the finger is not there."""
        v = raw.get(key)
        if isinstance(v, (int, float)):
            v = [float(v)] * 4
        if not isinstance(v, list) or len(v) != 4:
            raise ValueError("'%s' must be a number or a list of 4" % key)
        out = []
        for x in v:
            if x is None:
                out.append(None)
            elif not (lo <= float(x) <= hi):
                raise ValueError("'%s' value %g outside %g-%g mm "
                                 "(null = finger not present or not measured)"
                                 % (key, x, lo, hi))
            else:
                out.append(float(x))
        return out

    val = {}
    for key, (lo, hi) in REQUIRED.items():
        if key not in raw:
            raise ValueError("missing required input '%s'" % key)
        if raw[key] is None:
            if key not in ("thumb_length", "thumb_breadth"):
                raise ValueError("'%s' must be a number (only thumb_length "
                                 "and thumb_breadth may be null = no thumb)" % key)
            val[key] = None
            continue
        v = float(raw[key])
        if not (lo <= v <= hi):
            raise ValueError("'%s' value %g outside %g-%g mm" % (key, v, lo, hi))
        val[key] = v
    for key, (lo, hi) in PER_FINGER.items():
        if key not in raw:
            raise ValueError("missing required input '%s'" % key)
        val[key] = four(key, lo, hi)
    webs = raw.get("web_spaces")
    if not isinstance(webs, list) or len(webs) != 3:
        raise ValueError("'web_spaces' must be a list of 3 numbers (null "
                         "allowed where a neighbouring finger is missing)")
    for w in webs:
        if w is not None and not (WEB_RANGE[0] <= float(w) <= WEB_RANGE[1]):
            raise ValueError("web_space %g outside %g-%g mm" % (w, *WEB_RANGE))
    val["web_spaces"] = [None if w is None else float(w) for w in webs]

    # Optional inputs.
    val["palm_depth"] = float(raw["palm_depth"]) if raw.get("palm_depth") else None
    val["thumb_thickness"] = (float(raw["thumb_thickness"])
                              if raw.get("thumb_thickness") else None)

    # ------------------------------------------------------------------
    # v0.5.5 missing / shortened finger handling. A null finger_lengths
    # entry = finger NOT PRESENT: the geometry leaves out that groove
    # and the ridges beside it. Widths and thicknesses may be null for
    # any finger and are filled from the measured ones (they set the
    # row spacing and, for present fingers, the groove depth). Web
    # gaps may be null (filled from the measured gaps). The thumb may
    # be null. Every fill is recorded in the provenance.
    # ------------------------------------------------------------------
    fills = {}
    fl = val["finger_lengths"]
    if not any(x is not None for x in fl):
        raise ValueError("at least one of the four fingers must be present "
                         "(every finger_lengths entry is null)")
    for key in ("finger_widths", "finger_thicknesses"):
        arr = val[key]
        meas = [x for x in arr if x is not None]
        if not meas:
            raise ValueError("'%s': at least one finger needs a measured "
                             "value (the rest can be null)" % key)
        mean = sum(meas) / len(meas)
        for i in range(4):
            if arr[i] is None:
                arr[i] = mean
                fills["%s[%d]" % (key, i)] = (
                    "mean of the measured values" if fl[i] is not None else
                    "spacing fill (finger not present)")
    for i in range(4):
        if fl[i] is None:
            fl[i] = 0.0
            fills["finger_lengths[%d]" % i] = "no groove (finger not present)"
    webs = val["web_spaces"]
    wmeas = [w for w in webs if w is not None]
    wfill = (sum(wmeas) / len(wmeas)) if wmeas else 6.0
    for j in range(3):
        if webs[j] is None:
            webs[j] = wfill
            fills["web_spaces[%d]" % j] = ("mean of the measured gaps"
                                           if wmeas else "typical 6 mm")
    if val["thumb_length"] is None:
        if val["thumb_breadth"] is not None:
            fills["thumb_breadth"] = "ignored (thumb not present)"
        val["thumb_breadth"] = None
        fills["thumb_length"] = "no thumb channel (thumb not present)"
    elif val["thumb_breadth"] is None:
        raise ValueError("'thumb_breadth' is required when the thumb is "
                         "present (only thumb_length may be null = no thumb)")
    prov = dict(raw.get("_provenance", {}))
    if fills:
        prov["v055_fills"] = fills
    return val, prov


# ---------------------------------------------------------------------------
# Layout: measurements -> feature positions
# ---------------------------------------------------------------------------
def layout(val):
    """All derived sizes and positions (mm / deg) in one dict."""
    r_core = 0.5 * K["K_DIAM"] * val["grip_diameter_inside"]
    r_dome = K["DOME_K"] * r_core
    r_stub = K["STUB_K"] * r_core
    edge = K["K_EDGE"] * (sum(val["finger_widths"]) / 4.0)
    half = [0.5 * w for w in val["finger_widths"]]
    w = val["finger_widths"]
    t = val["finger_thicknesses"]
    webs, fl = val["web_spaces"], val["finger_lengths"]   # fl[i] = 0.0 if not present
    pitch = [0.5 * (w[i] + w[i + 1]) + K["K_WEB"] * webs[i] for i in range(3)]

    # Finger row: INDEX nearest the stub (thumb side), pinkie nearest the
    # cap (v0.4.4 order). c1 clears the thumb channel's rear edge from the
    # blend.
    tl = val["thumb_length"] or 0.0        # v0.5.5: None = no thumb channel
    hl_thumb = 0.5 * K["THUMB_LEN_K"] * tl
    c1 = max(r_dome + 1.5 + half[0] + 1.0,
             r_dome + 1.0 + hl_thumb + edge)
    centers = [c1,
               c1 + pitch[0],
               c1 + pitch[0] + pitch[1],
               c1 + pitch[0] + pitch[1] + pitch[2]]
    row_lo = centers[0] - 1.3 * half[0] - edge
    row_hi = centers[3] + 1.3 * half[3] + edge
    x_grip0 = r_dome                                    # flare zone start
    x_grip1 = max(row_hi, centers[0] + hl_thumb + edge) + 3.0  # grip end

    wraps = [max(K["K_WRAP_MIN"], min(K["K_WRAP_MAX"],
             math.degrees(K["K_WRAP"] * L / r_core))) for L in fl]
    # v0.5.5: a finger that is not present (length 0) gets no groove:
    # zero extent switches off the groove AND the ridges beside it.
    groove_extents = [wraps[i] + K["K_FALL"] if fl[i] > 0.0 else 0.0
                      for i in range(4)]
    depths = [K["K_DEPTH"] * ti for ti in t]
    ridge_h = [K["K_RIDGE"] * webs[j] for j in range(3)]
    ridge_c = [0.5 * (centers[j] + half[j] + centers[j + 1] - half[j + 1])
               for j in range(3)]

    swell_amp = K["K_SWELL"] * val["hand_breadth"]
    x_swell_end = x_grip0 + K["K_PALM"] * val["palm_length"]
    thumb_depth = K["K_THUMB_D"] * (val["thumb_thickness"] or val["thumb_breadth"] or 0.0)
    tb = val["thumb_breadth"] or 0.0       # v0.5.5: None = no thumb channel
    thumb_arc_half = math.degrees(0.5 * K["K_THUMB_W"] * tb / r_core)
    A = r_core * K["WT"]

    return {
        "r_core": r_core, "r_dome": r_dome, "r_stub": r_stub, "A": A,
        "edge_mm": edge, "scallop_centers": centers, "scallop_half": half,
        "scallop_depths": depths, "groove_wrap_deg": wraps,
        "groove_extents": groove_extents,
        "ridge_centers": ridge_c, "ridge_heights": ridge_h,
        "row_lo": row_lo, "row_hi": row_hi,
        "x_grip0": x_grip0, "x_grip1": x_grip1,
        "x_swell_end": x_swell_end, "swell_amp": swell_amp,
        "c_thumb": centers[0], "hl_thumb": hl_thumb,
        "thumb_depth": thumb_depth, "thumb_arc_half": thumb_arc_half,
        "tip_drift_mm": [K["K_CURL"] * L for L in fl],
        "r_envelope": A * K["TAPER_REAR"] * 1.02 + swell_amp,
        "total_length": x_grip1 + r_dome,
        "handle_within_hand": x_grip1 + r_dome <= val["hand_length"],
    }


# ---------------------------------------------------------------------------
# Surface radius r(x, theta) -- the whole handle shape in one function
# ---------------------------------------------------------------------------
def make_radius(val, L, with_fingers=True):
    """Return r(x, theta). with_fingers=False omits grooves/ridges."""
    A, B, n = L["A"], L["r_core"], K["N_EXP"]
    centers = L["scallop_centers"]
    halves, depths = L["scallop_half"], L["scallop_depths"]
    wraps, ridge_c = L["groove_wrap_deg"], L["ridge_centers"]
    ridge_h = L["ridge_heights"]
    fl, edge = val["finger_lengths"], L["edge_mm"]
    ROOT = -K["K_ROOT"]
    extents = L["groove_extents"]        # v0.5.5: 0.0 = finger not present
    CURL, WTAP = K["K_CURL"], K["K_WTAPER"]

    def taper(x):
        """Cross-section scale factor along the grip (rear flare -> cap)."""
        if x <= L["x_grip0"]:
            return K["TAPER_REAR"]
        if x >= L["x_grip1"]:
            return K["TAPER_FRONT"]
        t = (x - L["x_grip0"]) / (L["x_grip1"] - L["x_grip0"])
        return lerp(K["TAPER_REAR"], K["TAPER_FRONT"], t)

    def core(x, theta):
        """Superellipse cross-section, tapered along the grip."""
        ct, st = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        base = (abs(ct / A) ** n + abs(st / B) ** n) ** (-1.0 / n)
        return base * taper(x)

    def swell(x, theta):
        """Palm swell: raised-cosine ridge on the palm flank (theta ~ 0)."""
        if not (L["x_grip0"] <= x <= L["x_swell_end"]):
            return 0.0
        r = K["SWELL_RAMP"]
        axial = smooth01((x - L["x_grip0"]) / r) \
            * (1.0 - smooth01((x - (L["x_swell_end"] - r)) / r))
        return L["swell_amp"] * axial * raised_cos(wrap180(theta), K["SWELL_ARC"])

    def arc(theta):
        """Wrap arc (deg) walked from the groove root, down the underside."""
        return (360.0 - (theta - ROOT) % 360.0) % 360.0

    def drift(i, a):
        """Curl drift of groove i's centerline at wrap arc a: the fingertips
        converge toward the thumb/index side -- the STUB side (small x)."""
        u = min(a / extents[i], 1.0)
        return CURL * fl[i] * u * u

    def groove_ax(i, xq, u):
        """Axial ovoid bowl: quintic dome peaking at the groove centerline,
        zero at the neighbouring ridge centers (row ends for end grooves)."""
        c = centers[i]
        if i == 0:
            nb, far = ridge_c[0], (L["row_hi"] if c > ridge_c[0] else L["row_lo"])
        elif i == 3:
            nb, far = ridge_c[2], (L["row_lo"] if c < ridge_c[2] else L["row_hi"])
        else:
            nb, far = ridge_c[i - 1], ridge_c[i]
        left, right = min(nb, far), max(nb, far)
        sl = max((c - left) * (1.0 - WTAP * u), 1e-6)
        sh = max((right - c) * (1.0 - WTAP * u), 1e-6)
        t = xq - c
        return smooth01(1.0 + t / sl) if t <= 0.0 else 1.0 - smooth01(t / sh)

    def groove_ang(i, a):
        """Angular profile: quintic rise from the root, peak exactly at the
        fingertip landing, quintic fade past it. No flat shelf."""
        E = extents[i]
        if a <= 0.0 or a >= E:
            return 0.0
        u, u_tip = a / E, wraps[i] / E
        rise = smooth01(a / wraps[i]) if wraps[i] > 0.0 else 1.0
        fall = 1.0 - smooth01((u - u_tip) / (1.0 - u_tip)) if u > u_tip else 1.0
        return rise * fall

    def relief(x, theta):
        """Grooves (negative) and ridges (positive) on the underside."""
        a = arc(theta)
        if a <= 0.0 or a >= max(extents):
            return 0.0
        dmax = CURL * max(fl)
        if x < L["row_lo"] - dmax - 1.0 or x > L["row_hi"] + 1.0:
            return 0.0
        total = 0.0
        for i in range(4):
            if a < extents[i]:
                u = min(a / extents[i], 1.0)
                wa = groove_ax(i, x + drift(i, a), u)
                if wa > 0.0:
                    total -= wa * depths[i] * groove_ang(i, a)
        for j in range(3):
            ga = min(groove_ang(j, a), groove_ang(j + 1, a))
            if ga <= 0.0:
                continue
            dR = 0.5 * (drift(j, a) + drift(j + 1, a))
            uj = min(a / extents[j], 1.0)
            ujp = min(a / extents[j + 1], 1.0)
            e0 = centers[j] + (ridge_c[j] - centers[j]) * (1.0 - WTAP * uj)
            e1 = centers[j + 1] + (ridge_c[j] - centers[j + 1]) * (1.0 - WTAP * ujp)
            lo, hi = min(e0, e1), max(e0, e1)
            if lo < x + dR < hi:
                total += (math.sin(math.pi * (x + dR - lo) / (hi - lo)) ** 2) \
                    * ridge_h[j] * ga
        return total

    def thumb_cut(x, theta):
        """Thumb channel ON TOP, ROTATED about its own midpoint (v0.5.3):
        the angular center ramps linearly from K_THUMB_ANGLE - K_THUMB_TILT
        at the rear end to K_THUMB_ANGLE + K_THUMB_TILT at the tip; the
        midpoint stays at K_THUMB_ANGLE. The negative tilt (user-corrected)
        leans the tip toward the palm flank: rear 105 -> mid 90 -> tip 75."""
        t = smooth01((x - L["c_thumb"]) / max(2.0 * L["hl_thumb"], 1e-6))
        u = clamp01((x - (L["c_thumb"] - L["hl_thumb"]))
                    / max(2.0 * L["hl_thumb"], 1e-6))
        ctr = K["K_THUMB_ANGLE"] + K["K_THUMB_TILT"] * (2.0 * u - 1.0)
        across = raised_cos(wrap180(theta - ctr),
                            L["thumb_arc_half"] * (1.0 - K["K_THUMB_TAPER"] * t))
        if across <= 0.0:
            return 0.0
        half = L["hl_thumb"] + edge
        tx = x - L["c_thumb"]
        px = smooth01(1.0 + tx / half) if tx <= 0.0 else 1.0 - smooth01(tx / half)
        return L["thumb_depth"] * px * across if px > 0.0 else 0.0

    def radius(x, theta):
        r = core(x, theta) + swell(x, theta) - thumb_cut(x, theta)
        if with_fingers:
            r += relief(x, theta)
        # Never-exceed envelope: nothing pokes beyond the max designed radius.
        return min(max(r, 1.0), L["r_envelope"])

    return radius


# ---------------------------------------------------------------------------
# Mesh: one closed shell -- flat stub face at x=0, dome apex at the far end
# ---------------------------------------------------------------------------
def build_mesh(val, L, palm_side="right"):
    radius = make_radius(val, L)
    N = K["N_THETA"]
    thetas = [360.0 * k / N for k in range(N)]
    r_stub_rel = L["r_stub"] / L["r_core"]
    x_stub = K["STUB_LEN"]
    x_blend_end = x_stub + K["BLEND"]

    # stations: (x, cap_scale, mode, t) from the stub end to the dome apex
    st = []
    x = K["STUB_STEP"]                                   # bar stub
    while x < x_stub - 1e-9:
        st.append((x, r_stub_rel, "stub", 1.0))
        x += K["STUB_STEP"]
    st.append((x_stub, r_stub_rel, "stub", 1.0))
    for i in range(1, K["BLEND_STEPS"] + 1):             # stub -> body blend
        t = i / float(K["BLEND_STEPS"])
        st.append((lerp(x_stub, x_blend_end, t),
                   lerp(r_stub_rel, 1.0, t), "blend", t))
    x = x_blend_end + K["BODY_STEP"]                     # grip body
    while x < L["x_grip1"]:
        st.append((x, 1.0, "body", 0.0))
        x += K["BODY_STEP"]
    st.append((L["x_grip1"], 1.0, "body", 0.0))
    for j in range(K["DOME_STEPS"] - 1, 0, -1):          # front dome -> apex
        phi = 0.5 * math.pi * j / K["DOME_STEPS"]
        st.append((L["x_grip1"] + L["r_dome"] * math.cos(phi),
                   math.sin(phi), "body", 0.0))

    verts, rings = [], []
    for (xs, cap, mode, bt) in st:
        ring = []
        for th in thetas:
            if mode == "blend":
                # blend circle -> superellipse (A grows, n -> N_EXP)
                eff_A = lerp(L["r_core"], L["A"], bt)
                eff_n = lerp(2.0, K["N_EXP"], bt)
                ct, s = math.cos(math.radians(th)), math.sin(math.radians(th))
                r = (abs(ct / eff_A) ** eff_n + abs(s / L["r_core"]) ** eff_n) \
                    ** (-1.0 / eff_n) * cap
            else:
                r = radius(xs, th) * cap
            ring.append(len(verts))
            verts.append((xs, r * math.cos(math.radians(th)),
                          r * math.sin(math.radians(th))))
        rings.append(ring)

    tris = []
    for j in range(len(rings) - 1):
        r0, r1 = rings[j], rings[j + 1]
        for k in range(N):
            k2 = (k + 1) % N
            tris.append((r0[k], r0[k2], r1[k]))
            tris.append((r0[k2], r1[k2], r1[k]))
    face0 = len(verts)                                  # flat stub face (x=0)
    verts.append((0.0, 0.0, 0.0))
    for k in range(N):
        tris.append((face0, rings[0][(k + 1) % N], rings[0][k]))
    apex = len(verts)                                   # dome apex (x = total)
    verts.append((st[-1][0], 0.0, 0.0))
    for k in range(N):
        tris.append((apex, rings[-1][k], rings[-1][(k + 1) % N]))

    if palm_side == "left":                              # left hand: y-mirror
        verts = [(x, -y, z) for (x, y, z) in verts]
        tris = [(a, c, b) for (a, b, c) in tris]
    return verts, tris


# ---------------------------------------------------------------------------
# Stats: watertight checks, volume, feature probes
# ---------------------------------------------------------------------------
def mesh_stats(verts, tris, L, radius):
    edges = {}
    for (a, b, c) in tris:
        for (u, v) in ((a, b), (b, c), (c, a)):
            e = (u, v) if u < v else (v, u)
            edges[e] = edges.get(e, 0) + 1
    vol = 0.0
    for (a, b, c) in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        vol += (va[0] * (vb[1] * vc[2] - vb[2] * vc[1])
                - va[1] * (vb[0] * vc[2] - vb[2] * vc[0])
                + va[2] * (vb[0] * vc[1] - vb[1] * vc[0])) / 6.0
    closed = all(c == 2 for c in edges.values())
    watertight = (len(verts) - len(edges) + len(tris) == 2
                  and closed and vol > 0.0)

    def theta(v):
        return math.degrees(math.atan2(v[2], v[1])) % 360.0

    def probe(xc, band, pick):
        """pick='min' for grooves/thumb, 'max' for ridges; mesh vs analytic."""
        cand = [v for v in verts
                if abs(v[0] - xc) <= 3.0 and abs(wrap180(theta(v) - band)) <= 12.0]
        if not cand:
            return None
        r = {(v[1] ** 2 + v[2] ** 2) ** 0.5: v[0] for v in cand}
        key = min(r) if pick == "min" else max(r)
        return {"mesh_radius_mm": round(key, 2),
                "spec_radius_mm": round(radius(r[key], band), 2),
                "x_mm": round(r[key], 2)}

    scallops = []
    for i, c in enumerate(L["scallop_centers"]):
        p = probe(c, 270.0, "min")
        if p:
            present = bool(L["groove_extents"][i] > 0.0)
            p.update({"finger": FINGERS[i],
                      "present": present,
                      "depth_spec_mm": round(
                          L["scallop_depths"][i] if present else 0.0, 2)})
            scallops.append(p)
    thumb = probe(L["c_thumb"], K["K_THUMB_ANGLE"], "min")
    if thumb:
        thumb.update({"present": bool(L["thumb_arc_half"] > 0.0),
                      "depth_spec_mm": round(L["thumb_depth"], 2),
                      "angle_deg": K["K_THUMB_ANGLE"],
                      "tilt_deg": K["K_THUMB_TILT"],
                      "rear_angle_deg": K["K_THUMB_ANGLE"] - K["K_THUMB_TILT"],
                      "tip_angle_deg": K["K_THUMB_ANGLE"] + K["K_THUMB_TILT"]})
    max_r = max((v[1] ** 2 + v[2] ** 2) ** 0.5 for v in verts)
    return {
        "vertices": len(verts), "triangles": len(tris),
        "watertight": watertight, "volume_mm3": round(vol, 1),
        "handle_length_mm": round(L["total_length"], 2),
        "max_mesh_radius_mm": round(max_r, 2),
        "envelope_radius_mm": round(L["r_envelope"], 2),
        "envelope_margin_mm": round(L["r_envelope"] - max_r, 2),
        "envelope_ok": bool(max_r <= L["r_envelope"] + 1e-6),
        "handle_within_hand_length": bool(L["handle_within_hand"]),
        "scallop_probes": scallops, "thumb_probe": thumb,
        "axis": ("flat bar-stub face at x=0 (thumb/index side, v0.5); "
                 "rounded cap at the far end; thumb channel on top, rotated "
                 "about its midpoint (105 deg rear -> 90 deg mid -> 75 deg "
                 "tip, tip toward the palm flank)"),
    }


# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------
def write_stl(path, verts, tris):
    with open(path, "wb") as f:
        f.write(b"evertonians handle v0.5".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for (a, b, c) in tris:
            va, vb, vc = verts[a], verts[b], verts[c]
            u = ((vb[1] - va[1]) * (vc[2] - va[2])
                 - (vb[2] - va[2]) * (vc[1] - va[1]),
                 (vb[2] - va[2]) * (vc[0] - va[0])
                 - (vb[0] - va[0]) * (vc[2] - va[2]),
                 (vb[0] - va[0]) * (vc[1] - va[1])
                 - (vb[1] - va[1]) * (vc[0] - va[0]))
            ln = max((u[0] ** 2 + u[1] ** 2 + u[2] ** 2) ** 0.5, 1e-30)
            f.write(struct.pack("<12fH", u[0] / ln, u[1] / ln, u[2] / ln,
                                *va, *vb, *vc, 0))


def write_params(path, val, prov, L, stats):
    doc = {
        "generator": "grip_generator_v05.py (v0.5.5 missing/shortened-"
                      "finger support; geometry frozen at v0.5.3)",
        "inputs": dict(val, **{"_provenance": prov}),
        "input_wiring": WIRING,
        "constants": {k: v for k, v in K.items()},
        "derived_layout": {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in L.items()},
        "stats": stats,
    }
    with open(path, "w") as f:
        json.dump(doc, f, indent=2)


def write_svg(path, verts, L):
    """Compact 3-panel preview: side, top, and cross-sections."""
    xs = sorted(set(round(v[0], 2) for v in verts))
    side = [(x, max(z for (xx, y, z) in verts if abs(xx - x) < 0.05)) for x in xs]
    side_lo = [(x, min(z for (xx, y, z) in verts if abs(xx - x) < 0.05)) for x in xs]
    top = [(x, max(y for (xx, y, z) in verts if abs(xx - x) < 0.05)) for x in xs]
    W, H, m = 1600, 560, 30
    sx = (W - 2 * m) / L["total_length"]

    def pol(pts, sy, oy):
        pts = [(m + x * sx, oy - z * sy) for (x, z) in pts]
        return "M" + " L".join("%.1f,%.1f" % p for p in pts)

    panels = [
        (side, 170, "side view (thumb tilted about its midpoint, stub left)"),
        (top, 380, "top view (palm swell up, stub left)"),
    ]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">' % (W, H),
           '<rect width="%d" height="%d" fill="#fff"/>' % (W, H)]
    for (pts, oy, lbl) in panels:
        out.append('<path d="%s" fill="none" stroke="#888" stroke-width="1.4"/>'
                   % pol(pts, 4.0, oy))
        out.append('<text x="%d" y="%d" font-size="20">%s</text>'
                   % (m, oy + 60, lbl))
    out.append('<path d="%s" fill="none" stroke="#444" stroke-width="1.4"/>'
               % pol(side_lo, 4.0, 170))
    colors = ["#c33", "#393", "#33c", "#939"]
    for i, c in enumerate(L["scallop_centers"]):     # cross-sections at grooves
        ring = [(y, z) for (x, y, z) in verts if abs(x - c) < 0.05]
        pts = [(m + c * sx + y * 2.2, 380 - z * 2.2) for (y, z) in ring]
        out.append('<circle cx="%.1f" cy="380" r="3" fill="%s"/>'
                   % (m + c * sx, colors[i]))
        if len(pts) > 8:
            out.append('<path d="M%s" fill="none" stroke="%s" stroke-width="1.2"/>'
                       % (" L".join("%.1f,%.1f" % p for p in pts), colors[i]))
    out.append('<text x="%d" y="%d" font-size="18">'
               'colored sections: index/middle/ring/pinkie grooves</text>' % (m, 540))
    out.append("</svg>")
    with open(path, "w") as f:
        f.write("".join(out))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def generate(hand_path, outdir=".", palm_side="right", name=None):
    """Build the handle and write STL + params + preview; return stats."""
    val, prov = load_hand(hand_path)
    L = layout(val)
    verts, tris = build_mesh(val, L, palm_side)
    stats = mesh_stats(verts, tris, L, make_radius(val, L))
    name = name or os.path.splitext(os.path.basename(hand_path))[0]
    write_stl(os.path.join(outdir, name + ".stl"), verts, tris)
    write_params(os.path.join(outdir, name + "_params.json"), val, prov, L, stats)
    write_svg(os.path.join(outdir, name + "_preview.svg"), verts, L)
    stats["stl"] = name + ".stl"
    print(json.dumps(stats, indent=2))
    return stats


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Evertonians prybar handle generator (v0.5)")
    p.add_argument("hand", help="hand measurements JSON file")
    p.add_argument("-o", "--outdir", default=".", help="output directory")
    p.add_argument("--name", help="output file base name")
    p.add_argument("--palm-side", choices=("right", "left"), default="right",
                   help="which hand the handle is for")
    a = p.parse_args(argv)
    generate(a.hand, a.outdir, a.palm_side, a.name)


if __name__ == "__main__":
    main()
