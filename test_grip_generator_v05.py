#!/usr/bin/env python3
"""Tests for grip_generator_v05.py -- compact suite (v0.5, v0.5.5).

Run:  python3 test_grip_generator_v05.py     (exit 0 = all green)
Checks the v0.5 contract: watertight, envelope, nub on the thumb side,
thumb channel ROTATED about its midpoint, tip toward the palm flank
(tilt, not shift; sign corrected from v0.5.2 per user), right-hand finger
row, feature depths realized, swell present, curl toward the stub, and
(if the published v0.4.4 STL is available) a vertex-by-vertex proof
that the sculpted BODY is unchanged except the re-cut thumb channel.
"""

import json
import math
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_generator_v05 as G

HAND = {
    "hand_length": 190, "hand_breadth": 85, "palm_length": 105,
    "grip_diameter_inside": 55,
    "finger_widths": [22, 23, 20, 18],
    "finger_lengths": [75, 83, 73, 62],
    "finger_thicknesses": [22, 20, 19, 15],
    "thumb_length": 69, "thumb_breadth": 25, "thumb_thickness": 22,
    "web_spaces": [10, 6, 8],
}
V044_STL = "/home/user/artifacts/evertonians_handle_v044.stl"

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                        (" - " + detail) if detail else ""))
    PASSED, FAILED = PASSED + ok, FAILED + (not ok)


def build(hand, **kw):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(hand, f)
        p = f.name
    return G.generate(p, **kw)


tmp = tempfile.mkdtemp()
with open(os.path.join(tmp, "h.json"), "w") as f:
    json.dump(HAND, f)
val, prov = G.load_hand(os.path.join(tmp, "h.json"))
L = G.layout(val)
stats = G.generate(os.path.join(tmp, "h.json"), outdir=tmp, name="t")
verts, tris = G.build_mesh(val, L)
r = G.make_radius(val, L)
r_no = G.make_radius(val, L, with_fingers=False)

print("== watertight (3 independent checks) ==")
edges = {}
for (a, b, c) in tris:
    for (u, v) in ((a, b), (b, c), (c, a)):
        e = (u, v) if u < v else (v, u)
        edges[e] = edges.get(e, 0) + 1
check("Euler characteristic == 2",
      len(verts) - len(edges) + len(tris) == 2)
check("every edge shared by exactly 2 faces",
      all(c == 2 for c in edges.values()))
vol = 0.0
for (a, b, c) in tris:
    va, vb, vc = verts[a], verts[b], verts[c]
    vol += (va[0]*(vb[1]*vc[2]-vb[2]*vc[1]) - va[1]*(vb[0]*vc[2]-vb[2]*vc[0])
            + va[2]*(vb[0]*vc[1]-vb[1]*vc[0])) / 6.0
check("positive signed volume", vol > 0.0, "%.1f mm3" % vol)
check("volume matches stats", abs(vol - stats["volume_mm3"]) < 1.0)

print("== envelope ==")
check("mesh inside envelope", stats["envelope_ok"])
check("margin positive (not clamped flat)", stats["envelope_margin_mm"] > 0.2,
      "margin %.2f mm" % stats["envelope_margin_mm"])

print("== v0.5: nub on the thumb side ==")
stub_r = L["r_stub"] * G.K["TAPER_REAR"]
ring0 = min((v[1]**2 + v[2]**2) ** 0.5 for v in verts if abs(v[0] - 1.5) < 0.01)
check("bar stub exists at x=0..12 (thumb end)", abs(ring0 - stub_r) < 0.1,
      "stub ring r=%.2f vs %.2f (B side)" % (ring0, stub_r))
check("thumb imprint on the stub half of the handle",
      L["c_thumb"] < L["total_length"] / 2.0,
      "thumb x=%.1f < %.1f" % (L["c_thumb"], L["total_length"] / 2.0))
cap_zone = [v for v in verts if v[0] > L["total_length"] - L["r_dome"] - 1.0]
check("cap end is a full-radius dome, not a step-down to the stub",
      max((v[1]**2 + v[2]**2) ** 0.5 for v in cap_zone) > 0.9 * L["r_core"])
check("handle fits the hand", stats["handle_within_hand_length"],
      "%.1f <= %d mm" % (L["total_length"], HAND["hand_length"]))

print("== thumb channel rotated about its midpoint, right-hand row ==")
def deepest_theta(xlo, xhi):
    zone = [v for v in verts if xlo <= v[0] <= xhi
            and 60 <= math.degrees(math.atan2(v[2], v[1])) % 360 <= 150]
    dv = min(zone, key=lambda v: (v[1]**2 + v[2]**2) ** 0.5)
    return math.degrees(math.atan2(dv[2], dv[1])) % 360
c_th, hl_th = L["c_thumb"], L["hl_thumb"]
th_rear = deepest_theta(c_th - 17.0, c_th - 13.0)
th_mid = deepest_theta(c_th - 2.0, c_th + 2.0)
th_tip = deepest_theta(c_th + 13.0, c_th + 17.0)
check("thumb dent rotates clockwise along the channel (mesh)",
      th_rear > th_mid > th_tip and th_rear - th_tip > 5.0,
      "rear %.1f, mid %.1f, tip %.1f deg" % (th_rear, th_mid, th_tip))
check("thumb channel midpoint stays on top (~90 deg)",
      abs(th_mid - G.K["K_THUMB_ANGLE"]) < 8.0, "mid %.1f deg" % th_mid)
lo, hi = G.K["K_THUMB_ANGLE"] - 12.0, G.K["K_THUMB_ANGLE"] + 12.0
# symmetric about the top, so the oval core cancels and only the cut differs
check("rear leans counterclockwise of top, tip leans clockwise (tilt, not shift)",
      r_no(c_th - 15.0, hi) < r_no(c_th - 15.0, lo)
      and r_no(c_th + 15.0, lo) < r_no(c_th + 15.0, hi),
      "r(%.0f, %.0f)=%.2f < r(%.0f, %.0f)=%.2f; mirrored at x=+15" %
      (c_th - 15, hi, r_no(c_th - 15.0, hi), c_th - 15, lo, r_no(c_th - 15.0, lo)))
check("right-hand row: index nearest the stub, pinkie nearest the cap",
      L["scallop_centers"][0] == min(L["scallop_centers"])
      and L["scallop_centers"][3] == max(L["scallop_centers"]))

print("== feature depths realized (mesh vs analytic) ==")
for p in stats["scallop_probes"]:
    check("groove %s depth realized" % p["finger"],
          abs(p["mesh_radius_mm"] - p["spec_radius_mm"]) < 0.45,
          "mesh %.2f vs spec %.2f" % (p["mesh_radius_mm"], p["spec_radius_mm"]))
tp = stats["thumb_probe"]
check("thumb channel depth realized",
      abs(tp["mesh_radius_mm"] - tp["spec_radius_mm"]) < 0.45,
      "mesh %.2f vs spec %.2f" % (tp["mesh_radius_mm"], tp["spec_radius_mm"]))

print("== palm swell present ==")
A = L["A"]
swell_zone = [v for v in verts if L["x_grip0"] + 8 <= v[0] <= L["x_swell_end"] - 8
              and abs(math.degrees(math.atan2(v[2], v[1])) % 360) < 3]
check("palm flank bulges ~swell amp above the core",
      max((v[1]**2 + v[2]**2)**0.5 for v in swell_zone)
      >= A * G.K["TAPER_REAR"] + 0.9 * L["swell_amp"])

print("== curl toward the stub (mesh-verified, dent domain) ==")
cm = L["scallop_centers"][1]
def deepest_x(lo, hi):
    best = None
    for v in verts:
        if not (cm - 14.0 <= v[0] <= cm + 14.0):
            continue
        th = math.degrees(math.atan2(v[2], v[1])) % 360.0
        if lo <= th <= hi:
            d = r_no(v[0], th) - (v[1]**2 + v[2]**2) ** 0.5
            if best is None or d > best[0]:
                best = (d, v[0])
    return best[1]
x_low, x_high = deepest_x(303.0, 313.0), deepest_x(203.0, 213.0)
check("grooves curl toward the thumb/stub side",
      x_high < x_low - 2.5,
      "deep x at high wrap %.1f < at low wrap %.1f" % (x_high, x_low))

print("== body unchanged vs published v0.4.4 STL ==")
if os.path.exists(V044_STL):
    with open(V044_STL, "rb") as f:
        data = f.read()
    n = struct.unpack("<I", data[80:84])[0]
    vs = set()
    for i in range(n):
        t = struct.unpack("<12fH", data[84+50*i:84+50*i+50])[3:12]
        for k in range(3):
            vs.add((t[3*k], t[3*k+1], t[3*k+2]))
    diffs = []
    for (x, y, z) in vs:
        if L["x_grip0"] - 0.01 <= x <= L["x_grip1"] + 0.01:
            th = math.degrees(math.atan2(z, y)) % 360.0
            # skip the thumb-channel zone: it was re-cut (tilted in place,
            # 75 -> 105 deg across its length, v0.5.2)
            if 24.0 <= x <= 76.0 and 30.0 <= th <= 170.0:
                continue
            diffs.append(abs((y*y + z*z) ** 0.5 - r(x, th)))
    diffs.sort()
    check("body == v0.4.4 body except the thumb channel (tilted in place)",
          len(diffs) > 0 and diffs[int(0.99 * len(diffs))] < 0.1,
          "%d verts, 99th pct %.4f mm" % (len(diffs), diffs[int(0.99*len(diffs))]))
else:
    print("[SKIP] v0.4.4 STL not found; body-match not checked")

print("== input wiring (every dimension is live) ==")
base = build(HAND, outdir=tmp, name="w0")
for k, v in {"hand_breadth": 90, "palm_length": 100, "grip_diameter_inside": 50,
             "thumb_length": 60, "thumb_breadth": 22,
             "finger_widths": [18, 19, 17, 15],
             "finger_lengths": [64, 70, 64, 52],
             "finger_thicknesses": [16, 15, 14, 12],
             "web_spaces": [7, 5, 6]}.items():
    st = build(dict(HAND, **{k: v}), outdir=tmp, name="w1")
    check("input '%s' changes geometry" % k,
          abs(st["volume_mm3"] - base["volume_mm3"]) > 0.5)
st = build(dict(HAND, hand_length=170), outdir=tmp, name="hl")
check("hand_length acts as the handle-length bound",
      st["handle_within_hand_length"] is False, "%.1f > 170" % L["total_length"])

print("== determinism + params ==")
s1 = build(HAND, outdir=tmp, name="d1")
check("same inputs -> same mesh",
      s1["triangles"] == stats["triangles"] and s1["volume_mm3"] == stats["volume_mm3"])
with open(os.path.join(tmp, "t_params.json")) as f:
    pj = json.load(f)
check("params JSON embeds the inputs",
      all(abs(pj["inputs"][k] - HAND[k]) < 1e-9 for k in
          ("hand_length", "hand_breadth", "grip_diameter_inside")))

print("== v0.5.5: frozen master numbers ==")
check("master triangle count is 61760", stats["triangles"] == 61760,
      "%d" % stats["triangles"])
check("master handle length is 171.03 mm",
      stats["handle_length_mm"] == 171.03, "%.2f" % stats["handle_length_mm"])
check("master volume is 201039.2 mm3",
      abs(stats["volume_mm3"] - 201039.2) < 0.05,
      "%.1f" % stats["volume_mm3"])

print("== v0.5.5: missing / shortened fingers ==")
def build_hand(hand, name):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(hand, f)
        path = f.name
    return G.generate(path, outdir=tmp, name=name)

def expect_error(hand, needle):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(hand, f)
        path = f.name
    try:
        G.generate(path, outdir=tmp, name="err")
    except ValueError as e:
        check("rejects %s" % needle, needle in str(e), str(e))
        return
    check("rejects %s" % needle, False, "no error raised")

MISSING_MIDDLE = dict(HAND, finger_widths=[22, None, 20, 18],
                     finger_lengths=[75, None, 73, 62],
                     finger_thicknesses=[22, None, 19, 15],
                     web_spaces=[10, None, 8])
s_mm = build_hand(MISSING_MIDDLE, "mm")
check("missing middle finger: watertight", s_mm["watertight"])
mid = [p for p in s_mm["scallop_probes"] if p["finger"] == "middle"]
check("missing middle finger: no groove spec depth",
      mid and mid[0]["present"] is False and mid[0]["depth_spec_mm"] == 0.0)
check("missing middle finger: volume differs from master",
      abs(s_mm["volume_mm3"] - stats["volume_mm3"]) > 1.0)
p_mm = os.path.join(tmp, "mm.json")
with open(p_mm, "w") as f:
    json.dump(MISSING_MIDDLE, f)
val_mm, prov_mm = G.load_hand(p_mm)
check("missing middle finger: width filled from measured mean",
      val_mm["finger_widths"][1] == (22 + 20 + 18) / 3.0)
check("missing middle finger: length zeroed",
      val_mm["finger_lengths"][1] == 0.0)
check("provenance records the v0.5.5 fills",
      prov_mm.get("v055_fills", {}).get("finger_lengths[1]")
      == "no groove (finger not present)")

NUB_INDEX = dict(HAND, finger_widths=[13, 23, 20, 18],
                finger_lengths=[12, 83, 73, 62],
                finger_thicknesses=[12, 20, 19, 15])
s_nub = build_hand(NUB_INDEX, "nub")
idx = [p for p in s_nub["scallop_probes"] if p["finger"] == "index"]
check("short nub index finger: watertight", s_nub["watertight"])
check("short nub index finger: groove still cut",
      idx and idx[0]["present"] is True and idx[0]["depth_spec_mm"] > 0.0)
check("short nub index finger: handle shorter than master",
      s_nub["handle_length_mm"] < stats["handle_length_mm"])

MISSING_THUMB = dict(HAND, thumb_length=None, thumb_breadth=None,
                     thumb_thickness=None)
s_mt = build_hand(MISSING_THUMB, "mt")
check("missing thumb: watertight", s_mt["watertight"])
tp_mt = s_mt.get("thumb_probe")
check("missing thumb: channel omitted",
      tp_mt is None or (tp_mt["present"] is False
                        and tp_mt["depth_spec_mm"] == 0.0))
check("missing thumb: handle shorter than master",
      s_mt["handle_length_mm"] < stats["handle_length_mm"])

NULL_WEBS = dict(HAND, web_spaces=[None, None, None])
s_nw = build_hand(NULL_WEBS, "nw")
check("all-null web gaps: build watertight with typical fill",
      s_nw["watertight"])

expect_error(dict(HAND, finger_lengths=[None, None, None, None]),
             "at least one")
expect_error(dict(HAND, finger_widths=[None, None, None, None]),
             "at least one")
expect_error(dict(HAND, finger_thicknesses=[None, None, None, None]),
             "at least one")
expect_error(dict(HAND, thumb_length=69, thumb_breadth=None),
             "thumb_breadth")
expect_error(dict(HAND, finger_lengths=[4, 83, 73, 62]),
             "outside")
expect_error(dict(HAND, thumb_length=5), "outside")

print()
if FAILED:
    print("FAILED: %d checks" % FAILED)
    sys.exit(1)
print("ALL CHECKS PASSED (%d)" % PASSED)
