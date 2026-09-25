#!/usr/bin/env python
"""
Grid Timeline Builder - DaVinci Resolve (Studio) workspace script.

Builds a mosaic / contact-sheet timeline from a Media Pool bin:
every shot on its own video track, scaled into a uniform grid cell,
all starting at the timeline start, optionally extended to a common
length by loop or bounce (ping-pong).

Install:
  macOS  : ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/
  Windows: %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Edit\\
  Linux  : ~/.local/share/DaVinciResolve/Fusion/Scripts/Edit/
Run: Workspace > Scripts > Edit > Grid_Timeline_Builder

Verified on Resolve 21.1:
  - Items are forced to Scaling = Fit, zoom is relative to the fitted size.
  - Pan/Tilt are NOT timeline pixels: they are scaled by the fitted image size.
      real_dx = Pan  * fitted_w / timeline_w
      real_dy = Tilt * fitted_h / timeline_h
    (measured on 3840x2160, 2160x3840, 2160x2160, 1920x1080 timelines)
  - AppendToTimeline startFrame/endFrame: end is exclusive.
  - SetSpeed({"Percentage": -100}) reverses an item in place (used for bounce).

Crop (v1.4 rewrite - manual Crop properties dropped):
  - v1.3's pixel-unit fix was confirmed correct (readback matched exactly: set
    CropLeft=896.0, got back 896.0) - but a same-aspect test (1:1 crop target on a
    1:1 canvas, the cleanest possible case) still rendered broken: only every
    Nth track (N = column count) was visible, everything else black. So the bug was
    never (only) about units - manual CropLeft/Right/Top/Bottom combined with
    Scaling=Fit across many stacked tracks was producing unreliable results I could
    not fully explain from documentation alone, after three iterations.
  - Replaced entirely with Scaling=Fill (resolve.SCALE_FILL), confirmed via
    Blackmagic's own forum as the documented "scale up and crop the overflow,
    centered" behavior - Resolve's own renderer does the crop, not this script's
    arithmetic. No more CropLeft/Right/Top/Bottom, no more solve_crop().
  - Real limitation: Fill covers relative to the CANVAS's own aspect, not an
    arbitrary chosen crop-basis aspect. When crop basis == canvas aspect (Timeline
    resolution basis, or a Custom/Dominant value that happens to match): clean,
    gap-free, undistorted. When it doesn't match: ZoomX/ZoomY are set independently
    to fill the tile with no gap, at the cost of mild non-uniform stretch on one
    axis. A true distortion-free arbitrary-aspect crop needs a compound clip per
    source clip, sized to the target aspect - not implemented; build_grid() logs a
    warning when basis != canvas aspect so this isn't silent.
  - "timelineFrameRate" SetSetting key for FPS override remains unconfirmed against
    this API version - unrelated to any of the above.

Defaults (v1.5): Gap 2.0 (% of timeline width), Track color Cycle palette,
  Shorter clips Bounce (ping-pong). Frame rate left at Project default (no
  override). All other widget defaults unchanged from prior versions. NOTE: the
  saved-state file (STATE_FILE) is applied AFTER these hardcoded defaults and
  overrides them if it exists - delete it once for these new defaults to actually
  show up on next launch, otherwise your last-used values keep winning, as
  persistence is designed to do.

v1.6: Timeline Name is now persisted (previously deliberately excluded - see
  PERSIST_* comment). Restoring it bypasses the auto-name-from-bin+resolution
  logic, so it behaves like a manual edit: reopening the GUI, changing params, and
  rebuilding targets the same timeline name unless you type a different one.
  Non-Replace de-dup suffix changed from "_vNN" (2-digit, starting at v02) to
  "_vNNN" (3-digit, starting at v001).
"""

import math
import random
import re
import os
import json

SCRIPT_TITLE = "Grid Timeline Builder"
VERSION = "1.6"

STATE_FILE = os.path.join(os.path.expanduser("~"), ".grid_timeline_builder_state.json")

RES_PRESETS = [
    ("Custom", None),
    ("2160 x 2160 (square UHD)", (2160, 2160)),
    ("3840 x 2160 (UHD)", (3840, 2160)),
    ("4096 x 2160 (DCI 4K)", (4096, 2160)),
    ("1920 x 1080 (HD)", (1920, 1080)),
    ("1080 x 1080 (square HD)", (1080, 1080)),
    ("1080 x 1920 (vertical HD)", (1080, 1920)),
    ("2160 x 3840 (vertical UHD)", (2160, 3840)),
    ("4096 x 4096", (4096, 4096)),
]
GAP_UNITS = ["px", "% of timeline width", "% of timeline height"]
OUTER_MODES = ["Half gap (equal padding around every clip)", "Full gap", "None"]
LENGTH_MODES = ["Loop", "Bounce (ping-pong)", "None (native length)"]
ORDER_MODES = ["Name", "Random", "By Source Timecode"]
ANCHOR_MODES = ["Top", "Center"]
ASPECT_MODES = ["Letterbox (fit)", "Crop to fill"]
CROP_BASIS_MODES = ["Dominant source aspect", "Timeline resolution", "Custom"]
TRACK_COLOR_MODES = ["None", "Cycle palette", "Random"]
CLIP_COLOR_PALETTE = ["Orange", "Apricot", "Yellow", "Lime", "Olive", "Green", "Teal", "Navy",
                       "Blue", "Purple", "Violet", "Pink", "Tan", "Beige", "Brown", "Chocolate"]
FPS_OPTIONS = ["Project default", "23.976", "24", "25", "29.97", "30",
               "47.95", "48", "50", "59.94", "60"]
ALL_RES = "All resolutions"


# --------------------------------------------------------------------------
# Resolve access
# --------------------------------------------------------------------------
def get_resolve():
    g = globals()
    if g.get("resolve"):
        return g["resolve"]
    if g.get("app"):
        return g["app"].GetResolve()
    import DaVinciResolveScript as dvr
    return dvr.scriptapp("Resolve")


def get_bmd():
    g = globals()
    if g.get("bmd"):
        return g["bmd"]
    import DaVinciResolveScript as dvr  # the module is fusionscript itself
    return dvr


# --------------------------------------------------------------------------
# Media pool helpers
# --------------------------------------------------------------------------
def sanitize_name(s):
    """Collapse anything not alnum into a single underscore; never returns empty."""
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_") or "grid"


def list_folders(root):
    """Return [(path, folder)] for every folder, depth-first."""
    out = []

    def walk(folder, path):
        out.append((path, folder))
        for sub in folder.GetSubFolderList() or []:
            walk(sub, path + "/" + sub.GetName())

    walk(root, root.GetName())
    return out


def collect_clips(folder, recursive):
    clips = list(folder.GetClipList() or [])
    if recursive:
        for sub in folder.GetSubFolderList() or []:
            clips += collect_clips(sub, True)
    return clips


def parse_res(clip):
    try:
        w, h = clip.GetClipProperty("Resolution").lower().split("x")
        return int(w), int(h)
    except Exception:
        return None


def clip_frames(clip):
    try:
        return int(clip.GetClipProperty("Frames"))
    except Exception:
        return 0


def clip_start(clip):
    try:
        return int(clip.GetClipProperty("Start"))
    except Exception:
        return 0

def clip_start_tc(clip):
    """Source (embedded) start timecode as a string, e.g. '01:00:12:04'.
    Lexicographic sort works because Resolve reports fixed-width HH:MM:SS:FF."""
    try:
        return clip.GetClipProperty("Start TC") or "00:00:00:00"
    except Exception:
        return "00:00:00:00"


def usable_clips(folder, recursive):
    """Video clips with a readable resolution and frame count."""
    out = []
    for c in collect_clips(folder, recursive):
        if (c.GetClipProperty("Type") or "") not in ("Video", "Video + Audio"):
            continue
        if parse_res(c) is None or clip_frames(c) < 1:
            continue
        out.append(c)
    return out


def resolution_summary(clips):
    counts = {}
    for c in clips:
        key = "%dx%d" % parse_res(c)
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def solve_layout(n, W, H, aspect, gap, outer, min_grid, force_cols):
    """
    Returns dict with cols, rows, box_w, box_h, off_x, off_y.
    Tiles: box_w x box_h, spacing `gap` between tiles, `outer` at frame edges.
    """
    best = None
    col_range = [force_cols] if force_cols > 0 else range(min_grid, max(min_grid, n) + 1)
    for cols in col_range:
        rows = max(min_grid, int(math.ceil(float(n) / cols)))
        box_w = (W - 2 * outer - (cols - 1) * gap) / float(cols)
        box_h = box_w / aspect
        need_h = rows * box_h + (rows - 1) * gap + 2 * outer
        if need_h > H + 1e-6:
            box_h = (H - 2 * outer - (rows - 1) * gap) / float(rows)
            box_w = box_h * aspect
        if box_w <= 1 or box_h <= 1:
            continue
        if best is None or box_w > best[0] + 1e-9:
            best = (box_w, cols, rows, box_h)
    if best is None:
        raise ValueError("Gap/margin too large for this resolution and clip count.")
    box_w, cols, rows, box_h = best
    grid_w = cols * box_w + (cols - 1) * gap + 2 * outer
    grid_h = rows * box_h + (rows - 1) * gap + 2 * outer
    return {
        "cols": cols, "rows": rows, "box_w": box_w, "box_h": box_h,
        "grid_w": grid_w, "grid_h": grid_h,
        "off_x": (W - grid_w) / 2.0, "off_y": (H - grid_h) / 2.0,
    }


def dominant_aspect(clips):
    counts = {}
    for c in clips:
        w, h = parse_res(c)
        a = round(float(w) / h, 4)
        counts[a] = counts.get(a, 0) + 1
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def resolve_target_aspect(cfg, clips, W, H):
    """Aspect ratio used for tile shape, per cfg['crop_basis']. Also compared
    against the canvas's own aspect to decide whether Scaling=Fill (build_grid)
    can crop each clip cleanly or has to stretch slightly to avoid a gap."""
    if cfg.get("aspect_mode") == "crop":
        if cfg["crop_basis"] == "timeline":
            return float(W) / H
        if cfg["crop_basis"] == "custom":
            return float(cfg["crop_w"]) / float(cfg["crop_h"])
    return dominant_aspect(clips)


# --------------------------------------------------------------------------
# Time segments
# --------------------------------------------------------------------------
def build_segments(start, frames, length, mode):
    """
    Returns list of (src_a, src_b, reverse, duration); src_b exclusive.
    reverse=True plays src_b-1 down to src_a.
    mode: 'loop' | 'bounce' | 'none'
    """
    if mode == "none" or length <= frames:
        take = frames if mode == "none" else min(frames, length)
        return [(start, start + take, False, take)]
    segs, pos, forward = [], 0, True
    bounce = mode == "bounce" and frames > 2
    while pos < length:
        if bounce and not forward:
            a, b = start + 1, start + frames - 1        # skip both end frames
            avail, rev = b - a, True
        else:
            a, b = start, start + frames
            avail, rev = frames, False
        take = min(avail, length - pos)
        if rev:
            a = b - take          # reversed leg starts from the highest frame
        else:
            b = a + take
        segs.append((a, b, rev, take))
        pos += take
        if bounce:
            forward = not forward
    return segs


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build_grid(resolve, cfg, log=print):
    """
    cfg keys:
      folder, recursive, res_filter (None or 'WxH'), timeline_name, replace,
      W, H, gap_value, gap_unit (0 px, 1 %W, 2 %H), outer_mode (0 half, 1 full, 2 none),
      force_cols (0 auto), min_grid, anchor ('top'|'center'), order ('name'|'random'|'tc'),
      length_mode ('loop'|'bounce'|'none'), custom_length (0 = longest),
      fill_random (bool), seed (None or int),
      aspect_mode ('fit'|'crop'), crop_basis ('dominant'|'timeline'|'custom'),
      crop_w, crop_h (used only when crop_basis == 'custom'),
      track_color ('none'|'cycle'|'random'), fps (None or a string from FPS_OPTIONS)
    """
    project = resolve.GetProjectManager().GetCurrentProject()
    mp = project.GetMediaPool()
    W, H = int(cfg["W"]), int(cfg["H"])

    clips = usable_clips(cfg["folder"], cfg["recursive"])
    if cfg.get("res_filter"):
        clips = [c for c in clips if "%dx%d" % parse_res(c) == cfg["res_filter"]]
    if not clips:
        raise ValueError("No usable video clips in the selected bin / resolution filter.")

    rng = random.Random(cfg.get("seed"))
    if cfg["order"] == "random":
        rng.shuffle(clips)
    elif cfg["order"] == "tc":
        clips.sort(key=clip_start_tc)
    else:
        clips.sort(key=lambda c: (c.GetClipProperty("Clip Name") or "").upper())
    n = len(clips)

    if cfg["gap_unit"] == 1:
        gap = W * cfg["gap_value"] / 100.0
    elif cfg["gap_unit"] == 2:
        gap = H * cfg["gap_value"] / 100.0
    else:
        gap = float(cfg["gap_value"])
    outer = {0: gap / 2.0, 1: gap, 2: 0.0}[cfg["outer_mode"]]

    aspect = resolve_target_aspect(cfg, clips, W, H)
    canvas_aspect = float(W) / H
    aspect_mismatch = cfg["aspect_mode"] == "crop" and abs(aspect - canvas_aspect) > 1e-4
    lay = solve_layout(n, W, H, aspect, gap, outer, cfg["min_grid"], cfg["force_cols"])
    cols, box_w, box_h = lay["cols"], lay["box_w"], lay["box_h"]
    off_x = lay["off_x"]
    off_y = 0.0 if (cfg["anchor"] == "top" or cfg["fill_random"]) else lay["off_y"]
    pitch_x, pitch_y = box_w + gap, box_h + gap

    layout = list(clips)
    if cfg["fill_random"]:
        # fill the last partial row, then add rows until the frame bottom is covered
        rows_total = int(math.ceil(float(n) / cols))
        while off_y + outer + rows_total * pitch_y < H:
            rows_total += 1
        need = rows_total * cols - n
        pool = []
        while len(pool) < need:
            batch = list(clips)
            rng.shuffle(batch)
            pool += batch
        layout += pool[:need]

    length = int(cfg["custom_length"]) or max(clip_frames(c) for c in clips)

    # timeline
    existing = [project.GetTimelineByIndex(i + 1) for i in range(project.GetTimelineCount())]
    same = [t for t in existing if t.GetName() == cfg["timeline_name"]]
    name = cfg["timeline_name"]
    if same:
        if cfg["replace"]:
            mp.DeleteTimelines(same)
        else:
            names = set(t.GetName() for t in existing)
            k = 1
            while "%s_v%03d" % (name, k) in names:
                k += 1
            name = "%s_v%03d" % (name, k)

    mp.SetCurrentFolder(cfg["folder"])
    tl = mp.CreateEmptyTimeline(name)
    if not tl:
        raise RuntimeError("CreateEmptyTimeline failed for '%s'." % name)
    project.SetCurrentTimeline(tl)
    tl.SetSetting("useCustomSettings", "1")
    tl.SetSetting("timelineResolutionWidth", str(W))
    tl.SetSetting("timelineResolutionHeight", str(H))
    tl.SetSetting("timelineInputResMismatchBehavior", "scaleToFit")
    if cfg.get("fps"):
        tl.SetSetting("timelineFrameRate", cfg["fps"])
    while tl.GetTrackCount("video") < len(layout):
        tl.AddTrack("video")
    t0 = tl.GetStartFrame()

    log("Timeline '%s'  %dx%d" % (name, W, H))
    log("Clips %d (+%d fill)  grid %d x %d  tile %.1f x %.1f px  gap %.1f  outer %.1f"
        % (n, len(layout) - n, cols, int(math.ceil(float(len(layout)) / cols)),
           box_w, box_h, gap, outer))
    log("Length %d frames, mode %s" % (length, cfg["length_mode"]))
    log("Aspect %s (basis %s, target %.4f, canvas %.4f)  track color %s  fps %s"
        % (cfg["aspect_mode"], cfg["crop_basis"], aspect, canvas_aspect,
           cfg["track_color"], cfg.get("fps") or "project default"))
    if aspect_mismatch:
        log("WARNING: crop basis (%.4f) does not match the canvas aspect (%.4f). "
            "Scaling=Fill covers relative to the canvas, not this target, so tiles "
            "will be filled with a slight non-uniform stretch instead of a gap. "
            "Use 'Timeline resolution' crop basis for a clean, undistorted crop."
            % (aspect, canvas_aspect))

    problems, total_items = [], 0
    for i, c in enumerate(layout):
        track = i + 1
        r, col = divmod(i, cols)
        sw, sh = parse_res(c)
        cx = off_x + outer + col * pitch_x + box_w / 2.0 - W / 2.0
        cy = H / 2.0 - (off_y + outer + r * pitch_y + box_h / 2.0)

        if cfg["aspect_mode"] == "crop":
            # Scaling=Fill covers the full W x H canvas per clip (Resolve's own
            # scale-and-crop-overflow behavior - see module docstring). Its
            # baseline is therefore exactly W x H, so Zoom/Pan/Tilt are computed
            # directly against canvas pixels, independent of source resolution.
            scaling_mode = getattr(resolve, "SCALE_FILL", 3)  # 3 = Fill, per documented enum
            zoom_x = box_w / float(W)
            zoom_y = box_h / float(H)
            pan, tilt = cx, cy
        else:
            scaling_mode = resolve.SCALE_FIT
            fit = min(float(W) / sw, float(H) / sh)
            fw, fh = sw * fit, sh * fit
            disp_w = min(box_w, box_h * sw / float(sh))   # contain inside the tile
            zoom_x = zoom_y = disp_w / fw
            pan = cx * W / fw
            tilt = cy * H / fh

        if cfg["track_color"] == "cycle":
            color = CLIP_COLOR_PALETTE[i % len(CLIP_COLOR_PALETTE)]
        elif cfg["track_color"] == "random":
            color = rng.choice(CLIP_COLOR_PALETTE)
        else:
            color = None

        s, fr = clip_start(c), clip_frames(c)
        segs = build_segments(s, fr, length, cfg["length_mode"])
        infos, pos = [], 0
        for a, b, rev, dur in segs:
            ci = {"mediaPoolItem": c, "trackIndex": track, "recordFrame": t0 + pos, "mediaType": 1}
            if rev or a != s or b != s + fr:
                ci["startFrame"] = a
                ci["endFrame"] = b
            infos.append(ci)
            pos += dur
        items = mp.AppendToTimeline(infos) or []
        if len(items) != len(segs):
            problems.append("%s: appended %d of %d segments"
                            % (c.GetClipProperty("Clip Name"), len(items), len(segs)))
        for it, seg in zip(items, segs):
            it.SetProperty("Scaling", scaling_mode)
            it.SetProperty("ZoomGang", False)   # allow ZoomX/ZoomY to differ (crop-mode stretch case)
            it.SetProperty("ZoomX", zoom_x)
            it.SetProperty("ZoomY", zoom_y)
            it.SetProperty("Pan", pan)
            it.SetProperty("Tilt", tilt)
            if color:
                it.SetClipColor(color)
            if seg[2]:
                it.SetSpeed({"Percentage": -100.0, "RippleTimeline": False})
        total_items += len(items)
        label = (c.GetClipProperty("Clip Name") or "clip").split("_")[0]
        tl.SetTrackName("video", track, ("FILL_" if i >= n else "") + label)

        got = sorted(tl.GetItemListInTrack("video", track) or [], key=lambda x: x.GetStart())
        expect_end = t0 + sum(sg[3] for sg in segs)
        if got and got[-1].GetEnd() != expect_end:
            problems.append("%s: ends at %d, expected %d" % (label, got[-1].GetEnd(), expect_end))
        for x, y in zip(got, got[1:]):
            if x.GetEnd() != y.GetStart():
                problems.append("%s: gap/overlap at %d" % (label, x.GetEnd()))
                break

    log("Items placed: %d on %d tracks" % (total_items, len(layout)))
    if problems:
        log("WARNINGS:")
        for p in problems:
            log("  " + p)
    else:
        log("Checks passed: no gaps, all tracks end where expected.")
    return {"timeline": name, "problems": problems, "items": total_items,
            "cols": cols, "tracks": len(layout), "length": length}


# --------------------------------------------------------------------------
# Persisted UI state
# --------------------------------------------------------------------------
# Widgets whose value is a durable user preference, restored on next launch.
# TlName is handled separately below (see apply_saved_state) since restoring it
# has to bypass the auto-name-from-bin+resolution logic rather than go through it.
# Deliberately excludes: ResFilter (regenerated from the bin's actual clips every time).
PERSIST_SPIN_IDS = ["W", "H", "Cols", "MinGrid", "Length", "CropW", "CropH"]
PERSIST_DOUBLESPIN_IDS = ["Gap"]
PERSIST_CHECKBOX_IDS = ["Recursive", "Replace", "Fill"]
PERSIST_COMBO_LENGTHS = {
    "Preset": len(RES_PRESETS), "GapUnit": len(GAP_UNITS), "Outer": len(OUTER_MODES),
    "Anchor": len(ANCHOR_MODES), "Order": len(ORDER_MODES),
    "TrackColor": len(TRACK_COLOR_MODES), "LenMode": len(LENGTH_MODES),
    "AspectMode": len(ASPECT_MODES), "CropBasis": len(CROP_BASIS_MODES),
    "Fps": len(FPS_OPTIONS),
}


def load_state_file():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state_file(d):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass  # persistence is a convenience, never worth failing the build over


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
def run_gui():
    resolve = get_resolve()
    bmd = get_bmd()
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        print("%s: open a project first." % SCRIPT_TITLE)
        return
    mp = project.GetMediaPool()
    folders = list_folders(mp.GetRootFolder())

    fusion = resolve.Fusion()
    ui = fusion.UIManager
    disp = bmd.UIDispatcher(ui)

    L = 190  # label column width (widened for the larger font below)

    def row(label, *widgets):
        return ui.HGroup({"Weight": 0}, [ui.Label({"Text": label, "MinimumSize": [L, 0],
                                                   "MaximumSize": [L, 1000], "Weight": 0})]
                         + list(widgets))

    win = disp.AddWindow(
        {"ID": "GridWin", "WindowTitle": "%s v%s" % (SCRIPT_TITLE, VERSION),
         "Geometry": [200, 150, 800, 900],
         "StyleSheet": "* { font-size: 13px; }"},
        ui.VGroup({"Spacing": 6}, [
            ui.Label({"Text": "<b>Source</b>", "Weight": 0}),
            row("Bin", ui.ComboBox({"ID": "Bin"})),
            row("", ui.CheckBox({"ID": "Recursive", "Text": "Include subfolders", "Checked": False})),
            row("Resolution filter", ui.ComboBox({"ID": "ResFilter"})),
            ui.Label({"ID": "BinInfo", "Text": "", "Weight": 0, "WordWrap": True}),

            ui.Label({"Text": "<b>Timeline</b>", "Weight": 0}),
            row("Name", ui.LineEdit({"ID": "TlName", "Text": "GRID"})),
            row("", ui.CheckBox({"ID": "Replace", "Text": "Replace timeline with the same name",
                                 "Checked": True})),
            row("Preset", ui.ComboBox({"ID": "Preset"})),
            row("Width / Height",
                ui.SpinBox({"ID": "W", "Minimum": 16, "Maximum": 16384, "Value": 2160}),
                ui.SpinBox({"ID": "H", "Minimum": 16, "Maximum": 16384, "Value": 2160})),
            row("Frame rate", ui.ComboBox({"ID": "Fps"})),

            ui.Label({"Text": "<b>Grid</b>", "Weight": 0}),
            row("Gap",
                ui.DoubleSpinBox({"ID": "Gap", "Minimum": 0.0, "Maximum": 10000.0,
                                  "Decimals": 2, "Value": 2.0, "SingleStep": 1.0}),
                ui.ComboBox({"ID": "GapUnit"})),
            row("Outer margin", ui.ComboBox({"ID": "Outer"})),
            row("Columns (0 = auto)",
                ui.SpinBox({"ID": "Cols", "Minimum": 0, "Maximum": 200, "Value": 0})),
            row("Minimum grid (N x N)",
                ui.SpinBox({"ID": "MinGrid", "Minimum": 1, "Maximum": 50, "Value": 3})),
            row("Vertical anchor", ui.ComboBox({"ID": "Anchor"})),
            row("Order", ui.ComboBox({"ID": "Order"})),
            row("Track color", ui.ComboBox({"ID": "TrackColor"})),
            row("", ui.CheckBox({"ID": "Fill", "Text": "Fill empty space with random shots "
                                 "(forces top anchor)", "Checked": False})),
            row("Aspect handling", ui.ComboBox({"ID": "AspectMode"})),
            row("Crop basis", ui.ComboBox({"ID": "CropBasis"})),
            row("Custom crop W / H",
                ui.SpinBox({"ID": "CropW", "Minimum": 1, "Maximum": 16384, "Value": 16}),
                ui.SpinBox({"ID": "CropH", "Minimum": 1, "Maximum": 16384, "Value": 9})),

            ui.Label({"Text": "<b>Time</b>", "Weight": 0}),
            row("Shorter clips", ui.ComboBox({"ID": "LenMode"})),
            row("Length (0 = longest)",
                ui.SpinBox({"ID": "Length", "Minimum": 0, "Maximum": 100000, "Value": 0})),

            ui.Label({"ID": "Preview", "Text": "", "Weight": 0, "WordWrap": True}),
            ui.TextEdit({"ID": "Log", "ReadOnly": True, "Weight": 1}),
            ui.HGroup({"Weight": 0}, [
                ui.Button({"ID": "Build", "Text": "Build timeline"}),
                ui.Button({"ID": "Close", "Text": "Close"}),
            ]),
        ]),
    )
    itm = win.GetItems()

    itm["Bin"].AddItems([p for p, _ in folders])
    default_bin = next((i for i, (p, _) in enumerate(folders) if p.endswith("/IN")), 0)
    itm["Bin"].CurrentIndex = default_bin
    itm["Preset"].AddItems([p for p, _ in RES_PRESETS])
    itm["Preset"].CurrentIndex = 1
    itm["GapUnit"].AddItems(GAP_UNITS)
    itm["GapUnit"].CurrentIndex = 1        # default: % of timeline width
    itm["Outer"].AddItems(OUTER_MODES)
    itm["Anchor"].AddItems(ANCHOR_MODES)
    itm["Order"].AddItems(ORDER_MODES)
    itm["LenMode"].AddItems(LENGTH_MODES)
    itm["LenMode"].CurrentIndex = 1        # default: Bounce (ping-pong)
    itm["TrackColor"].AddItems(TRACK_COLOR_MODES)
    itm["TrackColor"].CurrentIndex = 1     # default: Cycle palette
    itm["AspectMode"].AddItems(ASPECT_MODES)
    itm["CropBasis"].AddItems(CROP_BASIS_MODES)
    itm["Fps"].AddItems(FPS_OPTIONS)

    state = {"clips": [], "auto_name": ""}

    def log(msg):
        itm["Log"].PlainText = (itm["Log"].PlainText + "\n" + msg).lstrip("\n")

    def current_folder():
        return folders[itm["Bin"].CurrentIndex][1]

    def auto_timeline_name():
        bin_name = sanitize_name(current_folder().GetName())
        return "%s_grid_%dx%d" % (bin_name, int(itm["W"].Value), int(itm["H"].Value))

    def maybe_update_name(ev=None):
        # Only overwrite the Name field if it still holds our last auto value
        # (or is empty / the original "GRID" placeholder) - never clobber a manual edit.
        new_auto = auto_timeline_name()
        if itm["TlName"].Text.strip() in ("", "GRID", state["auto_name"]):
            itm["TlName"].Text = new_auto
        state["auto_name"] = new_auto

    def update_aspect_controls(ev=None):
        crop_mode = itm["AspectMode"].CurrentIndex == 1
        itm["CropBasis"].Enabled = crop_mode
        custom = crop_mode and itm["CropBasis"].CurrentIndex == 2
        itm["CropW"].Enabled = custom
        itm["CropH"].Enabled = custom

    def gather_state_for_save():
        d = {wid: int(itm[wid].Value) for wid in PERSIST_SPIN_IDS}
        for wid in PERSIST_DOUBLESPIN_IDS:
            d[wid] = float(itm[wid].Value)
        for wid in PERSIST_CHECKBOX_IDS:
            d[wid] = bool(itm[wid].Checked)
        for wid in PERSIST_COMBO_LENGTHS:
            d[wid] = int(itm[wid].CurrentIndex)
        d["bin_path"] = folders[itm["Bin"].CurrentIndex][0] if folders else ""
        d["last_timeline_name"] = itm["TlName"].Text
        return d

    def apply_saved_state(d):
        if not d:
            return
        for wid in PERSIST_SPIN_IDS:
            if wid in d:
                try:
                    itm[wid].Value = int(d[wid])
                except Exception:
                    pass
        for wid in PERSIST_DOUBLESPIN_IDS:
            if wid in d:
                try:
                    itm[wid].Value = float(d[wid])
                except Exception:
                    pass
        for wid in PERSIST_CHECKBOX_IDS:
            if wid in d:
                itm[wid].Checked = bool(d[wid])
        for wid, count in PERSIST_COMBO_LENGTHS.items():
            if wid in d:
                idx = int(d[wid])
                if 0 <= idx < count:
                    itm[wid].CurrentIndex = idx
        bin_path = d.get("bin_path")
        if bin_path:
            match = next((i for i, (p, _) in enumerate(folders) if p == bin_path), None)
            if match is not None:
                itm["Bin"].CurrentIndex = match
        # Restored as-is, NOT recorded into state["auto_name"] - this makes
        # maybe_update_name() treat it exactly like a manual edit (protected from
        # being overwritten by a later bin/resolution change), which is the point:
        # reopening the GUI and rebuilding with different params still targets the
        # same timeline name.
        last_name = d.get("last_timeline_name")
        if last_name:
            itm["TlName"].Text = last_name

    def persist_state(ev=None):
        save_state_file(gather_state_for_save())

    def filtered_clips():
        f = itm["ResFilter"].CurrentText
        if not f or f.startswith(ALL_RES):
            return state["clips"]
        key = f.split(" ")[0]
        return [c for c in state["clips"] if "%dx%d" % parse_res(c) == key]

    def gather_cfg():
        f = itm["ResFilter"].CurrentText or ""
        return {
            "folder": current_folder(),
            "recursive": bool(itm["Recursive"].Checked),
            "res_filter": None if (not f or f.startswith(ALL_RES)) else f.split(" ")[0],
            "timeline_name": (itm["TlName"].Text or "GRID").strip(),
            "replace": bool(itm["Replace"].Checked),
            "W": int(itm["W"].Value), "H": int(itm["H"].Value),
            "gap_value": float(itm["Gap"].Value), "gap_unit": int(itm["GapUnit"].CurrentIndex),
            "outer_mode": int(itm["Outer"].CurrentIndex),
            "force_cols": int(itm["Cols"].Value), "min_grid": int(itm["MinGrid"].Value),
            "anchor": "top" if itm["Anchor"].CurrentIndex == 0 else "center",
            "order": ["name", "random", "tc"][itm["Order"].CurrentIndex],
            "length_mode": ["loop", "bounce", "none"][itm["LenMode"].CurrentIndex],
            "custom_length": int(itm["Length"].Value),
            "fill_random": bool(itm["Fill"].Checked),
            "seed": None,
            "track_color": ["none", "cycle", "random"][itm["TrackColor"].CurrentIndex],
            "aspect_mode": "crop" if itm["AspectMode"].CurrentIndex == 1 else "fit",
            "crop_basis": ["dominant", "timeline", "custom"][itm["CropBasis"].CurrentIndex],
            "crop_w": int(itm["CropW"].Value),
            "crop_h": int(itm["CropH"].Value),
            "fps": FPS_OPTIONS[itm["Fps"].CurrentIndex] if itm["Fps"].CurrentIndex > 0 else None,
        }

    def update_preview(ev=None):
        clips = filtered_clips()
        if not clips:
            itm["Preview"].Text = "No usable clips."
            return
        cfg = gather_cfg()
        W, H = cfg["W"], cfg["H"]
        gap = {0: cfg["gap_value"], 1: W * cfg["gap_value"] / 100.0,
               2: H * cfg["gap_value"] / 100.0}[cfg["gap_unit"]]
        outer = {0: gap / 2.0, 1: gap, 2: 0.0}[cfg["outer_mode"]]
        aspect = resolve_target_aspect(cfg, clips, W, H)
        try:
            lay = solve_layout(len(clips), W, H, aspect, gap, outer,
                               cfg["min_grid"], cfg["force_cols"])
        except ValueError as e:
            itm["Preview"].Text = "Layout error: %s" % e
            return
        length = cfg["custom_length"] or max(clip_frames(c) for c in clips)
        itm["Preview"].Text = (
            "Preview: %d clips -> %d x %d grid, tile %.1f x %.1f px, gap %.1f px, "
            "outer %.1f px, used height %.0f / %d, length %d fr"
            % (len(clips), lay["cols"], lay["rows"], lay["box_w"], lay["box_h"], gap, outer,
               lay["grid_h"], H, length))

    def refresh_bin(ev=None):
        state["clips"] = usable_clips(current_folder(), bool(itm["Recursive"].Checked))
        summary = resolution_summary(state["clips"])
        itm["ResFilter"].Clear()
        itm["ResFilter"].AddItem("%s (%d)" % (ALL_RES, len(state["clips"])))
        itm["ResFilter"].AddItems(["%s (%d)" % (k, v) for k, v in summary])
        if len(summary) > 1:
            itm["ResFilter"].CurrentIndex = 1   # default: most common resolution
            itm["BinInfo"].Text = ("Mixed resolutions found. Mixed aspect ratios are "
                                   "letterboxed inside equal cells.")
        else:
            itm["BinInfo"].Text = ""
        maybe_update_name()
        update_preview()

    def on_preset(ev=None):
        val = RES_PRESETS[itm["Preset"].CurrentIndex][1]
        if val:
            itm["W"].Value, itm["H"].Value = val
        maybe_update_name()
        update_preview()

    def on_dim_changed(ev=None):
        maybe_update_name()
        update_preview()

    def on_build(ev=None):
        itm["Log"].PlainText = ""
        itm["Build"].Enabled = False
        try:
            res = build_grid(resolve, gather_cfg(), log)
            log("Done: %s" % res["timeline"])
            persist_state()
        except Exception as e:
            import traceback
            log("ERROR: %s" % e)
            log(traceback.format_exc())
        finally:
            itm["Build"].Enabled = True

    def on_close(ev=None):
        persist_state()
        disp.ExitLoop()

    win.On.Bin.CurrentIndexChanged = refresh_bin
    win.On.Recursive.Clicked = refresh_bin
    win.On.ResFilter.CurrentIndexChanged = update_preview
    win.On.Preset.CurrentIndexChanged = on_preset
    win.On.W.ValueChanged = on_dim_changed
    win.On.H.ValueChanged = on_dim_changed
    for wid in ("Cols", "MinGrid", "Length", "CropW", "CropH"):
        getattr(win.On, wid).ValueChanged = update_preview
    win.On.Gap.ValueChanged = update_preview
    for wid in ("GapUnit", "Outer", "LenMode"):
        getattr(win.On, wid).CurrentIndexChanged = update_preview
    win.On.AspectMode.CurrentIndexChanged = lambda ev=None: (update_aspect_controls(), update_preview())
    win.On.CropBasis.CurrentIndexChanged = lambda ev=None: (update_aspect_controls(), update_preview())
    win.On.Build.Clicked = on_build
    win.On.Close.Clicked = on_close
    win.On.GridWin.Close = on_close

    update_aspect_controls()
    apply_saved_state(load_state_file())
    update_aspect_controls()   # re-sync enabled states in case restored state changed them
    refresh_bin()
    win.Show()
    disp.RunLoop()
    win.Hide()


if not globals().get("GRID_NO_GUI"):
    run_gui()
