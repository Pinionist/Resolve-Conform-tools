"""Find direct Media Pool clip uses in the current Resolve project.

Run from Workspace > Scripts > Utility. No third-party Python packages.
The scan only reads the project; navigation changes timeline and playhead.
"""

import math
import re
import time


def settings_for(obj):
    getter = getattr(obj, "GetSettings", None)
    if callable(getter):
        settings = getter()
        if isinstance(settings, dict):
            return settings
    return obj.GetSetting() or {}


def timebase(timeline):
    settings = settings_for(timeline)
    if str(settings.get("timelineInterlaceProcessing", "0")) == "1":
        raise ValueError("Interlaced timecode: navigation is not supported yet.")
    value = str(settings.get("timelineFrameRate", ""))
    match = re.match(r"\d+(?:\.\d+)?", value)
    if not match:
        raise ValueError("Cannot read timeline frame rate.")
    fps = float(match.group())
    nominal = round(fps)
    drop = (str(settings.get("timelineDropFrameTimecode", "0")) == "1"
            or "DF" in value or ";" in timeline.GetStartTimecode())
    if drop and not any(abs(fps - rate) < 0.02 for rate in (29.97, 59.94, 119.88)):
        raise ValueError("Unsupported drop-frame rate: " + value)
    if nominal < 1:
        raise ValueError("Invalid frame rate.")
    return nominal, (nominal // 15 if drop else 0)


def tc_to_frames(tc, nominal, drop=0):
    parts = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[:;](\d{2,3})", tc)
    if not parts:
        raise ValueError("Unsupported timecode: " + str(tc))
    h, m, s, f = map(int, parts.groups())
    if m > 59 or s > 59 or f >= nominal:
        raise ValueError("Invalid timecode: " + tc)
    minutes = h * 60 + m
    return ((h * 3600 + m * 60 + s) * nominal + f
            - drop * (minutes - minutes // 10))


def frames_to_tc(frame, nominal, drop=0):
    frame = int(frame)
    day = nominal * 86400 - drop * (1440 - 144)
    frame %= day
    if drop:
        ten_minutes = nominal * 600 - drop * 9
        minute = nominal * 60 - drop
        blocks, remainder = divmod(frame, ten_minutes)
        frame += drop * 9 * blocks
        if remainder >= drop:
            frame += drop * ((remainder - drop) // minute)
    seconds, f = divmod(frame, nominal)
    minutes, s = divmod(seconds, 60)
    h, m = divmod(minutes, 60)
    return "%02d:%02d:%02d%s%02d" % (h, m, s, ";" if drop else ":", f)


def timeline_tc(timeline, frame):
    nominal, drop = timebase(timeline)
    start = tc_to_frames(timeline.GetStartTimecode(), nominal, drop)
    offset = math.floor(frame) - int(timeline.GetStartFrame())
    return frames_to_tc(start + offset, nominal, drop)


def scan_project(project, selected):
    """Return direct occurrences, including audio and disabled clips.

    Identity is the Media Pool item's unique ID, never a name or file path.
    Embedded compound/multicam/Fusion contents are outside this scan.
    """
    targets = {}
    for media in selected:
        identity = media.GetUniqueId()
        if not identity:
            raise ValueError("Cannot read the selected clip's unique ID.")
        targets[identity] = media.GetName()
    if not targets:
        raise ValueError("Select one or more clips in the Media Pool first.")
    rows, warnings = [], []
    count = project.GetTimelineCount()
    if count is None:
        raise RuntimeError("Cannot read the project's timeline list.")
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline is None:
            warnings.append("Cannot read timeline %d." % index)
            continue
        name = timeline.GetName()
        for kind, prefix in (("video", "V"), ("audio", "A")):
            try:
                tracks = timeline.GetTrackCount(kind)
                if tracks is None:
                    raise RuntimeError("Cannot read track count")
                for track in range(1, tracks + 1):
                    clips = timeline.GetItemListInTrack(kind, track)
                    if clips is None:
                        raise RuntimeError("Cannot read track %s%d" % (prefix, track))
                    for item in clips:
                        media = item.GetMediaPoolItem()
                        if media is None:
                            continue
                        identity = media.GetUniqueId()
                        if identity not in targets:
                            continue
                        start, end = item.GetStart(), item.GetEnd()
                        try:
                            tc_in = timeline_tc(timeline, start)
                            tc_out = timeline_tc(timeline, end)
                        except ValueError as error:
                            tc_in, tc_out = "Frame %s" % start, "Frame %s" % end
                            warnings.append(name + ": " + str(error))
                        rows.append({
                            "source": targets[identity], "media_id": identity,
                            "timeline": timeline, "timeline_id": timeline.GetUniqueId(),
                            "timeline_name": name, "timeline_index": index,
                            "item_id": item.GetUniqueId(), "kind": kind, "track_index": track,
                            "track": "%s%d" % (prefix, track),
                            "clip": item.GetName(), "start": start, "end": end,
                            "in": tc_in, "out": tc_out,
                            "enabled": item.GetClipEnabled(),
                        })
            except Exception as error:
                warnings.append("%s (%s): %s" % (name, kind, error))
    return rows, sorted(set(warnings)), count


def navigate(resolve, project_id, row):
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None or project.GetUniqueId() != project_id:
        raise RuntimeError("Project changed. Run Find uses again.")
    timeline = None
    for index in range(1, project.GetTimelineCount() + 1):
        candidate = project.GetTimelineByIndex(index)
        if candidate and candidate.GetUniqueId() == row["timeline_id"]:
            timeline = candidate
            break
    if timeline is None:
        raise RuntimeError("Timeline was removed. Run Find uses again.")
    # Re-read the item: the user may have moved or trimmed it since the scan.
    for kind in ("video", "audio"):
        for track in range(1, timeline.GetTrackCount(kind) + 1):
            for item in timeline.GetItemListInTrack(kind, track) or []:
                if item.GetUniqueId() != row["item_id"]:
                    continue
                media = item.GetMediaPoolItem()
                if media is None or media.GetUniqueId() != row["media_id"]:
                    raise RuntimeError("Clip source changed. Run Find uses again.")
                tc = timeline_tc(timeline, item.GetStart())
                if not project.SetCurrentTimeline(timeline):
                    raise RuntimeError("Resolve could not open this timeline.")
                resolve.OpenPage("edit")
                # Resolve may finish switching the viewer after SetCurrentTimeline
                # returns. Confirm the actual playhead rather than trusting a bool.
                for attempt in range(10):
                    if not timeline.SetCurrentTimecode(tc):
                        raise RuntimeError("Timeline opened, but playhead navigation failed.")
                    time.sleep(0.1)
                    if timeline.GetCurrentTimecode().replace(";", ":") == tc.replace(";", ":"):
                        return timeline.GetName() + " — " + tc
                raise RuntimeError("Timeline opened, but playhead position could not be confirmed. Try again.")
    raise RuntimeError("Clip was removed. Run Find uses again.")


class ConnectedClipsWindow:
    def __init__(self, resolve, bmd):
        self.resolve = resolve
        self.rows = []
        self.project_id = None
        self.ui = resolve.Fusion().UIManager
        if self.ui is None:
            raise RuntimeError("Fusion UI Manager is unavailable. Use Resolve Studio.")
        ui = self.ui
        self.dispatcher = bmd.UIDispatcher(ui)
        self.window = self.dispatcher.AddWindow({
            "ID": "ConnectedClips", "WindowTitle": "Connected Clips — Media usage",
            "Geometry": [160, 160, 1100, 540],
        }, ui.VGroup({"Spacing": 10}, [
            ui.Label({"Text": "Select clips in Media Pool, then find their uses in this project.", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [
                ui.Button({"ID": "Scan", "Text": "Find uses of Media Pool selection"}),
                ui.Button({"ID": "Jump", "Text": "Go to selected use"}),
                ui.Button({"ID": "ClearButton", "Text": "Clear", "Weight": 0.2}),
            ]),
            ui.Tree({"ID": "Results", "ColumnCount": 9, "RootIsDecorated": False,
                     "AlternatingRowColors": True, "SortingEnabled": True,
                     "SelectionMode": "SingleSelection", "Events": {"ItemDoubleClicked": True}}),
            ui.Label({"ID": "Status", "Text": "Ready. Double-click a result to open its timeline.",
                      "WordWrap": True, "Weight": 0}),
            ui.Label({"Text": "Direct uses only. Compound / multicam contents and Fusion nodes are not expanded.\n"
                              "Audio and video uses are separate rows. OUT is exclusive. Scan again after edits.",
                      "WordWrap": True, "Weight": 0}),
            ui.HGroup({"Weight": 0}, [
                ui.HGap(0, 1),
                ui.Button({"ID": "CloseButton", "Text": "Close", "Weight": 0,
                           "MinimumSize": [360, 54], "MaximumSize": [360, 54],
                           "Font": ui.Font({"PointSize": 14})}),
            ]),
        ]))
        self.items = self.window.GetItems()
        tree = self.items["Results"]
        header = tree.NewItem()
        for i, label in enumerate(("#", "Source clip", "Timeline", "Track", "IN", "OUT", "Frames", "Enabled", "Timeline clip")):
            header.Text[i] = label
        tree.SetHeaderItem(header)
        for i, width in enumerate((40, 190, 190, 55, 110, 110, 65, 65, 170)):
            tree.ColumnWidth[i] = width
        self.window.On.Scan.Clicked = self.scan
        self.window.On.Jump.Clicked = self.jump
        self.window.On.ClearButton.Clicked = self.clear
        self.window.On.Results.ItemDoubleClicked = self.jump
        self.window.On.ConnectedClips.Close = self.close
        self.window.On.CloseButton.Clicked = self.close

    def clear(self, event=None):
        self.rows = []
        self.project_id = None
        self.items["Results"].Clear()
        self.items["Status"].Text = ""

    def scan(self, event=None):
        self.clear()
        try:
            project = self.resolve.GetProjectManager().GetCurrentProject()
            if project is None:
                raise RuntimeError("Open a project first.")
            self.project_id = project.GetUniqueId()
            selected = project.GetMediaPool().GetSelectedClips() or []
            self.items["Status"].Text = "Scanning timelines…"
            self.rows, warnings, total = scan_project(project, selected)
            tree = self.items["Results"]
            tree.SortingEnabled = False
            for index, row in enumerate(self.rows):
                item = tree.NewItem()
                values = (str(index + 1), row["source"], row["timeline_name"], row["track"],
                          row["in"], row["out"], str(row["end"] - row["start"]),
                          "Yes" if row["enabled"] else "No", row["clip"])
                for col, value in enumerate(values):
                    item.Text[col] = value
                tree.AddTopLevelItem(item)
            tree.SortingEnabled = True
            found = len({row["timeline_id"] for row in self.rows})
            status = "%d direct uses in %d timelines; %d project timelines scanned." % (len(self.rows), found, total)
            if warnings:
                status = "PARTIAL RESULTS / LIMITATIONS: " + status + " " + " | ".join(warnings[:3])
                print("Connected Clips warnings:\n" + "\n".join(warnings))
            self.items["Status"].Text = status
        except Exception as error:
            self.items["Status"].Text = str(error)

    def jump(self, event=None):
        try:
            item = event.get("item") if isinstance(event, dict) else None
            if item is None:
                item = self.items["Results"].CurrentItem()
            if item is None:
                raise RuntimeError("Select a result first.")
            row = self.rows[int(item.Text[0]) - 1]
            self.items["Status"].Text = navigate(self.resolve, self.project_id, row)
        except Exception as error:
            self.items["Status"].Text = str(error)

    def close(self, event=None):
        self.dispatcher.ExitLoop()

    def run(self):
        self.window.Show()
        self.scan()
        try:
            self.dispatcher.RunLoop()
        finally:
            self.window.Hide()


def main():
    bmd = globals().get("bmd")
    if bmd is None:
        import DaVinciResolveScript as bmd
    resolve = globals().get("resolve") or bmd.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError("Start DaVinci Resolve Studio and open a project first.")
    ConnectedClipsWindow(resolve, bmd).run()


if __name__ == "__main__":
    main()
