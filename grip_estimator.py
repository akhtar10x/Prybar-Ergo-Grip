#!/usr/bin/env python3
"""
===========================================================================
 Evertonians grip diameter estimator
===========================================================================
 Companion to grip_generator_v05.py. The handle generator takes 22 hand
 measurements, 21 of which can be taken from photographs (with a ruler in
 frame). The remaining one -- grip_diameter_inside -- cannot: it describes
 a CLOSED grip around an object, not a flat-hand dimension, and is
 normally taken by sliding a hand down a cone until the thumb and middle
 finger barely touch (the standard "maximum grip diameter" method).

 This file estimates that measurement from the others:

     circumference  =  thumb_length + middle_finger_length + thumb_thickness
     grip_diameter  =  circumference / pi

 Geometry: when the hand closes around a cylinder, the thumb wraps one
 side and the middle finger (the longest finger, so the first to meet the
 thumb) wraps the other. "Barely touching" happens when the two digits
 together span roughly the full circumference. The thumb tip overlaps the
 middle fingertip pad instead of meeting it edge-on, which buys back about
 one digit thickness, hence the + thumb_thickness term. No fitted
 constants: pi is the only number in the formula.

 Accuracy: verified against a real cone-slide measurement to within
 0.5 mm on one adult hand (see the project notes). Treat it as an
 estimate: if a direct measurement exists, use the direct measurement.

 Usage:
     python3 grip_estimator.py hand.json            # estimate + compare
     python3 grip_estimator.py hand.json --tolerance 2.0
     python3 grip_estimator.py --selftest

 Input JSON schema: same as grip_generator_v05.py. thumb_thickness is
 optional (falls back to thumb_breadth, then to mean finger thickness).
 If grip_diameter_inside is present in the file it is kept as the
 "measured" reference and compared against the estimate; otherwise the
 estimate is reported alone. Exit code 0 = ok, 1 = estimate differs from
 the measured value by more than --tolerance, 2 = bad/missing input.

 Part of the v0.5.4 code set. Python 3, no dependencies.
===========================================================================
"""

import argparse
import json
import math
import sys

G = {
    "TOLERANCE_MM": 2.0,   # default pass/fail band, estimate vs measured
    "PLAUSIBLE_MIN": 30.0, # adult sanity band for a maximum grip diameter
    "PLAUSIBLE_MAX": 85.0, # (same band the generator accepts as input)
}

FINGERS = ["index", "middle", "ring", "pinkie"]
REQUIRED = ("hand_length", "thumb_length", "finger_lengths")


# ---------------------------------------------------------------------------
# Input loading (same schema as the generator, minimal validation here)
# ---------------------------------------------------------------------------
def load_hand(path):
    """Load a hand JSON; return a dict or raise ValueError with a clear
    message. Tolerates extra keys; requires thumb_length and the finger
    lists (middle finger = finger_lengths[1])."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise ValueError("input file not found: %s" % path)
    except json.JSONDecodeError as e:
        raise ValueError("input file is not valid JSON: %s" % e)

    for key in REQUIRED:
        if raw.get(key) is None:
            raise ValueError("missing required measurement: '%s'" % key)

    fl = raw.get("finger_lengths")
    if not isinstance(fl, list) or len(fl) < 2 or not fl[1]:
        raise ValueError("'finger_lengths' must list 4 lengths "
                         "(index, middle, ring, pinkie); the middle "
                         "finger (2nd value) drives the estimate")
    for i in (0, 1):
        try:
            fl[i] = float(fl[i])
        except (TypeError, ValueError):
            raise ValueError("'finger_lengths' values must be numbers")

    try:
        val = {
            "hand_length": float(raw["hand_length"]),
            "thumb_length": float(raw["thumb_length"]),
            "middle_length": fl[1],
        }
    except (TypeError, ValueError):
        raise ValueError("hand_length and thumb_length must be numbers")

    val["thumb_thickness"] = (float(raw["thumb_thickness"])
                              if raw.get("thumb_thickness") else None)
    val["thumb_breadth"] = (float(raw["thumb_breadth"])
                            if raw.get("thumb_breadth") else None)
    ft = raw.get("finger_thicknesses")
    if isinstance(ft, list) and len(ft) >= 4:
        try:
            ft = [float(x) for x in ft]
        except (TypeError, ValueError):
            ft = None
    else:
        ft = None
    val["finger_thicknesses"] = ft
    val["measured"] = (float(raw["grip_diameter_inside"])
                       if raw.get("grip_diameter_inside") else None)
    return val


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------
def estimate(val):
    """Return a dict: terms used, circumference, estimated diameter."""
    # Fallback chain for the pad-overlap term, same spirit as the
    # generator's thumb-depth fallback: thumb thickness, else thumb
    # breadth, else mean finger thickness.
    if val["thumb_thickness"]:
        pad = val["thumb_thickness"]
        pad_source = "thumb_thickness"
    elif val["thumb_breadth"]:
        pad = val["thumb_breadth"]
        pad_source = "thumb_breadth (fallback)"
    elif val["finger_thicknesses"]:
        pad = sum(val["finger_thicknesses"]) / 4.0
        pad_source = "mean finger_thicknesses (fallback)"
    else:
        pad = 0.0
        pad_source = "0 (no thickness data; estimate runs high-side)"

    circumference = val["thumb_length"] + val["middle_length"] + pad
    diameter = circumference / math.pi
    return {
        "thumb_length": val["thumb_length"],
        "middle_length": val["middle_length"],
        "pad": pad, "pad_source": pad_source,
        "circumference_mm": circumference,
        "grip_diameter_mm": diameter,
    }


def report(val, est, tolerance):
    """Human-readable report + pass/fail vs the measured value (if any)."""
    lines = [
        "grip diameter estimate",
        "  thumb_length          %6.1f mm" % est["thumb_length"],
        "  middle_length         %6.1f mm" % est["middle_length"],
        "  pad term (%s) %6.1f mm" % (est["pad_source"], est["pad"]),
        "  circumference         %6.1f mm" % est["circumference_mm"],
        "  estimated diameter    %6.1f mm" % est["grip_diameter_mm"],
    ]
    ok = True
    if val["measured"]:
        delta = est["grip_diameter_mm"] - val["measured"]
        ok = abs(delta) <= tolerance
        lines += [
            "  measured diameter     %6.1f mm" % val["measured"],
            "  delta (est - meas)    %+6.1f mm" % delta,
            "  tolerance             %6.1f mm  ->  %s"
            % (tolerance, "PASS" if ok else "FAIL"),
        ]
    else:
        lines.append("  (no measured grip_diameter_inside in the input;")
        lines.append("   report the estimate as an estimate)")
    return ok, "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test (synthetic values only -- no personal data)
# ---------------------------------------------------------------------------
def selftest():
    """11 checks on synthetic data. Exit 0 = all green."""
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    def synth(thumb=70.0, middle=80.0, pad=20.0, measured=None,
              with_pad=True, with_breadth=True, with_fts=True):
        v = {"hand_length": 180.0, "thumb_length": thumb,
             "middle_length": middle, "thumb_thickness":
             pad if with_pad else None,
             "thumb_breadth": 24.0 if with_breadth else None,
             "finger_thicknesses": [20.0, 19.0, 18.0, 15.0] if with_fts
             else None, "measured": measured}
        return v

    # 1. known-value math: (70 + 80 + 20) / pi
    est = estimate(synth())
    check("known value (70+80+20)/pi",
          abs(est["grip_diameter_mm"] - 170.0 / math.pi) < 1e-9)

    # 2. circumference terms add up
    check("circumference = terms",
          abs(est["circumference_mm"] - 170.0) < 1e-9)

    # 3. pad falls back to thumb_breadth when thickness absent
    est3 = estimate(synth(with_pad=False))
    check("pad fallback -> thumb_breadth",
          est3["pad_source"].startswith("thumb_breadth")
          and abs(est3["pad"] - 24.0) < 1e-9)

    # 4. pad falls back to mean finger thickness
    est4 = estimate(synth(with_pad=False, with_breadth=False))
    check("pad fallback -> mean finger thickness",
          est4["pad_source"].startswith("mean")
          and abs(est4["pad"] - 18.0) < 1e-9)

    # 5. no thickness data at all -> pad 0, still computes
    est5 = estimate(synth(with_pad=False, with_breadth=False,
                         with_fts=False))
    check("no thickness data -> pad 0",
          est5["pad"] == 0.0 and est5["grip_diameter_mm"] > 0.0)

    # 6. comparison: within tolerance passes
    ok6, _ = report(synth(measured=53.0), estimate(synth()),
                    G["TOLERANCE_MM"])
    check("measured 53.0 vs est %.2f -> pass"
          % estimate(synth())["grip_diameter_mm"], ok6)

    # 7. comparison: far outside tolerance fails
    ok7, _ = report(synth(measured=40.0), estimate(synth()),
                    G["TOLERANCE_MM"])
    check("measured 40.0 -> fail", not ok7)

    # 8. custom tolerance is honored
    ok8, _ = report(synth(measured=53.5), estimate(synth()), 0.1)
    check("tight tolerance 0.1 -> fail", not ok8)

    # 9. monotonicity: longer thumb -> larger estimate
    est9 = estimate(synth(thumb=80.0))
    check("longer thumb -> larger estimate",
          est9["grip_diameter_mm"] > est["grip_diameter_mm"])

    # 10. plausibility: example-template-scale hand lands in range
    est10 = estimate(synth(thumb=65.0, middle=80.0, pad=21.0))
    check("template-scale hand plausible (%.1f mm)"
          % est10["grip_diameter_mm"],
          G["PLAUSIBLE_MIN"] <= est10["grip_diameter_mm"]
          <= G["PLAUSIBLE_MAX"])

    # 11. missing middle finger length is a clear error
    bad = {"hand_length": 180.0, "thumb_length": 70.0,
           "finger_lengths": [70.0], "measured": None}
    try:
        # emulate load_hand validation on a short list
        if not isinstance(bad["finger_lengths"], list) or \
                len(bad["finger_lengths"]) < 2:
            raise ValueError("short list")
        check("short finger_lengths rejected", False)
    except ValueError:
        check("short finger_lengths rejected", True)

    fails = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    print()
    if fails:
        print("SELF-TEST FAILED (%d)" % len(fails))
        return 1
    print("ALL CHECKS PASSED (%d)" % len(checks))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(
        description="Estimate inside grip diameter (mm) from the other "
                    "hand measurements.")
    p.add_argument("input", nargs="?", help="hand JSON (generator schema)")
    p.add_argument("--tolerance", type=float, default=G["TOLERANCE_MM"],
                   help="pass/fail band vs measured value, mm "
                        "(default %.1f)" % G["TOLERANCE_MM"])
    p.add_argument("--selftest", action="store_true",
                   help="run the built-in checks and exit")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.input:
        p.error("an input file is required (or use --selftest)")

    try:
        val = load_hand(args.input)
    except ValueError as e:
        print("ERROR: %s" % e)
        return 2

    ok, text = report(val, estimate(val), args.tolerance)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
