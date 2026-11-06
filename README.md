There are four files under the Lab 2 directory in Canvas:

1) initial_placement.json = this is the file that contains the list of cells, nets, and initial placements of the cells.  This is your starting point for placement - it has a total HPWL of 4362.  The square region size is 10.0 x 10.0 - don't change this.

2) placement_utils.py = this is a python program that contains useful functions you can use in your optimizer.  See the comments in the file.  Also, you can run it directly with an input json file to see the placement, HPWL values, and density check.

3) grade_placement.py = this is a python program that you can use to check your results to see the improvement and make sure you didn't violate the density rule (see below).

4) random_optimize.py = this is a python program that tries to optimize the HPWL by simply doing many random placements, and keeping the best ones.  It is a really slow and bad optimizer - like buying a lottery ticket and hoping you hit the jackpot.  You can do much better!

One important rule - the cells need to be roughly evenly distributed over the (10.0 x 10.0) square region, i.e. the density of cells can't change drastically across the placement.  This is because the cells can't all be bunched up on top of each other (that would give a very low HPWL, but would not be a useful result, since the cells can't overlap in the final design).  If your optimizer only swaps positions from the initial placement, you will not violate the density - but if you move the positions, you will need to make sure you don't violate the density requirement.  The grade_placement.py tool will check the density for you.

Your optimizer should take the initial_placement.json file as input, and produce a new output.json file with a modified placement that gets a better HPWL.  Look at (and run) the random_optimize.py program as an example.

I encourage you to use AI to work on this; try different optimization approaches and see how much better you can get.

You will need to install the "tk" python package to run the visualizer (might be called "python3-tk"), as well as "math" and "json" which should already be part of the python distribution.  AI can also help you if you are unsure how to set up your python environment.

---

# Solution

**Result:** `output.json` has **HPWL = 295.57**, down from 4362.05, a **93.22 % improvement**. The density check passes (max bin deviation 44 % against a 50 % tolerance). `grade_placement.py` gives it full marks.

How to reproduce it (the default settings generate the submitted `output.json` in about 2 minutes):

```
python3 random_optimize.py initial_placement.JSON          # writes output.json
python3 grade_placement.py initial_placement.JSON output.json
```

The provided `random_optimize.py` was extended with three more methods, selected with `--method`. The original random method is still available as `--method random -n <trials>`. Only the Python standard library is used.

## The problem

* 689 cells and 504 nets: 263 two-pin, 137 three-pin, 87 four-pin, 16 with 5–8 pins, and one 194-pin net (likely a clock or reset).
* The grader splits the 10 × 10 region into 4 × 4 density bins. The ideal count is 43.06 cells per bin, and each bin must stay within ±50 %, so every bin needs **22–64 cells**.
* HPWL is the sum over all nets of (max x − min x) + (max y − min y).

## Optimization methods

All methods use **incremental HPWL**. When cells move, only the nets connected to them are recomputed, instead of the whole netlist. The original example re-evaluates every net on every trial; this runs about 85 k moves per second in plain Python. At the end, the HPWL is recomputed from scratch and checked against the incremental total.

| Method | How it works |
| --- | --- |
| `random` | The original example. Generates completely random placements and keeps the best one. |
| `greedy` | Hill climbing. Picks two cells at random and swaps their positions. The swap is kept **only if HPWL decreases**. |
| `sa_swap` | Simulated annealing with swaps. A swap that makes HPWL worse by Δ is still accepted with probability e^(−Δ/T). The temperature cools geometrically (T ← α·T). |
| `sa_move` | Simulated annealing with swaps **and** displacement moves (cells move to new coordinates). |

**How each method satisfies the density rule:**

* *Swaps* only exchange existing positions. The set of occupied positions never changes, so density cannot change.
* *Displacement moves* (`sa_move`) are checked before they are evaluated:
  * *Density:* the optimizer tracks the 4 × 4 bin counts using the grader's own binning rule. A move is rejected if it would push a bin outside 24–62 cells. That range is the 22–64 limit with a 5 % safety margin.
  * *Spacing:* a spatial hash rejects any position closer than `--min-spacing` (0.2) to another cell, so cells cannot overlap or bunch up.

## Parameters

| Flag | Meaning |
| --- | --- |
| `-n` | Number of random placements (`random` only) |
| `--iters` | Total number of moves for greedy and SA |
| `--t0` | Starting temperature. `0` means auto: T0 is set so about 80 % of uphill swaps are accepted at the start (gives T0 ≈ 22.5). |
| `--alpha`, `--temps` | Cooling factor and number of temperature steps |
| `--window` | Maximum swap/move distance. `0` means the whole chip. |
| `--adaptive-window` | Range limiting: the window shrinks as the acceptance rate drops, down to `--min-window` 0.5. Turn it off with `--no-adaptive-window`. |
| `--polish` | Number of greedy swaps (window 1.0) run after annealing finishes |
| `--min-spacing`, `--density-margin` | Legality constraints for `sa_move` |
| `--seed` | Random seed (default 1) |

## Results

Every run below passed `grade_placement.py`. Each command starts with `python3 random_optimize.py initial_placement.JSON`.

| # | Method | Parameters | HPWL | Improvement | Max density dev. | Time |
|---|--------|-----------|-----:|------------:|-----:|-----:|
| 1 | random | `--method random -n 200` | 4159.24 | 4.65 % | 32 % | 0.1 s |
| 2 | greedy | `--method greedy --iters 200000` | 821.64 | 81.16 % | 42 % | 2 s |
| 3 | greedy | `--method greedy --iters 2000000` | 653.47 | 85.02 % | 42 % | 20 s |
| 4 | greedy | `--method greedy --iters 2000000 --window 1.0` | 865.19 | 80.17 % | 42 % | 27 s |
| 5 | SA swap | `--method sa_swap --iters 2000000 --alpha 0.95 --temps 150 --t0 1.0 --no-adaptive-window --polish 0` (too cold) | 593.67 | 86.39 % | 42 % | 24 s |
| 6 | SA swap | `--method sa_swap --iters 2000000 --alpha 0.90 --temps 60 --no-adaptive-window --polish 0` | 500.61 | 88.52 % | 42 % | 22 s |
| 7 | SA swap | `--method sa_swap --iters 2000000 --alpha 0.95 --temps 150 --no-adaptive-window --polish 0` | 502.34 | 88.48 % | 42 % | 22 s |
| 8 | SA swap | `--method sa_swap --iters 2000000 --alpha 0.97 --temps 250 --no-adaptive-window --polish 0` | 508.08 | 88.35 % | 42 % | 21 s |
| 9 | SA swap | `--method sa_swap --iters 2000000 --alpha 0.95 --temps 150 --polish 300000` (adaptive window) | 500.04 | 88.54 % | 42 % | 32 s |
| 10 | SA move | `--method sa_move --iters 2000000 --alpha 0.95 --temps 150 --polish 300000 --min-spacing 0.3` | 498.19 | 88.58 % | 14 % | 24 s |
| 11 | SA move | `--method sa_move --iters 2000000 --alpha 0.95 --temps 150 --polish 300000` | 373.57 | 91.44 % | 44 % | 26 s |
| 12 | SA move | same as #11 with `--seed 2` | 365.65 | 91.62 % | 44 % | 26 s |
| 13 | SA move | same as #11 with `--seed 3` | 360.48 | 91.74 % | 42 % | 26 s |
| 14 | **SA move (final)** | defaults: `--iters 10000000 --alpha 0.97 --temps 300 --polish 1000000` | **295.57** | **93.22 %** | 44 % | 124 s |

## Discussion

**Random search (#1).** Each trial is independent and learns nothing from the trials before it. The best of 200 is only about 5 % better than the start, which is below the 5 % partial-credit threshold.

**Greedy vs. simulated annealing (#3 vs #7).** Greedy swapping improves very quickly (81 % in 2 s), then gets stuck in a local minimum. Running 10× more iterations only adds about 4 points. SA sometimes accepts moves that make HPWL worse, which lets it escape those local minima. With the same 2 M-move budget it ends about 23 % lower than greedy (502 vs 653).

**SA parameters.**
* *Starting temperature (#5).* If T0 is too cold, SA behaves almost like greedy and ends at 594. With the auto value (≈ 22.5), about 85 % of moves are accepted at the start.
* *Cooling rate (#6–#8).* With a fixed number of moves, α = 0.90, 0.95 and 0.97 all finish within 1.5 % of each other. The move budget matters more than α itself. Only a larger budget (#14) gave a big improvement.
* *Window (#4, #9).* A small fixed window from the start hurts, because long-distance moves are needed early on. An adaptive window starts at the full chip and shrinks as the temperature drops. It keeps more moves useful in the middle of the run: acceptance at T ≈ 0.65 is 19.8 %, compared with 9.7 % with the full-chip window. Combined with a final greedy polish, it gave the best swap-only result.

**Swap-only vs. displacement moves (#9 vs #11).** Swaps can only rearrange cells among the 689 original random positions. Moving cells uses the slack in the density rule (bins may hold 22–64 cells), so connected cells can sit closer together. That lowers HPWL by another 25 % (500 → 374). The trade-off is density: the placement gets closer to the limit (44 % deviation). Forcing a larger minimum spacing of 0.3 (#10) keeps the placement almost perfectly uniform (14 %), but most of the gain disappears. This is the basic wirelength-vs-density trade-off in placement.

**Robustness (#11–#13).** Three different seeds finish within about 4 % of each other, so the result is not a lucky seed.

**Checking the final placement.** Every cell is inside the 10 × 10 region, and the 4 × 4 density check passes. The minimum distance between any two cells is 0.200, while the initial placement has two cells only 0.014 apart. One caveat: on a finer 10 × 10 grid, a few small regions are empty and the densest holds 20 cells (the initial placement ranges from 2 to 14). If stricter uniformity is required, the swap-only result (#9, 88.5 %) keeps exactly the original set of positions.

**The 194-pin net.** Its cells cover the whole chip, so its HPWL stays close to 20 (19.75 → 17.68) in any density-legal placement. It is a fixed cost that cannot be optimized away.