#!/usr/bin/env python3
"""
XML Scale Converter (Resolve native UI)  -  Premiere/FCP7 XML  ->  Resolve-friendly XML

Runs inside DaVinci Resolve via UIManager. No PySide6.
Install: Resolve scripts folder -> Scripts/Utility/XmlScaleConverter_Resolve.py
Run:     Workspace > Scripts > XmlScaleConverter_Resolve

Math (per clip, source WxH, timeline TWxTH):
    fill_factor = max(TW/W, TH/H)
    mode_fit    = Fill: max(TW/W, TH/H) | Fit: min(TW/W, TH/H) | None: 1.0
    clips whose source == reference source:
        scale_new = scale_old * target_base / original_base
        (target_base auto = fill_factor / mode_fit * 100)
    clips with any other source (stills, proxies, ...):
        scale_new = scale_old / (fill_factor*100) * (fill_factor / mode_fit * 100)
    position (Resolve px)  X = horiz*TW, Y = -vert*TH
        position_new = position_old * position_factor   (auto = 1 / mode_fit)
    -> Fill mode, 4608x3164 into 1920x1080: factor 2.4 (verified against offline)
    -> Fit / None factors are extrapolated from the same rule, verify on a clip.
"""
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ----------------------------------------------------------------------------------------
# Core (unchanged)
# ----------------------------------------------------------------------------------------

MODES = [
    ("Scale full frame with crop (Fill)", "fill", "_FILL"),
    ("Scale entire image to fit (Fit)", "fit", "_FIT"),
    ("Center crop with no resizing (None)", "none", "_NATIVE"),
]


@dataclass
class Settings:
    tl_w: Optional[int] = None            # None -> auto from XML
    tl_h: Optional[int] = None
    src_w: Optional[int] = None           # None -> auto (most common source res in XML)
    src_h: Optional[int] = None
    orig_base: float = 42.0               # scale in XML that means "fills the frame"
    target_base: Optional[float] = None   # None -> auto from mode
    mode: str = "fill"
    convert_pos: bool = True
    pos_factor: Optional[float] = None    # None -> auto (1 / mode_fit)


def mode_fit(mode, sw, sh, tw, th):
    if mode == "fill":
        return max(tw / sw, th / sh)
    if mode == "fit":
        return min(tw / sw, th / sh)
    return 1.0


def fmt_scale(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def fmt_pos(v):
    if v == 0:
        return "0"
    return "%.7g" % v


def parse_xml_info(txt):
    m = re.search(r"<sequence\b.*?<format>.*?<width>(\d+)</width>\s*<height>(\d+)</height>", txt, re.S)
    tl = (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)
    dims = {}
    for fm in re.finditer(r'<file id="(file-\d+)">(.*?)</file>', txt, re.S):
        w = re.search(r"<width>(\d+)</width>", fm.group(2))
        h = re.search(r"<height>(\d+)</height>", fm.group(2))
        if w and h:
            dims[fm.group(1)] = (int(w.group(1)), int(h.group(1)))
    ref = Counter(dims.values()).most_common(1)[0][0] if dims else (1920, 1080)
    return {"tl": tl, "dims": dims, "ref": ref}


def process_xml(txt, st, overrides=None):
    """Returns (new_text, rows, info). overrides: {clipitem_id: (X_px, Y_px)} in Resolve convention."""
    overrides = overrides or {}
    info = parse_xml_info(txt)
    tw, th = (st.tl_w, st.tl_h) if (st.tl_w and st.tl_h) else info["tl"]
    ref = (st.src_w, st.src_h) if (st.src_w and st.src_h) else info["ref"]
    dims = info["dims"]
    info = dict(info, tl=(tw, th), ref=ref)

    audio_pos = txt.find("<numOutputChannels>")
    track_pos = [m.start() for m in re.finditer(r"<track\b", txt)]
    rows = []
    warns = []

    ref_fill = max(tw / ref[0], th / ref[1])
    ref_mf = mode_fit(st.mode, ref[0], ref[1], tw, th)
    info["auto_target"] = st.orig_base if st.mode == "none" else ref_fill / ref_mf * 100.0
    info["auto_pos"] = 1.0 / ref_mf
    info["fill_factor"] = ref_fill

    def fix_clip(m):
        clip = m.group(0)
        cid = re.search(r'<clipitem id="(clipitem-\d+)"', clip).group(1)
        fm = re.search(r'<file id="(file-\d+)"', clip)
        if not fm or fm.group(1) not in dims or "<name>Basic Motion</name>" not in clip:
            return clip
        sw, sh = dims[fm.group(1)]
        name = re.search(r"<name>(.*?)</name>", clip).group(1)

        fillf = max(tw / sw, th / sh)
        mf = mode_fit(st.mode, sw, sh, tw, th)
        auto_target = fillf / mf * 100.0
        if (sw, sh) == ref:
            base = st.orig_base
            target = auto_target if st.target_base is None else st.target_base
        else:
            base = fillf * 100.0
            target = auto_target
        smul = 1.0 if (st.mode == "none" and st.target_base is None) else target / base

        if not st.convert_pos:
            pfac = 1.0
        elif st.pos_factor is not None:
            pfac = st.pos_factor
        else:
            pfac = 1.0 / mf

        row = {"cid": cid, "name": name, "src": (sw, sh), "s_old": None, "s_new": None,
               "p_old": (0.0, 0.0), "p_new": (0.0, 0.0), "manual": False, "kf": False}

        # ---- scale (base value + keyframes)
        def fix_scale(pm):
            def fix_val(vm):
                old = float(vm.group(2))
                new = old * smul
                if row["s_old"] is None:
                    row["s_old"], row["s_new"] = old, new
                return vm.group(1) + fmt_scale(new) + vm.group(3)
            return re.sub(r"(<value>)([-\d.eE]+)(</value>)", fix_val, pm.group(0))

        clip = re.sub(
            r'<parameter authoringApp="PremierePro">\s*<parameterid>scale</parameterid>.*?</parameter>',
            fix_scale, clip, flags=re.S)

        # ---- anchor point warning
        am = re.search(r"<parameterid>centerOffset</parameterid>.*?</parameter>", clip, re.S)
        if am:
            ah = re.search(r"<horiz>([-\d.eE]+)</horiz>", am.group(0))
            av = re.search(r"<vert>([-\d.eE]+)</vert>", am.group(0))
            if (ah and float(ah.group(1)) != 0) or (av and float(av.group(1)) != 0):
                warns.append("%s (%s): anchor point is non-zero, not converted" % (cid, name))

        # ---- position (center)
        def fix_center(pm):
            block = pm.group(0)
            h0 = float(re.search(r"<horiz>([-\d.eE]+)</horiz>", block).group(1))
            v0 = float(re.search(r"<vert>([-\d.eE]+)</vert>", block).group(1))
            row["p_old"] = (h0 * tw + 0.0, -v0 * th + 0.0)
            has_kf = "<keyframe>" in block
            row["kf"] = has_kf
            if cid in overrides and not has_kf:
                x, y = overrides[cid]
                row["manual"] = True
                row["p_new"] = (x, y)
                block = re.sub(r"<horiz>[-\d.eE]+</horiz>", "<horiz>%s</horiz>" % fmt_pos(x / tw), block)
                block = re.sub(r"<vert>[-\d.eE]+</vert>", "<vert>%s</vert>" % fmt_pos(-y / th), block)
                return block
            row["p_new"] = (h0 * tw * pfac + 0.0, -v0 * th * pfac + 0.0)
            block = re.sub(r"<horiz>([-\d.eE]+)</horiz>",
                           lambda mm: "<horiz>%s</horiz>" % fmt_pos(float(mm.group(1)) * pfac), block)
            block = re.sub(r"<vert>([-\d.eE]+)</vert>",
                           lambda mm: "<vert>%s</vert>" % fmt_pos(float(mm.group(1)) * pfac), block)
            return block

        clip = re.sub(
            r'<parameter authoringApp="PremierePro">\s*<parameterid>center</parameterid>.*?</parameter>',
            fix_center, clip, flags=re.S)

        # video track index (1-based) from <track> tags preceding this clip, before audio section
        vt = sum(1 for p in track_pos if p < m.start() and (audio_pos < 0 or p < audio_pos))
        row["vtrack"] = vt
        row["n"] = len(rows) + 1
        rows.append(row)
        return clip

    out = re.sub(r'<clipitem id="clipitem-\d+">.*?</clipitem>', fix_clip, txt, flags=re.S)
    info["warns"] = warns
    return out, rows, info


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, txt):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt)


# ----------------------------------------------------------------------------------------
# Resolve UIManager bootstrap
# ----------------------------------------------------------------------------------------

def get_ui():
    """Returns (fusion, ui, dispatcher). Uses injected globals inside Resolve, else external scripting."""
    try:
        _fu = fu          # noqa: F821  (injected by Resolve)
        _bmd = bmd        # noqa: F821
        ui = _fu.UIManager
        return _fu, ui, _bmd.UIDispatcher(ui)
    except NameError:
        pass
    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        print("Run this script from Resolve: Workspace > Scripts (or set up DaVinciResolveScript for external use).")
        sys.exit(1)
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        print("Cannot connect to Resolve. Is it running with external scripting enabled (Studio)?")
        sys.exit(1)
    _fu = resolve.Fusion()
    ui = _fu.UIManager
    return _fu, ui, dvr.UIDispatcher(ui)


# ----------------------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------------------
OUT_FOLDER_NAME = "fixed"
DEFAULT_SUFFIX = "_fixed"


class SettingsManager:
    def __init__(self):
        docs_path = Path.home() / "Documents" / "XMLScaleConverter"
        try:
            docs_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.settings_file = docs_path / "settings.json"
        self.default_settings = {
            "last_dir": "",
            "mode_index": 0,
            "tl_auto": True, "tl_w": 1920, "tl_h": 1080,
            "src_auto": True, "src_w": 4608, "src_h": 3164,
            "orig_base": 42.0,
            "target_auto": True, "target_value": 100.0,
            "pos_convert": True, "pos_auto": True, "pos_value": 2.4,
            "suffix": "_fixed",
            "out_dir": "",
            "settings_version": 2,
        }

    def load_settings(self):
        try:
            if self.settings_file.exists():
                with open(self.settings_file, "r") as f:
                    loaded = json.load(f)
                merged = {**self.default_settings, **loaded}
                if loaded.get("settings_version", 1) < 2:
                    merged["suffix"] = self.default_settings["suffix"]
                    merged["settings_version"] = 2
                return merged
        except Exception as e:
            print("Failed to load settings: %s" % e)
        return dict(self.default_settings)

    def save_settings(self, settings):
        try:
            with open(self.settings_file, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print("Failed to save settings: %s" % e)


# ----------------------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------------------
COLS = ["#", "V", "Clip ID", "Name", "Source", "Scale old", "Scale new",
        "Pos X old", "Pos Y old", "Pos X new", "Pos Y new"]
COL_W = [40, 40, 90, 260, 90, 80, 80, 90, 90, 90, 90]
NEW_COLS = (6, 9, 10)

WIN_X, WIN_Y, WIN_W, WIN_H = 60, 40, 1700, 1100
LEFT_W = 450

CSS_TITLE = "font-size: 22px; font-weight: bold; color: #4376A1;"
CSS_SECTION = "font-size: 13px; font-weight: bold; color: #ffffff; padding-top: 8px;"
CSS_STATUS = {
    "info": "color: #0C0C0C; background: #2196F3; border-radius: 4px; padding: 8px;",
    "success": "color: #0C0C0C; background: #4376A1; border-radius: 4px; padding: 8px;",
    "warning": "color: #0C0C0C; background: #ff9800; border-radius: 4px; padding: 8px;",
    "error": "color: #ffffff; background: #f44336; border-radius: 4px; padding: 8px;",
}
CSS_PRIMARY = "background: #4376A1; color: #0C0C0C; font-weight: bold; border-radius: 4px; min-height: 34px;"
COLOR_NEW = {"R": 0.59, "G": 1.0, "B": 0.59, "A": 1.0}
COLOR_MANUAL = {"R": 1.0, "G": 0.6, "B": 0.0, "A": 1.0}

BIG = 16777215


class App:
    def __init__(self):
        self.fusion, self.ui, self.disp = get_ui()
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load_settings()
        self.texts = {}        # path -> xml text
        self.overrides = {}    # path -> {clipitem id: (x, y)} in Resolve px
        self.paths = []        # ordered list of loaded paths
        self.rows = []         # rows of the currently previewed file
        self.building = True
        self.win = self.build_window()
        self.it = self.win.GetItems()
        self.setup_widgets()
        self.bind_events()
        self.load_ui_from_settings()
        self.building = False
        self.on_toggles()

    # ------------------------------------------------------------ layout
    def build_window(self):
        ui = self.ui

        def section(text):
            return ui.Label({"Text": text, "Weight": 0, "StyleSheet": CSS_SECTION})

        def label(text):
            return ui.Label({"Text": text, "Weight": 0})

        def spin(id_, lo, hi, val=0):
            return ui.SpinBox({"ID": id_, "Minimum": lo, "Maximum": hi, "Value": val,
                               "Events": {"ValueChanged": True}})

        def dspin(id_, dec, lo, hi, val=0.0, step=1.0, tip=""):
            return ui.DoubleSpinBox({"ID": id_, "Decimals": dec, "Minimum": lo, "Maximum": hi,
                                     "Value": val, "SingleStep": step, "ToolTip": tip,
                                     "Events": {"ValueChanged": True}})

        def check(id_, text):
            return ui.CheckBox({"ID": id_, "Text": text, "Weight": 0, "Events": {"Clicked": True}})

        # ---------------- left column: controls
        left = ui.VGroup({"Weight": 0, "MinimumSize": [LEFT_W, 0], "MaximumSize": [LEFT_W, BIG]}, [
            section("Resolve Setup"),
            label("Input Scaling:"),
            ui.ComboBox({"ID": "Mode", "Weight": 0, "Events": {"CurrentIndexChanged": True}}),
            label("Timeline resolution:"),
            check("TlAuto", "Auto from XML"),
            ui.HGroup({"Weight": 0}, [spin("TlW", 1, 32768, 1920), ui.Label({"Text": "x", "Weight": 0}),
                                      spin("TlH", 1, 32768, 1080)]),
            label("Source resolution (clips the base scale applies to):"),
            check("SrcAuto", "Auto (most common in XML)"),
            ui.HGroup({"Weight": 0}, [spin("SrcW", 1, 65536, 4608), ui.Label({"Text": "x", "Weight": 0}),
                                      spin("SrcH", 1, 65536, 3164)]),

            section("Scale"),
            label("Original scale in XML (%):"),
            dspin("Orig", 4, 0.0001, 100000, 42.0, 1.0,
                  "Scale value in the XML that means 'image fills the frame' (e.g. 42 for 0.420)."),
            label("Target scale (%):"),
            check("TargetAuto", "Auto from mode"),
            dspin("Target", 4, 0.0001, 100000, 100.0, 1.0,
                  "Scale the 'fills the frame' look should have in Resolve (100 for Fill)."),

            section("Position"),
            check("PosConvert", "Convert position"),
            check("PosAuto", "Auto factor (1 / Resolve fit factor)"),
            dspin("Pos", 6, 0.000001, 1000, 2.4, 0.1, "Multiplier applied to the XML position values."),

            section("Output"),
            label("Output folder:"),
            ui.HGroup({"Weight": 0}, [
                ui.LineEdit({"ID": "OutDir", "PlaceholderText":
                             "Default: '%s' folder next to each source XML" % OUT_FOLDER_NAME}),
                ui.Button({"ID": "OutBrowse", "Text": "Browse", "Weight": 0}),
            ]),
            label("File name suffix:"),
            ui.LineEdit({"ID": "Suffix", "Weight": 0,
                         "PlaceholderText": "e.g. _fixed (empty = same file name)"}),

            ui.VGap(8),
            ui.Label({"ID": "Status", "Text": "No XML loaded", "Weight": 0, "WordWrap": True,
                      "StyleSheet": CSS_STATUS["info"]}),
            ui.Button({"ID": "Process", "Text": "PROCESS ALL FILES", "Weight": 0,
                       "StyleSheet": CSS_PRIMARY}),
            ui.VGap(0, 1),
        ])

        # ---------------- right column: clip table + manual position + log
        right = ui.VGroup({"Weight": 1}, [
            ui.Label({"Text": "Clips", "Weight": 0, "StyleSheet": CSS_SECTION}),
            ui.Label({"ID": "Info", "Text": "", "Weight": 0, "WordWrap": True}),
            ui.Tree({"ID": "Table", "Weight": 1, "ColumnCount": len(COLS), "AlternatingRowColors": True,
                     "SortingEnabled": False, "UniformRowHeights": True,
                     "Events": {"CurrentItemChanged": True, "ItemClicked": True}}),
            ui.Label({"Text": "Manual position for selected clip (Resolve px, Y up):", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "X", "Weight": 0}),
                dspin("ManX", 3, -100000, 100000, 0.0, 1.0),
                ui.Label({"Text": "Y", "Weight": 0}),
                dspin("ManY", 3, -100000, 100000, 0.0, 1.0),
                ui.Button({"ID": "ManSet", "Text": "Set", "Weight": 0}),
                ui.Button({"ID": "ManClear", "Text": "Clear clip", "Weight": 0}),
                ui.Button({"ID": "ManClearAll", "Text": "Clear all (selected file)", "Weight": 0}),
            ]),
            ui.Label({"Text": "Log", "Weight": 0, "StyleSheet": CSS_SECTION}),
            ui.TextEdit({"ID": "Log", "ReadOnly": True, "Weight": 0, "MinimumSize": [0, 120],
                         "MaximumSize": [BIG, 180], "Font": ui.Font({"Family": "Courier New", "PixelSize": 12})}),
        ])

        # ---------------- top: title + files
        top = ui.VGroup({"Weight": 0}, [
            ui.Label({"Text": "XMLScaleConverter", "Weight": 0, "StyleSheet": CSS_TITLE}),
            ui.Label({"Text": "XML Files", "Weight": 0, "StyleSheet": CSS_SECTION}),
            ui.Tree({"ID": "Files", "Weight": 0, "ColumnCount": 2, "HeaderHidden": True,
                     "MinimumSize": [0, 70], "MaximumSize": [BIG, 100],
                     "Events": {"CurrentItemChanged": True}}),
            ui.HGroup({"Weight": 0}, [
                ui.Button({"ID": "Add", "Text": "Add"}),
                ui.Button({"ID": "AddDir", "Text": "Add Folder"}),
                ui.Button({"ID": "Remove", "Text": "Remove"}),
                ui.Button({"ID": "Clear", "Text": "Clear"}),
            ]),
        ])

        return self.disp.AddWindow({
            "ID": "XSC",
            "WindowTitle": "XMLScaleConverter v1.1",
            "Geometry": [WIN_X, WIN_Y, WIN_W, WIN_H],
            "Spacing": 10,
        }, [
            ui.VGroup({"Spacing": 8}, [
                top,
                ui.HGroup({"Weight": 1, "Spacing": 20}, [left, right]),
            ])
        ])

    def setup_widgets(self):
        it = self.it
        it["Mode"].AddItems([m[0] for m in MODES])

        hdr = it["Table"].NewItem()
        for i, c in enumerate(COLS):
            hdr.Text[i] = c
        it["Table"].SetHeaderItem(hdr)
        for i, w in enumerate(COL_W):
            it["Table"].ColumnWidth[i] = w

        fh = it["Files"].NewItem()
        fh.Text[0] = "File"
        fh.Text[1] = "#"
        it["Files"].SetHeaderItem(fh)
        it["Files"].ColumnWidth[0] = 1400
        it["Files"].ColumnWidth[1] = 40

    def bind_events(self):
        w = self.win
        on = w.On
        on.XSC.Close = lambda ev: self.on_close()

        on.Add.Clicked = lambda ev: self.on_add()
        on.AddDir.Clicked = lambda ev: self.on_add_dir()
        on.Remove.Clicked = lambda ev: self.on_remove()
        on.Clear.Clicked = lambda ev: self.on_clear()
        on.OutBrowse.Clicked = lambda ev: self.on_pick_out()
        on.Process.Clicked = lambda ev: self.on_process()
        on.ManSet.Clicked = lambda ev: self.on_manual_set()
        on.ManClear.Clicked = lambda ev: self.on_manual_clear()
        on.ManClearAll.Clicked = lambda ev: self.on_clear_overrides()

        on.Files.CurrentItemChanged = lambda ev: self.refresh()
        on.Table.CurrentItemChanged = lambda ev: self.on_row_selected()

        for cid in ("TlAuto", "SrcAuto", "TargetAuto", "PosConvert", "PosAuto"):
            getattr(on, cid).Clicked = lambda ev: self.on_toggles()
        for sid in ("TlW", "TlH", "SrcW", "SrcH", "Orig", "Target", "Pos"):
            getattr(on, sid).ValueChanged = lambda ev: self.refresh()
        on.Mode.CurrentIndexChanged = lambda ev: self.refresh()

    # ------------------------------------------------------------ settings persistence
    def load_ui_from_settings(self):
        s, it = self.settings, self.it
        it["Mode"].CurrentIndex = max(0, min(int(s["mode_index"]), len(MODES) - 1))
        it["TlAuto"].Checked = bool(s["tl_auto"])
        it["TlW"].Value = int(s["tl_w"])
        it["TlH"].Value = int(s["tl_h"])
        it["SrcAuto"].Checked = bool(s["src_auto"])
        it["SrcW"].Value = int(s["src_w"])
        it["SrcH"].Value = int(s["src_h"])
        it["Orig"].Value = float(s["orig_base"])
        it["TargetAuto"].Checked = bool(s["target_auto"])
        it["Target"].Value = float(s["target_value"])
        it["PosConvert"].Checked = bool(s["pos_convert"])
        it["PosAuto"].Checked = bool(s["pos_auto"])
        it["Pos"].Value = float(s["pos_value"])
        it["Suffix"].Text = s["suffix"]
        it["OutDir"].Text = s["out_dir"]

    def save_current_settings(self):
        s, it = self.settings, self.it
        s["mode_index"] = int(it["Mode"].CurrentIndex)
        s["tl_auto"] = bool(it["TlAuto"].Checked)
        s["src_auto"] = bool(it["SrcAuto"].Checked)
        if not it["TlAuto"].Checked:
            s["tl_w"], s["tl_h"] = int(it["TlW"].Value), int(it["TlH"].Value)
        if not it["SrcAuto"].Checked:
            s["src_w"], s["src_h"] = int(it["SrcW"].Value), int(it["SrcH"].Value)
        s["orig_base"] = float(it["Orig"].Value)
        s["target_auto"] = bool(it["TargetAuto"].Checked)
        if not it["TargetAuto"].Checked:
            s["target_value"] = float(it["Target"].Value)
        s["pos_convert"] = bool(it["PosConvert"].Checked)
        s["pos_auto"] = bool(it["PosAuto"].Checked)
        if not it["PosAuto"].Checked:
            s["pos_value"] = float(it["Pos"].Value)
        s["suffix"] = it["Suffix"].Text
        s["out_dir"] = it["OutDir"].Text.strip()
        self.settings_manager.save_settings(s)

    def on_close(self):
        try:
            self.save_current_settings()
        except Exception as e:
            print("Failed to save settings: %s" % e)
        self.disp.ExitLoop()

    # ------------------------------------------------------------ helpers
    def set_status(self, text, kind):
        self.it["Status"].Text = text
        self.it["Status"].StyleSheet = CSS_STATUS[kind]

    def say(self, msg):
        try:
            self.it["Log"].Append(msg)
        except Exception:
            self.it["Log"].PlainText = (self.it["Log"].PlainText or "") + msg + "\n"
        print(msg)

    def current_path(self):
        cur = self.it["Files"].CurrentItem()
        if cur is not None:
            try:
                idx = int(cur.Text[1])
                if 0 <= idx < len(self.paths):
                    return self.paths[idx]
            except Exception:
                pass
        return self.paths[0] if self.paths else None

    def conv_settings(self):
        it = self.it
        st = Settings()
        if not it["TlAuto"].Checked:
            st.tl_w, st.tl_h = int(it["TlW"].Value), int(it["TlH"].Value)
        if not it["SrcAuto"].Checked:
            st.src_w, st.src_h = int(it["SrcW"].Value), int(it["SrcH"].Value)
        st.orig_base = float(it["Orig"].Value)
        st.target_base = None if it["TargetAuto"].Checked else float(it["Target"].Value)
        st.mode = MODES[int(it["Mode"].CurrentIndex)][1]
        st.convert_pos = bool(it["PosConvert"].Checked)
        st.pos_factor = None if it["PosAuto"].Checked else float(it["Pos"].Value)
        return st

    @staticmethod
    def select_item(tree, item):
        try:
            item.Selected = True
        except Exception:
            pass
        try:
            tree.CurrentItem = item
        except Exception:
            pass

    # ------------------------------------------------------------ files
    def rebuild_file_list(self, select=0):
        tree = self.it["Files"]
        tree.Clear()
        self.building = True
        try:
            first = None
            for i, p in enumerate(self.paths):
                row = tree.NewItem()
                row.Text[0] = os.path.basename(p)
                row.Text[1] = str(i)       # hidden-ish index used to map back to path
                tree.AddTopLevelItem(row)
                if i == select:
                    first = row
            if first is not None:
                self.select_item(tree, first)
        finally:
            self.building = False
        self.refresh()

    def add_files(self, paths):
        have = set(self.paths)
        added = False
        for p in paths:
            p = os.path.abspath(p)
            if p in have or not os.path.isfile(p):
                continue
            try:
                self.texts[p] = read_text(p)
            except Exception as e:
                self.say("ERROR reading %s: %s" % (p, e))
                continue
            self.overrides.setdefault(p, {})
            self.paths.append(p)
            have.add(p)
            self.settings["last_dir"] = os.path.dirname(p)
            added = True
        if added:
            self.rebuild_file_list(select=self._cur_index())
        else:
            self.refresh()

    def _cur_index(self):
        p = self.current_path()
        return self.paths.index(p) if p in self.paths else 0

    def on_add(self):
        start = self.settings.get("last_dir", "")
        res = self.fusion.RequestFile("Add XML file", start, {"FReqS_Filter": "XML Files (*.xml)|*.xml|All Files (*)|*"})
        if res:
            self.add_files([res])

    def on_add_dir(self):
        start = self.settings.get("last_dir", "")
        d = self.fusion.RequestDir("Add all XML files from folder", start)
        if d:
            found = sorted(str(p) for p in Path(d).glob("*.xml"))
            if not found:
                self.say("No .xml files in %s" % d)
                return
            self.add_files(found)

    def on_remove(self):
        p = self.current_path()
        if p is None:
            return
        idx = self.paths.index(p)
        self.paths.remove(p)
        self.texts.pop(p, None)
        self.overrides.pop(p, None)
        self.rebuild_file_list(select=min(idx, len(self.paths) - 1))

    def on_clear(self):
        self.paths = []
        self.texts.clear()
        self.overrides.clear()
        self.rebuild_file_list()

    def on_pick_out(self):
        start = self.it["OutDir"].Text.strip() or self.settings.get("last_dir", "")
        d = self.fusion.RequestDir("Select Output Folder", start)
        if d:
            self.it["OutDir"].Text = str(d)

    # ------------------------------------------------------------ settings changes
    def on_toggles(self):
        if self.building:
            return
        it = self.it
        it["TlW"].Enabled = not it["TlAuto"].Checked
        it["TlH"].Enabled = not it["TlAuto"].Checked
        it["SrcW"].Enabled = not it["SrcAuto"].Checked
        it["SrcH"].Enabled = not it["SrcAuto"].Checked
        it["Target"].Enabled = not it["TargetAuto"].Checked
        it["PosAuto"].Enabled = bool(it["PosConvert"].Checked)
        it["Pos"].Enabled = bool(it["PosConvert"].Checked) and not it["PosAuto"].Checked
        self.refresh()

    # ------------------------------------------------------------ preview
    def refresh(self, keep_row=None):
        if self.building:
            return
        it = self.it
        path = self.current_path()
        table = it["Table"]
        self.building = True
        try:
            table.Clear()
            self.rows = []
            if not path:
                it["Info"].Text = "Add an XML to preview."
                self.set_status("No XML loaded", "info")
                return
            st = self.conv_settings()
            _, rows, info = process_xml(self.texts[path], st, self.overrides.get(path, {}))
            self.rows = rows

            # show computed auto values in the (disabled) controls
            if it["TlAuto"].Checked:
                it["TlW"].Value, it["TlH"].Value = info["tl"][0], info["tl"][1]
            if it["SrcAuto"].Checked:
                it["SrcW"].Value, it["SrcH"].Value = info["ref"][0], info["ref"][1]
            if it["TargetAuto"].Checked:
                it["Target"].Value = info["auto_target"]
            if it["PosAuto"].Checked:
                it["Pos"].Value = info["auto_pos"]

            it["Info"].Text = ("%s  |  Timeline %dx%d  |  Reference source %dx%d  |  Fill factor %.5f  |  %d video clips" % (
                os.path.basename(path), info["tl"][0], info["tl"][1], info["ref"][0], info["ref"][1],
                info["fill_factor"], len(rows)))
            if info["warns"]:
                self.set_status("WARNING: " + "; ".join(info["warns"]), "warning")
            else:
                self.set_status("%d XML file(s) loaded" % len(self.paths), "info")

            sel_item = None
            for i, rw in enumerate(rows):
                vals = [
                    str(rw["n"]), "V%d" % rw["vtrack"], rw["cid"], rw["name"],
                    "%dx%d" % rw["src"],
                    "%.4g" % rw["s_old"], "%.4f" % rw["s_new"],
                    "%.3f" % rw["p_old"][0], "%.3f" % rw["p_old"][1],
                    "%.3f" % rw["p_new"][0], "%.3f" % rw["p_new"][1],
                ]
                row_item = table.NewItem()
                for c, v in enumerate(vals):
                    row_item.Text[c] = v
                    try:
                        if rw["manual"] and c in (9, 10):
                            row_item.TextColor[c] = COLOR_MANUAL
                        elif c in NEW_COLS:
                            row_item.TextColor[c] = COLOR_NEW
                    except Exception:
                        pass
                table.AddTopLevelItem(row_item)
                if keep_row is not None and i == keep_row:
                    sel_item = row_item
            if sel_item is not None:
                self.select_item(table, sel_item)
        finally:
            self.building = False

    # ------------------------------------------------------------ manual position
    def selected_row(self):
        cur = self.it["Table"].CurrentItem()
        if cur is None:
            return None, None
        try:
            idx = int(cur.Text[0]) - 1
        except Exception:
            return None, None
        if 0 <= idx < len(self.rows):
            return idx, self.rows[idx]
        return None, None

    def on_row_selected(self):
        if self.building:
            return
        idx, rw = self.selected_row()
        if rw is None:
            return
        self.building = True
        try:
            self.it["ManX"].Value = float(rw["p_new"][0])
            self.it["ManY"].Value = float(rw["p_new"][1])
        finally:
            self.building = False
        kf = rw["kf"]
        self.it["ManX"].Enabled = not kf
        self.it["ManY"].Enabled = not kf
        self.it["ManSet"].Enabled = not kf
        if kf:
            self.say("%s has position keyframes: manual position not available." % rw["cid"])

    def on_manual_set(self):
        path = self.current_path()
        idx, rw = self.selected_row()
        if not path or rw is None or rw["kf"]:
            return
        self.overrides.setdefault(path, {})[rw["cid"]] = (float(self.it["ManX"].Value), float(self.it["ManY"].Value))
        self.refresh(keep_row=idx)

    def on_manual_clear(self):
        path = self.current_path()
        idx, rw = self.selected_row()
        if not path or rw is None:
            return
        self.overrides.get(path, {}).pop(rw["cid"], None)
        self.refresh(keep_row=idx)
        self.on_row_selected()

    def on_clear_overrides(self):
        path = self.current_path()
        if path:
            self.overrides[path] = {}
            self.refresh()

    # ------------------------------------------------------------ process
    def on_process(self):
        paths = list(self.paths)
        if not paths:
            self.say("Add at least one XML file first.")
            self.set_status("No XML loaded", "error")
            return
        st = self.conv_settings()
        suffix = self.it["Suffix"].Text
        custom_dir = self.it["OutDir"].Text.strip()
        self.save_current_settings()

        ok, failed = 0, 0
        for p in paths:
            outdir = custom_dir or os.path.join(os.path.dirname(p), OUT_FOLDER_NAME)
            stem = os.path.splitext(os.path.basename(p))[0]
            dst = os.path.join(outdir, stem + suffix + ".xml")
            if os.path.abspath(dst) == os.path.abspath(p):
                self.say("SKIP %s: output would overwrite the source (set a suffix or another folder)" % p)
                failed += 1
                continue
            try:
                os.makedirs(outdir, exist_ok=True)
                out, rows, info = process_xml(self.texts[p], st, self.overrides.get(p, {}))
                write_text(dst, out)
            except Exception as e:
                self.say("ERROR %s: %s" % (p, e))
                failed += 1
                continue
            n_man = sum(1 for r in rows if r["manual"])
            self.say("OK  %s -> %s  (%d clips, %d manual positions)" % (
                os.path.basename(p), dst, len(rows), n_man))
            for w in info["warns"]:
                self.say("    WARN " + w)
            ok += 1

        if failed:
            self.set_status("Done: %d written, %d failed/skipped" % (ok, failed), "warning")
        else:
            self.set_status("Done: %d file(s) written" % ok, "success")

    # ------------------------------------------------------------ run
    def run(self):
        self.win.Show()
        self.disp.RunLoop()
        self.win.Hide()


def main():
    App().run()


if __name__ == "__main__":
    main()
