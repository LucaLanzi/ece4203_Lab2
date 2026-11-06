#!/usr/bin/env python3
"""
random_optimize.py
==================
Placement optimizer for ECE4203 Lab 2.  Started as the provided example
(random placements, keep the best) and extended with better methods so they
can be compared against each other (results are documented in README.md):

  random   - the original example: generate random placements, keep the best
  greedy   - hill climbing with pairwise swaps of existing cell positions
             (only accepts moves that lower HPWL)
  sa_swap  - simulated annealing with pairwise swaps of existing positions
             (density is preserved automatically because the set of
             occupied positions never changes)
  sa_move  - simulated annealing with swaps AND free displacement moves.
             Displacements are restricted by (1) the grader's density rule,
             with an extra safety margin, and (2) a minimum spacing between
             cells so nothing overlaps or bunches up.

Usage:
    # defaults reproduce the submitted output.json (sa_move, ~2 minutes)
    python3 random_optimize.py initial_placement.JSON

    python3 random_optimize.py initial_placement.JSON --method random -n 1000
    python3 random_optimize.py initial_placement.JSON --method greedy --iters 2000000
    python3 random_optimize.py initial_placement.JSON --method sa_swap \
        --iters 2000000 --alpha 0.95 --temps 150 --no-adaptive-window
"""

import argparse, json, math, random, time


# ── I/O and HPWL ──────────────────────────────────────────────────────────────

def load(path):
    with open(path) as f:
        return json.load(f)


def save(data, placement, h, path):
    out = dict(data)
    out['placement'] = {c: [round(x, 4), round(y, 4)] for c, (x, y) in placement.items()}
    out['hpwl'] = round(h, 6)
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved {path}")


def net_hpwl(net, X, Y):
    xs = [X[c] for c in net]
    ys = [Y[c] for c in net]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


class Placer:
    """Holds the placement as index arrays and supports incremental HPWL."""

    def __init__(self, data):
        self.cells = data['cells']
        self.idx = {c: i for i, c in enumerate(self.cells)}
        self.gw, self.gh = data['grid']
        p = data['placement']
        self.X = [float(p[c][0]) for c in self.cells]
        self.Y = [float(p[c][1]) for c in self.cells]
        # nets as index lists (single-pin nets contribute nothing)
        self.nets = [[self.idx[c] for c in net if c in self.idx] for net in data['nets']]
        self.nets = [n for n in self.nets if len(n) >= 2]
        self.cell_nets = [[] for _ in self.cells]
        for ni, net in enumerate(self.nets):
            for c in net:
                self.cell_nets[c].append(ni)
        self.net_cost = [net_hpwl(n, self.X, self.Y) for n in self.nets]
        self.total = sum(self.net_cost)

    def affected(self, *cs):
        s = set()
        for c in cs:
            s.update(self.cell_nets[c])
        return s

    def try_move(self, moves):
        """moves: list of (cell, newx, newy). Applies them and returns
        (delta, undo_info). Call undo() to revert."""
        old = [(c, self.X[c], self.Y[c]) for c, _, _ in moves]
        for c, x, y in moves:
            self.X[c], self.Y[c] = x, y
        nets = self.affected(*[m[0] for m in moves])
        delta = 0.0
        new_costs = []
        for ni in nets:
            nc = net_hpwl(self.nets[ni], self.X, self.Y)
            new_costs.append((ni, nc))
            delta += nc - self.net_cost[ni]
        return delta, (old, new_costs)

    def commit(self, delta, info):
        for ni, nc in info[1]:
            self.net_cost[ni] = nc
        self.total += delta

    def undo(self, info):
        for c, x, y in info[0]:
            self.X[c], self.Y[c] = x, y

    def placement(self):
        return {c: (self.X[i], self.Y[i]) for i, c in enumerate(self.cells)}

    def exact_hpwl(self):
        return sum(net_hpwl(n, self.X, self.Y) for n in self.nets)


# ── Density bookkeeping (same binning rule as grade_placement.py) ────────────

class Density:
    def __init__(self, pl, tolerance=0.50, margin=0.05):
        n = len(pl.cells)
        self.bins = max(3, min(10, int(math.floor(math.sqrt(n / 32)))))
        ideal = n / self.bins ** 2
        tol = tolerance - margin          # stay safely inside the rule
        self.lo = math.ceil(ideal * (1 - tol))
        self.hi = math.floor(ideal * (1 + tol))
        self.gw, self.gh = pl.gw, pl.gh
        self.count = {}
        for i in range(len(pl.cells)):
            b = self.bin_of(pl.X[i], pl.Y[i])
            self.count[b] = self.count.get(b, 0) + 1

    def bin_of(self, x, y):
        col = min(int(x / self.gw * self.bins), self.bins - 1)
        row = min(int(y / self.gh * self.bins), self.bins - 1)
        return (row, col)

    def ok_move(self, b_from, b_to):
        if b_from == b_to:
            return True
        return self.count[b_from] - 1 >= self.lo and self.count.get(b_to, 0) + 1 <= self.hi

    def apply(self, b_from, b_to):
        self.count[b_from] -= 1
        self.count[b_to] = self.count.get(b_to, 0) + 1


class Spacing:
    """Spatial hash used to keep a minimum distance between cells."""

    def __init__(self, pl, dmin):
        self.d = dmin
        self.d2 = dmin * dmin
        self.grid = {}
        for i in range(len(pl.cells)):
            self.add(i, pl.X[i], pl.Y[i])

    def key(self, x, y):
        return (int(x / self.d), int(y / self.d))

    def add(self, i, x, y):
        self.grid.setdefault(self.key(x, y), set()).add(i)

    def remove(self, i, x, y):
        self.grid[self.key(x, y)].discard(i)

    def free(self, x, y, ignore=()):
        kx, ky = self.key(x, y)
        for gx in (kx - 1, kx, kx + 1):
            for gy in (ky - 1, ky, ky + 1):
                for j in self.grid.get((gx, gy), ()):
                    if j in ignore:
                        continue
                    # positions are looked up via the placer (set by caller)
                    jx, jy = self.pos[j]
                    if (jx - x) ** 2 + (jy - y) ** 2 < self.d2:
                        return False
        return True


# ── Optimization methods ──────────────────────────────────────────────────────

def run_random(pl, args, rng):
    best = pl.total
    best_xy = (pl.X[:], pl.Y[:])
    for t in range(args.trials):
        pl.X = [rng.uniform(0, pl.gw) for _ in pl.cells]
        pl.Y = [rng.uniform(0, pl.gh) for _ in pl.cells]
        h = pl.exact_hpwl()
        if h < best:
            best, best_xy = h, (pl.X[:], pl.Y[:])
            print(f"  trial {t+1}: new best {h:.2f}")
    pl.X, pl.Y = best_xy[0][:], best_xy[1][:]
    pl.net_cost = [net_hpwl(n, pl.X, pl.Y) for n in pl.nets]
    pl.total = sum(pl.net_cost)


def random_partner(pl, a, rng, window):
    """Pick a swap partner, optionally restricted to a window around a."""
    n = len(pl.cells)
    if window <= 0:
        return rng.randrange(n)
    # rejection-sample a partner inside the window (fall back to anyone)
    ax, ay = pl.X[a], pl.Y[a]
    for _ in range(20):
        b = rng.randrange(n)
        if abs(pl.X[b] - ax) <= window and abs(pl.Y[b] - ay) <= window:
            return b
    return rng.randrange(n)


def run_greedy(pl, args, rng):
    n = len(pl.cells)
    accepted = 0
    for it in range(args.iters):
        a = rng.randrange(n)
        b = random_partner(pl, a, rng, args.window)
        if a == b:
            continue
        delta, info = pl.try_move([(a, pl.X[b], pl.Y[b]), (b, pl.X[a], pl.Y[a])])
        if delta < 0:
            pl.commit(delta, info)
            accepted += 1
        else:
            pl.undo(info)
        if (it + 1) % args.report == 0:
            print(f"  iter {it+1:>9}: HPWL {pl.total:9.2f}  accepted {accepted}")


def run_sa(pl, args, rng, allow_moves):
    n = len(pl.cells)
    dens = Density(pl, margin=args.density_margin) if allow_moves else None
    space = None
    if allow_moves and args.min_spacing > 0:
        space = Spacing(pl, args.min_spacing)
        space.pos = {}
        for i in range(n):
            space.pos[i] = (pl.X[i], pl.Y[i])

    # Initial temperature: if t0 <= 0, estimate from average |delta| of
    # random swaps so ~80% of uphill moves are accepted at the start.
    T = args.t0
    if T <= 0:
        ds = []
        for _ in range(500):
            a, b = rng.randrange(n), rng.randrange(n)
            d, info = pl.try_move([(a, pl.X[b], pl.Y[b]), (b, pl.X[a], pl.Y[a])])
            pl.undo(info)
            ds.append(abs(d))
        T = (sum(ds) / len(ds)) / -math.log(0.8)
    print(f"  T0 = {T:.4f}, alpha = {args.alpha}, steps/temperature = {args.iters // args.temps}")

    steps_per_T = max(1, args.iters // args.temps)
    window = args.window if args.window > 0 else max(pl.gw, pl.gh)
    it = 0
    for k in range(args.temps):
        acc = 0
        for _ in range(steps_per_T):
            it += 1
            a = rng.randrange(n)
            if allow_moves and rng.random() < args.move_prob:
                # displacement move inside the window
                nx = min(max(pl.X[a] + rng.uniform(-window, window), 0.0), pl.gw)
                ny = min(max(pl.Y[a] + rng.uniform(-window, window), 0.0), pl.gh)
                bf, bt = dens.bin_of(pl.X[a], pl.Y[a]), dens.bin_of(nx, ny)
                if not dens.ok_move(bf, bt):
                    continue
                if space is not None and not space.free(nx, ny, ignore=(a,)):
                    continue
                ox, oy = pl.X[a], pl.Y[a]
                delta, info = pl.try_move([(a, nx, ny)])
                if delta <= 0 or rng.random() < math.exp(-delta / T):
                    pl.commit(delta, info)
                    dens.apply(bf, bt)
                    if space is not None:
                        space.remove(a, ox, oy)
                        space.add(a, nx, ny)
                        space.pos[a] = (nx, ny)
                    acc += 1
                else:
                    pl.undo(info)
            else:
                # swap move (density-neutral, spacing-neutral)
                b = random_partner(pl, a, rng, window)
                if a == b:
                    continue
                ax, ay, bx, by = pl.X[a], pl.Y[a], pl.X[b], pl.Y[b]
                delta, info = pl.try_move([(a, bx, by), (b, ax, ay)])
                if delta <= 0 or rng.random() < math.exp(-delta / T):
                    pl.commit(delta, info)
                    if space is not None:
                        space.remove(a, ax, ay); space.remove(b, bx, by)
                        space.add(a, bx, by); space.add(b, ax, ay)
                        space.pos[a] = (bx, by); space.pos[b] = (ax, ay)
                    acc += 1
                else:
                    pl.undo(info)
        if (k + 1) % max(1, args.temps // 20) == 0:
            print(f"  T={T:9.5f}  HPWL {pl.total:9.2f}  accept {acc/steps_per_T*100:5.1f}%  window {window:.2f}")
        T *= args.alpha
        # adaptive window (range limiting): shrink when acceptance is low
        if args.adaptive_window:
            rate = acc / steps_per_T
            window = min(max(pl.gw, pl.gh), max(args.min_window, window * (1 - 0.44 + rate)))

    # finish with a greedy pass at T=0 to polish
    if args.polish:
        print("  polishing (greedy swaps)...")
        old_window = args.window
        args.window = 1.0
        saved = args.iters
        args.iters = args.polish
        run_greedy(pl, args, rng)
        args.iters, args.window = saved, old_window


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("assignment")
    ap.add_argument("-o", "--output", default="output.json")
    ap.add_argument("--method", choices=["random", "greedy", "sa_swap", "sa_move"],
                    default="sa_move")
    ap.add_argument("-n", "--trials", type=int, default=1000,
                    help="random: number of random placements to try")
    ap.add_argument("--iters", type=int, default=10_000_000,
                    help="greedy/SA: total number of moves")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--t0", type=float, default=0.0,
                    help="initial temperature (0 = auto-estimate)")
    ap.add_argument("--alpha", type=float, default=0.97, help="geometric cooling factor")
    ap.add_argument("--temps", type=int, default=300, help="number of temperature steps")
    ap.add_argument("--window", type=float, default=0.0,
                    help="max move/swap distance (0 = whole chip)")
    ap.add_argument("--adaptive-window", action=argparse.BooleanOptionalAction,
                    default=True, help="shrink window as acceptance rate drops")
    ap.add_argument("--min-window", type=float, default=0.5)
    ap.add_argument("--move-prob", type=float, default=0.5,
                    help="sa_move: fraction of displacement vs swap moves")
    ap.add_argument("--min-spacing", type=float, default=0.2,
                    help="sa_move: minimum distance between any two cells")
    ap.add_argument("--density-margin", type=float, default=0.05,
                    help="sa_move: safety margin subtracted from the 50%% tolerance")
    ap.add_argument("--polish", type=int, default=1_000_000,
                    help="greedy swap iterations after annealing")
    ap.add_argument("--report", type=int, default=1_000_000)
    args = ap.parse_args()

    data = load(args.assignment)
    pl = Placer(data)
    rng = random.Random(args.seed)
    base = data.get('initial_hpwl') or pl.total
    print(f"{len(pl.cells)} cells, {len(pl.nets)} nets, baseline HPWL {base:.2f}")
    print(f"method={args.method} iters={args.iters} seed={args.seed}")

    t = time.time()
    if args.method == "random":
        run_random(pl, args, rng)
    elif args.method == "greedy":
        run_greedy(pl, args, rng)
    else:
        run_sa(pl, args, rng, allow_moves=(args.method == "sa_move"))
    dt = time.time() - t

    h = pl.exact_hpwl()
    assert abs(h - pl.total) < 1e-3, "incremental HPWL drifted"
    print(f"Final HPWL {h:.2f}  ({(base - h) / base * 100:+.2f}% vs baseline)  in {dt:.1f}s")
    save(data, pl.placement(), h, args.output)


if __name__ == "__main__":
    main()
