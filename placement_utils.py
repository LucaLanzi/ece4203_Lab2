"""
placement_utils.py
==================
Utility library for the ECE4203 placement assignment.

Provides:
    load_placement(path)               -> dict
    save_placement(data, path)         -> None
    compute_hpwl(nets, placement)      -> float
    hpwl_breakdown(nets, placement)    -> list of dicts
    check_density(placement, grid)     -> dict
    print_density_report(result)       -> None
    hpwl_histogram(nets, placement)    -> None  (Tkinter window)
    visualize(data, title='')          -> None  (Tkinter window)

Typical student workflow
------------------------
    from placement_utils import load_placement, save_placement, compute_hpwl

    data = load_placement('assignment.json')

    # data['placement'] is a dict  {cell_name: [x, y]}
    # data['nets']      is a list  [[cell, cell, ...], ...]
    # data['grid']      is         [width, height]

    print('HPWL:', compute_hpwl(data['nets'], data['placement']))
    save_placement(data, 'my_placement.json')
"""

import json
import math
import tkinter as tk
from typing import Dict, List, Tuple, Optional


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_placement(path: str) -> dict:
    """
    Load a placement JSON file.

    Returns a dict with keys:
        'cells'        : list of cell names
        'nets'         : list of nets (each net is a list of cell names)
        'placement'    : dict mapping cell name -> [x, y]
        'grid'         : [width, height]
        'initial_hpwl' : HPWL of the original random placement (float)
    """
    with open(path) as f:
        data = json.load(f)
    for key in ('cells', 'nets', 'placement', 'grid'):
        if key not in data:
            raise ValueError(f"Missing key '{key}' in {path}")
    return data


def save_placement(data: dict, path: str) -> None:
    """
    Save a placement dict to a JSON file.
    Recomputes 'hpwl' automatically and runs a density uniformity check.
    Prints a warning if density check fails but saves regardless.
    """
    data = dict(data)
    data['hpwl'] = compute_hpwl(data['nets'], data['placement'])

    density = check_density(data['placement'], data['grid'])
    if not density['pass'] and not density.get('note'):
        print(f"WARNING: density check failed — "
              f"max deviation {density['max_deviation']*100:.1f}% "
              f"exceeds {density['tolerance']*100:.0f}% tolerance "
              f"({len(density['violations'])} bin(s) out of range)")

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {path}  (HPWL = {data['hpwl']:.4f})")


# ── HPWL ──────────────────────────────────────────────────────────────────────

def compute_hpwl(nets: List[List[str]],
                 placement: Dict[str, List[float]]) -> float:
    """
    Compute total Half-Perimeter Wire Length (HPWL).

    For each net: contribution = (max_x - min_x) + (max_y - min_y).
    Nets with fewer than 2 placed cells are skipped.
    """
    total = 0.0
    for net in nets:
        xs = [placement[c][0] for c in net if c in placement]
        ys = [placement[c][1] for c in net if c in placement]
        if len(xs) < 2:
            continue
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return round(total, 6)


def hpwl_breakdown(nets: List[List[str]],
                   placement: Dict[str, List[float]]) -> List[dict]:
    """
    Return per-net HPWL contributions as a list of dicts, sorted descending.
    Each dict: {'net': [...cell names...], 'hpwl': float}
    Useful for identifying which nets dominate wire length.
    """
    rows = []
    for net in nets:
        xs = [placement[c][0] for c in net if c in placement]
        ys = [placement[c][1] for c in net if c in placement]
        if len(xs) < 2:
            continue
        h = (max(xs) - min(xs)) + (max(ys) - min(ys))
        rows.append({'net': net, 'hpwl': round(h, 6)})
    return sorted(rows, key=lambda r: r['hpwl'], reverse=True)


# ── Density uniformity check ──────────────────────────────────────────────────

def check_density(placement: Dict[str, List[float]],
                  grid: List[float],
                  bins: int = 0,
                  tolerance: float = 0.50) -> dict:
    """
    Check that cells are distributed roughly uniformly across the layout.
    The grid is divided into bins×bins sub-regions; the cell count in each
    bin is compared to the ideal (total_cells / bins²).

    Args:
        placement : dict mapping cell name -> [x, y]
        grid      : [width, height]
        bins      : divisions per axis (0 = auto: floor(sqrt(n_cells/4)),
                    clamped to [3, 10], giving ~10 cells/bin on average)
        tolerance : max allowed fractional deviation from ideal (default 0.50)

    Returns a dict:
        {
          'pass'         : bool,
          'bins'         : int,           # actual bins used
          'tolerance'    : float,
          'ideal'        : float,         # ideal cells per bin
          'max_count'    : int,
          'min_count'    : int,
          'max_deviation': float,         # worst fractional deviation from ideal
          'empty_bins'   : int,
          'violations'   : list of (bin_row, bin_col, count, deviation)
        }
    """
    import math as _math
    gw, gh = grid
    n_cells = len(placement)

    # Auto-size bins so ideal count is ~4 cells/bin (enough to be meaningful)
    if bins <= 0:
        bins = max(3, min(10, int(_math.floor(_math.sqrt(n_cells / 32)))))

    ideal = n_cells / (bins * bins)

    # Not meaningful for very small netlists (< 2 cells/bin on average)
    if ideal < 2.0:
        return {
            'pass': True, 'bins': bins, 'tolerance': tolerance,
            'ideal': round(ideal, 3), 'max_count': 0, 'min_count': 0,
            'max_deviation': 0.0, 'empty_bins': 0, 'violations': [],
            'note': f'Skipped: {n_cells} cells gives only {ideal:.1f} cells/bin — too sparse to measure',
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
            dev = abs(cnt - ideal) / ideal if ideal > 0 else 0.0
            max_dev = max(max_dev, dev)
            if dev > tolerance:
                violations.append((row, col, cnt, round(dev, 4)))

    all_counts = [counts[r][c] for r in range(bins) for c in range(bins)]

    return {
        'pass'         : len(violations) == 0,
        'bins'         : bins,
        'tolerance'    : tolerance,
        'ideal'        : round(ideal, 3),
        'max_count'    : max(all_counts),
        'min_count'    : min(all_counts),
        'max_deviation': round(max_dev, 4),
        'empty_bins'   : sum(1 for c in all_counts if c == 0),
        'violations'   : sorted(violations, key=lambda v: -v[3]),
    }


def print_density_report(result: dict) -> None:
    """Pretty-print the result of check_density()."""
    if result.get('note'):
        print(f"Density check: SKIP — {result['note']}")
        return
    status = "PASS ✓" if result['pass'] else "FAIL ✗"
    print(f"Density check: {status}")
    print(f"  Grid        : {result['bins']}×{result['bins']} "
          f"({result['bins']**2} sub-regions)")
    print(f"  Ideal count : {result['ideal']:.2f} cells/bin")
    print(f"  Range       : {result['min_count']} – {result['max_count']} cells/bin")
    print(f"  Max deviation: {result['max_deviation']*100:.1f}%  "
          f"(tolerance {result['tolerance']*100:.0f}%)")
    if result['empty_bins']:
        print(f"  Empty bins  : {result['empty_bins']}")
    if result['violations']:
        print(f"  Violations  : {len(result['violations'])} bins exceed tolerance")
        for row, col, cnt, dev in result['violations'][:5]:
            print(f"    bin ({row},{col}): {cnt} cells  "
                  f"({dev*100:+.1f}% from ideal)")
        if len(result['violations']) > 5:
            print(f"    ... and {len(result['violations'])-5} more")


# ── Colour scheme (shared) ────────────────────────────────────────────────────

_BG       = "#0d1117"
_PANEL    = "#161b22"
_CELL_CLR = "#58a6ff"
_NET_CLR  = "#2d3f55"
_NET_HIGH = "#ff4444"
_TEXT     = "#e6edf3"
_DIM      = "#484f58"
_GRID_CLR = "#1c2128"
_BAR_CLR  = "#58a6ff"
_BAR_HIGH = "#ff4444"
_MEAN_CLR = "#ffd700"
_MED_CLR  = "#50fa7b"
_MARGIN   = 52
_DENS_OK  = "#1a3a1a"   # dark green fill for passing density bins
_DENS_BAD = "#3a1a1a"   # dark red fill for failing density bins
_DENS_OK_BORDER  = "#3fb950"
_DENS_BAD_BORDER = "#f85149"


# ── Histogram ─────────────────────────────────────────────────────────────────

def hpwl_histogram(nets: List[List[str]],
                   placement: Dict[str, List[float]],
                   bins: int = 0,
                   title: str = "Per-Net HPWL Distribution") -> None:
    """
    Open a Tkinter window showing a histogram of per-net HPWL values,
    with mean and median marked.

    Args:
        nets      : list of nets
        placement : dict mapping cell name -> [x, y]
        bins      : number of histogram bins (0 = auto: sqrt of net count)
        title     : window title
    """
    bd = hpwl_breakdown(nets, placement)
    if not bd:
        print("No nets to histogram.")
        return

    values = [r['hpwl'] for r in bd]
    n      = len(values)
    mean   = sum(values) / n
    sorted_v = sorted(values)
    if n % 2 == 1:
        median = sorted_v[n // 2]
    else:
        median = (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0

    n_bins = bins if bins > 0 else max(4, round(math.sqrt(n)))
    v_min  = min(values)
    v_max  = max(values)
    width  = (v_max - v_min) / n_bins if v_max > v_min else 1.0

    counts = [0] * n_bins
    for v in values:
        idx = min(int((v - v_min) / width), n_bins - 1)
        counts[idx] += 1

    root = tk.Tk()
    root.title(title)
    root.configure(bg=_BG)
    root.resizable(True, True)

    # Stats bar at top
    stats_frame = tk.Frame(root, bg=_PANEL)
    stats_frame.pack(fill=tk.X, padx=12, pady=(10, 0))

    stats = [
        ("Nets",   str(n),             _TEXT),
        ("Total",  f"{sum(values):.4f}", _TEXT),
        ("Mean",   f"{mean:.4f}",       _MEAN_CLR),
        ("Median", f"{median:.4f}",     _MED_CLR),
        ("Min",    f"{v_min:.4f}",      _DIM),
        ("Max",    f"{v_max:.4f}",      _DIM),
    ]
    for label, value, color in stats:
        cell = tk.Frame(stats_frame, bg=_PANEL, padx=14, pady=6)
        cell.pack(side=tk.LEFT)
        tk.Label(cell, text=label, bg=_PANEL, fg=_DIM,
                 font=("Courier", 8)).pack()
        tk.Label(cell, text=value, bg=_PANEL, fg=color,
                 font=("Courier", 11, "bold")).pack()

    # Canvas
    frame = tk.Frame(root, bg=_PANEL)
    frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

    canvas = tk.Canvas(frame, bg=_PANEL, highlightthickness=0,
                       width=600, height=320)
    canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def draw_histogram(event=None):
        canvas.delete("all")
        canvas.update_idletasks()
        W = canvas.winfo_width()  or 600
        H = canvas.winfo_height() or 320

        PL, PR, PT, PB = 52, 20, 20, 48
        cw = W - PL - PR
        ch = H - PT - PB

        max_count = max(counts) if counts else 1

        def val_to_x(v):
            return PL + (v - v_min) / (v_max - v_min + 1e-9) * cw

        def count_to_y(c):
            return PT + ch - (c / max_count) * ch

        # Y grid lines and labels
        y_ticks = 4
        for i in range(y_ticks + 1):
            frac = i / y_ticks
            cnt  = round(frac * max_count)
            y    = PT + ch - frac * ch
            canvas.create_line(PL, y, PL + cw, y,
                               fill=_GRID_CLR, dash=(2, 6))
            canvas.create_text(PL - 5, y, text=str(cnt),
                               fill=_DIM, font=("Courier", 8), anchor=tk.E)

        # Bars
        bar_w = cw / n_bins
        for i, cnt in enumerate(counts):
            x0 = PL + i * bar_w + 1
            x1 = PL + (i + 1) * bar_w - 1
            y0 = count_to_y(cnt)
            y1 = PT + ch
            # Highlight bins containing mean or median
            bin_lo = v_min + i * width
            bin_hi = bin_lo + width
            contains_mean   = bin_lo <= mean   < bin_hi
            contains_median = bin_lo <= median < bin_hi
            color = (_BAR_HIGH if contains_mean or contains_median
                     else _BAR_CLR)
            canvas.create_rectangle(x0, y0, x1, y1,
                                    fill=color, outline=_PANEL, width=1)
            # Count label above bar
            if cnt > 0:
                canvas.create_text((x0 + x1) / 2, y0 - 4,
                                   text=str(cnt), fill=_TEXT,
                                   font=("Courier", 7))

        # X-axis labels (bin edges)
        label_step = max(1, n_bins // 6)
        for i in range(0, n_bins + 1, label_step):
            v   = v_min + i * width
            x   = PL + i * bar_w
            canvas.create_line(x, PT + ch, x, PT + ch + 4, fill=_DIM)
            canvas.create_text(x, PT + ch + 14, text=f"{v:.2f}",
                               fill=_DIM, font=("Courier", 7))

        # Mean line
        xm = val_to_x(mean)
        canvas.create_line(xm, PT, xm, PT + ch,
                           fill=_MEAN_CLR, width=2, dash=(6, 3))
        canvas.create_text(xm + 3, PT + 4, text=f"mean\n{mean:.3f}",
                           fill=_MEAN_CLR, font=("Courier", 8), anchor=tk.NW)

        # Median line
        xmed = val_to_x(median)
        canvas.create_line(xmed, PT, xmed, PT + ch,
                           fill=_MED_CLR, width=2, dash=(4, 4))
        canvas.create_text(xmed + 3, PT + ch - 28,
                           text=f"median\n{median:.3f}",
                           fill=_MED_CLR, font=("Courier", 8), anchor=tk.NW)

        # Axes
        canvas.create_line(PL, PT, PL, PT + ch, fill=_DIM, width=1)
        canvas.create_line(PL, PT + ch, PL + cw, PT + ch, fill=_DIM, width=1)

        canvas.create_text(PL + cw // 2, H - 8,
                           text="per-net HPWL", fill=_DIM,
                           font=("Courier", 9))
        canvas.create_text(10, PT + ch // 2,
                           text="count", fill=_DIM,
                           font=("Courier", 9), angle=90)

    canvas.bind("<Configure>", draw_histogram)
    root.mainloop()


# ── Placement visualiser ──────────────────────────────────────────────────────

def visualize(data: dict, title: str = "Placement Viewer",
              compare: Optional[dict] = None) -> None:
    """
    Open a Tkinter window showing the placement.

    Args:
        data    : placement dict (from load_placement or your algorithm)
        title   : window title string
        compare : optional second placement dict to show side-by-side

    The viewer highlights the top-5 HPWL nets in red with bounding boxes.
    Close the window to continue your script.
    """
    root = tk.Tk()
    root.title(title)
    root.configure(bg=_BG)

    total_hpwl = compute_hpwl(data['nets'], data['placement'])
    root.title(f"{title}  —  HPWL = {total_hpwl:.4f}")

    panels    = [data] if compare is None else [data, compare]
    subtitles = (["Your placement"]
                 if compare is None
                 else ["Initial (random)", "Your placement"])

    for col_idx, pdata in enumerate(panels):
        phpwl = compute_hpwl(pdata['nets'], pdata['placement'])
        breakdown = hpwl_breakdown(pdata['nets'], pdata['placement'])
        top5 = {tuple(sorted(r['net'])) for r in breakdown[:5]}

        frame = tk.Frame(root, bg=_PANEL)
        frame.grid(row=0, column=col_idx,
                   padx=(14 if col_idx == 0 else 6, 14),
                   pady=12, sticky="nsew")
        root.columnconfigure(col_idx, weight=1)
        root.rowconfigure(0, weight=1)

        tk.Label(frame,
                 text=f"{subtitles[col_idx]}   HPWL = {phpwl:.4f}",
                 bg=_PANEL, fg=_TEXT,
                 font=("Courier", 10, "bold")).pack(anchor=tk.W, padx=8,
                                                    pady=(6, 0))

        c = tk.Canvas(frame, bg=_PANEL, highlightthickness=0,
                      width=480, height=480)
        c.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        def draw(canvas, pd, ph, pt, density_result):
            canvas.delete("all")
            canvas.update_idletasks()
            W  = canvas.winfo_width()  or 480
            H  = canvas.winfo_height() or 480
            m  = _MARGIN
            gw, gh = pd['grid']

            def to_px(x, y):
                return (m + (x / gw) * (W - 2 * m),
                        H - m - (y / gh) * (H - 2 * m))

            # ── Density heatmap overlay (drawn first, behind everything) ──
            if not density_result.get('note'):
                bins  = density_result['bins']
                ideal = density_result['ideal']
                tol   = density_result['tolerance']
                # Rebuild bin counts for this panel
                bin_counts = [[0] * bins for _ in range(bins)]
                for cell, (cx, cy) in pd['placement'].items():
                    col = min(int(cx / gw * bins), bins - 1)
                    row = min(int(cy / gh * bins), bins - 1)
                    bin_counts[row][col] += 1

                viol_set = {(r2, c2) for r2, c2, _, _ in density_result['violations']}

                for row in range(bins):
                    for col in range(bins):
                        cnt   = bin_counts[row][col]
                        # bin covers [col/bins*gw, (col+1)/bins*gw] x [row/bins*gh, ...]
                        bx0, by1 = to_px( col      / bins * gw,  row      / bins * gh)
                        bx1, by0 = to_px((col + 1) / bins * gw, (row + 1) / bins * gh)
                        failing = (row, col) in viol_set
                        fill    = _DENS_BAD   if failing else _DENS_OK
                        border  = _DENS_BAD_BORDER if failing else _DENS_OK_BORDER
                        canvas.create_rectangle(bx0, by0, bx1, by1,
                                                fill=fill, outline=border, width=1)
                        # Cell count label in each bin
                        cx_mid = (bx0 + bx1) / 2
                        cy_mid = (by0 + by1) / 2
                        label_clr = _DENS_BAD_BORDER if failing else _DENS_OK_BORDER
                        canvas.create_text(cx_mid, cy_mid, text=str(cnt),
                                           fill=label_clr,
                                           font=("Courier", 8, "bold"))

            # ── Axis grid lines ───────────────────────────────────────────
            steps = 5
            for i in range(steps + 1):
                fx = i / steps
                x0, y0 = to_px(fx * gw, 0)
                x1, y1 = to_px(fx * gw, gh)
                canvas.create_line(x0, y0, x1, y1, fill=_GRID_CLR)
                canvas.create_text(x0, H - m + 14,
                                   text=f"{fx*gw:.1f}", fill=_DIM,
                                   font=("Courier", 7))
            for i in range(steps + 1):
                fy = i / steps
                x0, y0 = to_px(0, fy * gh)
                x1, y1 = to_px(gw, fy * gh)
                canvas.create_line(x0, y0, x1, y1, fill=_GRID_CLR)
                canvas.create_text(m - 6, y0, text=f"{fy*gh:.1f}",
                                   fill=_DIM, font=("Courier", 7),
                                   anchor=tk.E)

            # ── Nets ──────────────────────────────────────────────────────
            for net in pd['nets']:
                members = [n for n in net if n in pd['placement']]
                if len(members) < 2:
                    continue
                if len(members) > 10:
                    continue  # skip very large nets for visual clarity
                key    = tuple(sorted(members))
                is_hot = key in pt
                color  = _NET_HIGH if is_hot else _NET_CLR
                width  = 1.6 if is_hot else 0.8

                if len(members) == 2:
                    x1c, y1c = to_px(*pd['placement'][members[0]])
                    x2c, y2c = to_px(*pd['placement'][members[1]])
                    canvas.create_line(x1c, y1c, x2c, y2c,
                                       fill=color, width=width)
                else:
#                    xs = [pd['placement'][n][0] for n in members]
#                    ys = [pd['placement'][n][1] for n in members]
#                    mxn, myn = to_px(sum(xs)/len(xs), sum(ys)/len(ys))
                    first = True
                    for n in members:
                        px2, py2 = to_px(*pd['placement'][n])
                        if not first:
                            canvas.create_line(opx2, opy2, px2, py2,
                                               fill=color, width=width)
                            opx2, opy2 = px2, py2
                        else:
                            first = False 
                            opx2, opy2 = px2, py2   
#                        canvas.create_line(mxn, myn, px2, py2,
#                                           fill=color, width=width)

                if is_hot:
                    xv = [pd['placement'][n][0] for n in members]
                    yv = [pd['placement'][n][1] for n in members]
                    bx0c, by0c = to_px(min(xv), min(yv))
                    bx1c, by1c = to_px(max(xv), max(yv))
                    canvas.create_rectangle(bx0c, by0c, bx1c, by1c,
                                            outline=_NET_HIGH, dash=(3, 4))

            # ── Cells ─────────────────────────────────────────────────────
            r = 12
            for cell in pd['cells']:
                if cell not in pd['placement']:
                    continue
                pxc, pyc = to_px(*pd['placement'][cell])
                canvas.create_oval(pxc-r, pyc-r, pxc+r, pyc+r,
                                   fill=_CELL_CLR, outline="#ffffff", width=1.2)
                canvas.create_text(pxc, pyc, text=cell,
                                   fill="#000000", font=("Courier", 7, "bold"))

            # ── Overlays: HPWL + density status badge ─────────────────────
            canvas.create_text(W - 8, 8, text=f"HPWL = {ph:.4f}",
                               fill=_TEXT, font=("Courier", 9, "bold"),
                               anchor=tk.NE)

            if density_result.get('note'):
                dens_txt = "density: n/a"
                dens_clr = _DIM
            elif density_result['pass']:
                dens_txt = (f"density: PASS  "
                            f"max {density_result['max_deviation']*100:.0f}% dev")
                dens_clr = _DENS_OK_BORDER
            else:
                n_viol = len(density_result['violations'])
                dens_txt = (f"density: FAIL  "
                            f"{n_viol} bin(s)  "
                            f"max {density_result['max_deviation']*100:.0f}% dev")
                dens_clr = _DENS_BAD_BORDER
            canvas.create_text(W - 8, 26, text=dens_txt,
                               fill=dens_clr, font=("Courier", 8),
                               anchor=tk.NE)

        density_result = check_density(pdata['placement'], pdata['grid'])

        def make_cb(cv, pd, ph, pt, dr):
            return lambda e: draw(cv, pd, ph, pt, dr)

        c.bind("<Configure>", make_cb(c, pdata, phpwl, top5, density_result))

    # Legend
    leg = tk.Frame(root, bg=_BG)
    leg.grid(row=1, column=0, columnspan=len(panels),
             padx=14, pady=(0, 10), sticky=tk.W)
    legend_items = [
        (_CELL_CLR,        "oval",  "Cell"),
        (_NET_HIGH,        "oval",  "Top-5 HPWL nets (bounding box shown)"),
        (_NET_CLR,         "oval",  "Other nets"),
        (_DENS_OK_BORDER,  "rect",  "Density bin: pass"),
        (_DENS_BAD_BORDER, "rect",  "Density bin: fail"),
    ]
    for color, shape, label in legend_items:
        row = tk.Frame(leg, bg=_BG)
        row.pack(side=tk.LEFT, padx=10)
        ic = tk.Canvas(row, bg=_BG, width=14, height=14, highlightthickness=0)
        ic.pack(side=tk.LEFT)
        if shape == "oval":
            ic.create_oval(2, 2, 12, 12, fill=color, outline="")
        else:
            ic.create_rectangle(2, 2, 12, 12, fill=color,
                                outline=color, width=1)
        tk.Label(row, text=f" {label}", bg=_BG, fg=_DIM,
                 font=("Courier", 9)).pack(side=tk.LEFT)

    root.mainloop()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, argparse

    ap = argparse.ArgumentParser(
        description="Visualize and score a placement JSON file.")
    ap.add_argument("placement",         help="Placement JSON file")
    ap.add_argument("--compare",         help="Second JSON to compare side-by-side",
                    default=None)
    ap.add_argument("--histogram", "-H", help="Show per-net HPWL histogram",
                    action="store_true")
    ap.add_argument("--hpwl-only", "-q", help="Print HPWL and exit (no GUI)",
                    action="store_true")
    args = ap.parse_args()

    data  = load_placement(args.placement)
    total = compute_hpwl(data['nets'], data['placement'])

    if args.hpwl_only:
        baseline = data.get('initial_hpwl') or data.get('hpwl')
        print(f"HPWL = {total:.4f}")
        if baseline and baseline != total:
            pct = (baseline - total) / baseline * 100
            print(f"vs initial = {baseline:.4f}  ({pct:+.1f}%)")
        sys.exit(0)

    if args.histogram:
        hpwl_histogram(data['nets'], data['placement'],
                       title=args.placement)
    else:
        compare_data = load_placement(args.compare) if args.compare else None
        visualize(data, title=args.placement, compare=compare_data)
