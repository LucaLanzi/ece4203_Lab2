#!/usr/bin/env python3
"""
random_optimize.py
==================
The simplest possible placement optimizer: repeatedly generate a completely
random placement and keep the best one found.

Usage:
    python random_optimize.py assignment.json [-o output.json] [-n 1000]
"""

import json, random, argparse


def load(path):
    with open(path) as f:
        return json.load(f)

def save(data, path):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {path}")

def hpwl(nets, placement):
    total = 0.0
    for net in nets:
        xs = [placement[c][0] for c in net if c in placement]
        ys = [placement[c][1] for c in net if c in placement]
        if len(xs) < 2:
            continue
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total

def random_placement(cells, gw, gh, rng):
    return {c: [round(rng.uniform(0, gw), 4),
                round(rng.uniform(0, gh), 4)] for c in cells}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("assignment")
    ap.add_argument("-o", "--output",  default=None)
    ap.add_argument("-n", "--trials",  type=int, default=1000,
                    help="Number of random placements to try (default 1000)")
    ap.add_argument("--seed",          type=int, default=None)
    args = ap.parse_args()

    data  = load(args.assignment)
    cells = data['cells']
    nets  = data['nets']
    gw, gh = data['grid']
    baseline = data.get('initial_hpwl') or hpwl(nets, data['placement'])

    print(f"Loaded: {len(cells)} cells, {len(nets)} nets")
    print(f"Baseline HPWL : {baseline:.4f}")
    print(f"Trying {args.trials} random placements...")

    rng = random.Random(args.seed)
    best_placement = None
    best_hpwl = float('inf')

    for i in range(args.trials):
        p = random_placement(cells, gw, gh, rng)
        h = hpwl(nets, p)
        if h < best_hpwl:
            best_hpwl = h
            best_placement = p
            print(f"  Trial {i+1:>6}: new best HPWL = {best_hpwl:.4f}")

    improvement = (baseline - best_hpwl) / baseline * 100
    print(f"Best HPWL     : {best_hpwl:.4f}  ({improvement:+.2f}% vs baseline)")

    out = dict(data)
    out['placement'] = best_placement
    out['hpwl'] = round(best_hpwl, 6)
    save(out, args.output or args.assignment.replace('.json', '_random.json'))


if __name__ == "__main__":
    main()
