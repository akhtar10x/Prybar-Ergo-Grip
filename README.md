# Evertonians Ergonomic Handle Generator

Parametric Python generator for the Phase 2 prybar handle. It takes 22 hand
measurements (mm) and produces a printable STL handle. No dependencies:
Python 3 only. Build v0.5.4 (October 2026).

## What it makes

A single-piece screwdriver-style handle:

- bar stub with a flat face at x=0 + 10mm blend (the prybar slots in here)
- rounded dome cap at the pinkie end
- four finger grooves wrapping the underside (index nearest the stub,
  ridges between fingers, fingertip curl toward the stub)
- palm swell on the +Y flank
- thumb channel on top, rotated 15 degrees about its own midpoint
  (rear 105 deg, mid 90 deg, tip 75 deg)
- the generator prints a stats JSON and enforces a never-exceed envelope

## Files

| File | Purpose |
| --- | --- |
| `grip_generator_v05.py` | The generator. All tuning constants live in the `K` dict. |
| `test_grip_generator_v05.py` | 34 automated checks (geometry, wiring, determinism). |
| `grip_estimator.py` | Estimates the grip diameter from the other measurements (11 built-in checks). |
| `hand_template.json` | Example inputs -- copy it and replace the values. |

## How to run

```
python3 grip_generator_v05.py hand_template.json -o . --name my_handle
```

Outputs:

- `my_handle.stl` -- binary STL, ready to slice
- `my_handle_params.json` -- inputs, constants, layout and stats; keep it
  next to the STL
- `my_handle_preview.svg` -- side and top views plus groove cross-sections

Use `--palm-side left` to y-mirror the handle for left hands.

The grip diameter cannot be photographed (it is a closed grip around an
object), so if no cone measurement exists, estimate it:

```
python3 grip_estimator.py hand.json
```

The estimator uses `grip_diameter = (thumb_length + middle_finger_length
+ thumb_thickness) / pi` -- when the hand closes around a cylinder, the
thumb and middle finger together span about one full circumference, and
the thumb tip overlapping the fingertip pad buys back one digit
thickness. Run `python3 grip_estimator.py --selftest` for its checks. If
`grip_diameter_inside` is already in the JSON, the estimator compares the
estimate against it and flags a difference larger than 2 mm.

## The 22 measurements

Hand and grip (4):

- `hand_length` -- wrist crease to longest fingertip; bounds handle length
- `hand_breadth` -- across the hand (e.g. at the thumb); palm swell height
- `palm_length` -- wrist crease to middle-finger base; swell extent
- `grip_diameter_inside` -- inside a clenched grip (e.g. sliding down a
  cone until thumb and middle finger barely touch); core diameter. This
  one cannot be taken from photographs -- use the cone method, or
  estimate it with `grip_estimator.py`

Thumb (3):

- `thumb_length` -- thumb channel length
- `thumb_breadth` -- thumb channel width
- `thumb_thickness` -- thumb channel depth

Per finger, 4 values each, index first, pinkie last (12):

- `finger_widths` -- groove size, spacing and positions
- `finger_lengths` -- groove wrap and fingertip curl
- `finger_thicknesses` -- groove depths

Web spaces (3):

- `web_spaces` -- gaps between adjacent fingers: index-middle, middle-ring,
  ring-pinkie

Optional:

- `palm_depth` -- unused in v0.5, kept for compatibility

In the input JSON the per-finger values are grouped into three lists of
four, so the 22 numbers sit in 11 named fields. Out-of-range values are
rejected with a clear error.

### Missing or shortened fingers (v0.5.5)

Hands differ. The generator accepts `null` entries for digits that are
not there, and small sizes for digits that are:

- `finger_lengths[i] = null` -- that finger is not present: the handle
  is built without its groove and without the ridges beside it. The row
  spacing is filled from the fingers that are present.
- `thumb_length = null` -- no thumb channel. (`thumb_breadth` may then
  be `null` too; a present thumb still requires `thumb_breadth`.)
- `null` entries in `finger_widths`, `finger_thicknesses` and
  `web_spaces` mean "not measured": they are filled from the mean of
  the measured values and recorded in the params JSON under
  `_provenance.v055_fills`.
- At least one finger must be present. Ranges accept short fingers:
  widths 5-30, lengths 5-115, thicknesses 4-30, thumb length 8-105,
  thumb breadth 8-36 mm.
- A fully intact hand rebuilds byte-identically to v0.5.4: every new
  code path is a no-op for present, in-range measurements.

`grip_estimator.py` follows the same contract: a missing middle finger
is replaced by the longest present finger; a missing thumb makes the
grip diameter impossible to estimate (a direct measurement is required).

## Tests

```
python3 test_grip_generator_v05.py
```

56 checks: watertight mesh (3 scales), envelope fit, stub/dome layout,
thumb-channel rotation, groove depths, palm swell, fingertip curl, input
wiring, determinism, plus the v0.5.5 set: frozen master numbers, missing
middle finger, shortened (nub) index finger, missing thumb, null web
fills and the new error cases. One check compares the body against a
reference STL and skips politely if that file is absent.

## Version notes

- v0.5.5 -- missing / shortened finger support (null entries, nub-friendly
  ranges); intact hands rebuild byte-identically to v0.5.4
- v0.5.4 -- cleanup only; geometry frozen, byte-identical to v0.5.3
- v0.5.3 -- tilt direction corrected (tip toward the palm flank)
- v0.5.2 -- rotate the thumb channel, not shift it
- v0.5.0 -- nub moved to the thumb side; simplified rewrite of the v0.4.4 body
