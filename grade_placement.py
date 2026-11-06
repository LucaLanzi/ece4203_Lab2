#!/usr/bin/env python3
"""
grade_placement.py
==================
Autograder for the ECE4203 placement assignment.

Loads the original assignment JSON and the student's submission, checks
validity, computes HPWL, checks density uniformity, and scores.

Usage:
    python grade_placement.py assignment.json student_placement.json

Exit codes:
    0  pass
    1  fail (invalid, density violation, or no improvement)
    2  usage error

"""

import argparse, json, math, sys
from typing import Dict, List, Tuple


# ── Helpers ───────────────────────────────────────────────────────────────────

def load(path):
    with open(path) as f:
        return json.load(f)


def compute_hpwl(nets, placement):
    total = 0.0
    for net in nets:
        xs = [placement[c][0] for c in net if c in placement]
        ys = [placement[c][1] for c in net if c in placement]
        if len(xs) < 2:
            continue
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return round(total, 6)


def check_density(placement, grid, bins=0, tolerance=0.50):
    """
    Returns a result dict with 'pass' bool and diagnostic fields.
    Bins are auto-scaled to give ~10 cells/bin.
    Skipped (pass=True, note set) when netlist is too small to measure.
    """
    gw, gh  = grid
    n_cells = len(placement)

    if bins <= 0:
        bins = max(3, min(10, int(math.floor(math.sqrt(n_cells / 32)))))

    ideal = n_cells / (bins * bins)

    if ideal < 2.0:
        return {
            'pass': True, 'bins': bins, 'tolerance': tolerance,
            'ideal': round(ideal, 3), 'max_deviation': 0.0,
            'violations': [], 'empty_bins': 0,
            'note': f'{n_cells} cells / {bins*bins} bins = {ideal:.1f} cells/bin — too sparse to check',
        }

    counts = [[0] * bins for _ in range(bins)]
    for cell, (x, y) in placement.items():
        col = min(int(x / gw * bins), bins - 1)
        row = min(int(y / gh * bins), bins - 1)
        counts[row][col] += 1

    violations = []
    max_dev = 0.0
    for row in range(bins):
        for col in range(bins):
            cnt = counts[row][col]
            dev = abs(cnt - ideal) / ideal
            max_dev = max(max_dev, dev)
            if dev > tolerance:
                violations.append((row, col, cnt, round(dev, 4)))

    all_counts = [counts[r][c] for r in range(bins) for c in range(bins)]
    return {
        'pass':          len(violations) == 0,
        'bins':          bins,
        'tolerance':     tolerance,
        'ideal':         round(ideal, 3),
        'max_deviation': round(max_dev, 4),
        'empty_bins':    sum(1 for c in all_counts if c == 0),
        'violations':    sorted(violations, key=lambda v: -v[3]),
    }


def validate(assignment, submission, grid_tolerance=1e-6):
    """Return list of error strings (empty = valid)."""
    errors   = []
    expected = set(assignment['cells'])
    gw, gh   = assignment['grid']
    placement = submission.get('placement', {})

    missing = expected - set(placement)
    extra   = set(placement) - expected
    if missing:
        errors.append(f"Missing cells: {sorted(missing)}")
    if extra:
        errors.append(f"Extra/unknown cells: {sorted(extra)}")

    out_of_bounds = []
    for cell, xy in placement.items():
        if cell not in expected:
            continue
        x, y = xy
        if not (-grid_tolerance <= x <= gw + grid_tolerance and
                -grid_tolerance <= y <= gh + grid_tolerance):
            out_of_bounds.append(f"{cell}=[{x:.2f},{y:.2f}]")
    if out_of_bounds:
        errors.append(f"Cells outside grid [{gw}x{gh}]: {out_of_bounds}")

    return errors


def score(improvement_pct, thresh_full, thresh_partial):
    if improvement_pct >= thresh_full:
        return "FULL",    1.0
    elif improvement_pct >= thresh_partial:
        frac = ((improvement_pct - thresh_partial) /
                (thresh_full    - thresh_partial))
        return "PARTIAL", round(0.5 + 0.5 * frac, 3)
    else:
        return "NONE",    0.0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Grade a placement submission")
    ap.add_argument("assignment",  help="Original assignment JSON")
    ap.add_argument("submission",  help="Student's output JSON")
    ap.add_argument("--full",      type=float, default=10.0, metavar="PCT",
                    help="Improvement %% for full marks (default 10)")
    ap.add_argument("--partial",   type=float, default=5.0,  metavar="PCT",
                    help="Improvement %% for partial credit (default 5)")
    ap.add_argument("--density-tolerance", type=float, default=0.50,
                    metavar="FRAC",
                    help="Max fractional deviation from ideal density (default 0.50)")
    ap.add_argument("--json",      action="store_true",
                    help="Emit machine-readable JSON result")
    args = ap.parse_args()

    try:
        assignment = load(args.assignment)
        submission = load(args.submission)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON — {e}", file=sys.stderr); sys.exit(1)

    # ── Structural validation ─────────────────────────────────────────────────
    errors = validate(assignment, submission)

    result = {
        "assignment": args.assignment,
        "submission": args.submission,
        "errors":     errors,
        "valid":      len(errors) == 0,
    }

    if errors:
        result.update({
            "grade": "INVALID", "score": 0.0,
            "density_pass": None,
            "improvement_pct": None,
            "baseline_hpwl": None,
            "submission_hpwl": None,
        })
    else:
        placement = submission['placement']
        nets      = assignment['nets']

        # ── Density check ─────────────────────────────────────────────────────
        density = check_density(placement, assignment['grid'],
                                tolerance=args.density_tolerance)
        density_skipped = bool(density.get('note'))
        density_pass    = density['pass']

        result['density'] = {
            'pass':          density_pass,
            'skipped':       density_skipped,
            'bins':          density['bins'],
            'tolerance':     density['tolerance'],
            'ideal':         density['ideal'],
            'max_deviation': density['max_deviation'],
            'empty_bins':    density['empty_bins'],
            'n_violations':  len(density['violations']),
            'note':          density.get('note', ''),
        }
        result['density_pass'] = density_pass

        # ── HPWL scoring ──────────────────────────────────────────────────────
        baseline = assignment.get('initial_hpwl') or \
                   compute_hpwl(nets, assignment['placement'])
        student  = compute_hpwl(nets, placement)
        imp_pct  = (baseline - student) / baseline * 100.0 if baseline else 0.0

        result['baseline_hpwl']   = round(baseline, 6)
        result['submission_hpwl'] = round(student,  6)
        result['improvement_pct'] = round(imp_pct,  4)

        # Density failure zeros the HPWL score
        if not density_pass and not density_skipped:
            grade_lbl, score_frac = "DENSITY_FAIL", 0.0
        else:
            grade_lbl, score_frac = score(imp_pct, args.full, args.partial)

        result['grade'] = grade_lbl
        result['score'] = score_frac

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        sep = "─" * 56
        print(sep)
        print(f"  Assignment : {result['assignment']}")
        print(f"  Submission : {result['submission']}")
        print(sep)

        if errors:
            print("  ✗  INVALID SUBMISSION")
            for e in errors:
                print(f"     • {e}")
        else:
            d = result['density']

            # Density section
            if d['skipped']:
                print(f"  Density    : SKIP  ({d['note']})")
            elif d['pass']:
                print(f"  Density    : PASS ✓  "
                      f"(max deviation {d['max_deviation']*100:.0f}%  "
                      f"tolerance {d['tolerance']*100:.0f}%  "
                      f"{d['bins']}×{d['bins']} bins)")
            else:
                print(f"  Density    : FAIL ✗  "
                      f"{d['n_violations']} bin(s) exceed "
                      f"{d['tolerance']*100:.0f}% tolerance  "
                      f"(max {d['max_deviation']*100:.0f}%  "
                      f"{d['empty_bins']} empty)")

            # HPWL section
            imp = result['improvement_pct']
            arrow = "▲" if imp > 0 else ("▼" if imp < 0 else "=")
            print(f"  Baseline   : {result['baseline_hpwl']:.4f}")
            print(f"  Submission : {result['submission_hpwl']:.4f}")
            print(f"  Improvement: {arrow} {abs(imp):.2f}%  "
                  f"({'better' if imp > 0 else 'worse'})")
            print(sep)

            g = result['grade']
            s = result['score']

            if g == "DENSITY_FAIL":
                print(f"  ✗  DENSITY FAIL — HPWL score zeroed")
                print(f"     Placement is too non-uniform to receive marks.")
            else:
                sym = "✓" if g == "FULL" else ("◑" if g == "PARTIAL" else "✗")
                print(f"  {sym}  {g} MARKS  ({s*100:.0f}% of HPWL component)")
                if g == "NONE" and imp <= 0:
                    print("     Submission did not improve over the random baseline.")
                elif g == "PARTIAL":
                    print(f"     Need ≥{args.full:.0f}% improvement for full marks "
                          f"(achieved {imp:.2f}%).")

        print(sep)

    sys.exit(0 if result['valid'] and result.get('score', 0) > 0 else 1)


if __name__ == "__main__":
    main()
