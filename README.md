# Lab 2: Placement Optimization

The Lab 2 directory in Canvas contains four files:

| File | Description |
| --- | --- |
| `initial_placement.json` | Contains the cells, nets, and initial cell placements. This is the starting point for optimization. It has a total HPWL of **4362**. The square placement region is **10.0 × 10.0** and must not be changed. |
| `placement_utils.py` | Provides useful functions for the optimizer. See the comments in the file. You can also run it directly with an input JSON file to view the placement, HPWL values, and density check. |
| `grade_placement.py` | Checks whether your result improves the HPWL and satisfies the density rule described below. |
| `random_optimize.py` | Provides an example optimizer that generates many random placements and keeps the best ones. It is intentionally slow and inefficient; you can do much better. |

## Density Requirement

Cells must be distributed roughly evenly across the **10.0 × 10.0** square region. The cell density must not vary drastically across the placement.

Cells cannot be bunched together or overlap in the final design. Although this would produce a very low HPWL, it would not be a valid or useful placement.

If your optimizer only swaps positions from the initial placement, it will not violate the density requirement. If it moves cells to new positions, make sure that the resulting placement still satisfies the requirement. The `grade_placement.py` tool checks the density for you.

## Optimizer Requirements

Your optimizer must:

1. Take `initial_placement.json` as input.
2. Produce a new `output.json` file containing a modified placement.
3. Improve the HPWL while satisfying the density requirement.

Use `random_optimize.py` as an example of how to load and optimize a placement.

You are encouraged to use AI to explore different optimization approaches and see how much you can improve the result.

## Python Dependencies

To run the visualizer, install the Tk package for Python. Depending on your system, the package may be named `tk` or `python3-tk`.

The `math` and `json` modules are part of the standard Python distribution and should already be available.
