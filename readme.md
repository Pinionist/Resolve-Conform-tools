@ -0,0 +1,121 @@
# DaVinci Resolve Lua Scripts

These are some of the tools I use to speed up conforming & plate publishing in DaVinci Resolve.

## Installation

Place `.lua` files in:
- **Windows**: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\`
- **macOS**: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/`
- **Linux**: `~/.local/share/DaVinciResolve/Fusion/Scripts/Edit/`

Access via Workspace > Scripts > Edit

## ExportTimelineGenerator.lua

Duplicates timelines and groups clips by resolution. Each output timeline contains only clips matching its resolution and is configured to that resolution.
Some of the script logic based on Thatcher Freeman's "Generate All Clips Timeline" lua script. 

**Features:**
- Groups clips by native resolution
- Optional PAR (Pixel Aspect Ratio) correction for non-square pixels
- Optional half-resolution output (50%) with configurable minimum threshold
- Video-only mode (strips audio tracks)
- Multiple sorting methods (source name, inpoint, reel name, timeline position)
- Preserves Color page version names from source timeline
- Handles disabled clips

**Output:**
- Timeline name format: `EXPORT_<resolution>` (e.g., `EXPORT_1920x1080`)
- Suffixes added: `_PAR` for PAR-corrected, `_HALF` for half resolution


## RemoveSequencePadding.lua

Strips frame range indicators and file extensions from Media Pool clip names.

**Transformations:**
- `clip_name.[1001-1130].exr` → `clip_name`
- `clip_name_[1001-1130].mov` → `clip_name`
- `shot_010.mp4` → `shot_010`

**Operation:**
- Runs on current Media Pool bin
- Processes all clips in bin
- Only renames if pattern matches
- Verifies changes after rename

## TimelineClipsRenamer.lua

Batch renames timeline clips using customizable naming patterns. Handles multi-layer stacks and audio tracks. This version requires Resolve 20.2. 

**Pattern Syntax:**
- `#` = Number placeholder (padding determined by count: `##` = 2 digits, `####` = 4 digits)
- Scene + Shot pattern: `sc01` + `sh####` → `sc01_sh0010`, `sc01_sh0020`
- Layer suffix: `_L#` appended to stacked clips → `sc01_sh0010_L1`, `sc01_sh0010_L2`

**Features:**
- Preview before execution
- Start/increment values for numbering
- Process from timeline start or playhead position
- Separate processing for video/audio tracks
- Automatic detection of vertically stacked clips (shares naming across layers)
- Skips disabled clips

**Use Case:**
Standardize shot naming for editorial handoff or VFX plate organization.

## VersionControl.lua

This script is my modified version of Thatcher Freemans's "Update Version Number" script. 
Version management system for versioned file sequences (e.g., `shot_010_v001.exr`, `shot_010_v002.exr`).

**Context-Aware Operation:**
- **Timeline Mode**: Operates on all clips in current timeline (>0 clips present)
- **Media Pool Mode**: Operates on selected clips (no timeline or empty timeline)
- GUI indicates active mode in title bar

**Features:**
- Detects version numbers in file paths (v001, v002, V001, etc.)
- Version navigation (up/down/min/max)
- Scans filesystem for available versions (±50 from current)
- Automatic metadata extraction from file paths (Scene, Shot, Take)
- Color coding:
  - **Apricot**: v000 (plate versions)
  - **Violet**: v001+ (comp versions)
  - **Brown**: Timecode mismatch between plate and comp
- Plate metadata inheritance (requires matching duration)
- Plate/comp timecode comparison
- Simplified UI for >10 clips (summary view)
- Detailed UI for ≤10 clips (per-clip version list)

**Plate/Comp Detection:**
Automatically finds corresponding plate for comp clips by:
- Replacing `/comp/` with `/plate/` in path
- Resetting version to v000
- Matching Scene and Shot names

**Requirements:**
- Files must follow versioning pattern: `<name>_v###.<ext>` or `<name>_V###.<ext>`
- Plate/comp must have identical frame counts for timecode comparison
- Versions must exist on filesystem (script cannot create missing versions)

**Metadata Extraction:**
Parses file paths for:
- Scene: Text before shot identifier
- Shot: `SHOT_010`, `SH010`, `SEQ01_SH010`, etc.
- Take: Version number from filename

**Limitations:**
- Cannot switch versions if target file doesn't exist
- Timecode comparison skipped if plate/comp durations differ
- Metadata extraction depends on consistent file naming conventions

**Known bugs:**
-Currently there's a bug in Resolve when replacing clips (this script is using replace clip functionality) - when you have a clip imported from XML/AAF offline edit, Resolve thinks clips is much longer then it is, so when you're doing replace clips through this script (changing versions), then moves all the keyframes to the right of clip. Workaround - if possible, re-do your timewarps in compositing package of your choice and use non-timewarped versioned clip version in Resolve. 

## Notes

These scripts modify project data. Test on non-critical projects first. No undo functionality beyond Resolve's native history.

Version Control's plate/comp features assume specific folder structure (`/plate/` and `/comp/` directories). Modify `find_plate_sequence_path()` function if your structure differs.

# ExtractReelName.lua

Strips camera metadata, timestamps, and noise from Media Pool clip names, leaving only reel and clip identifiers.

**Transformations:**
- `A001_10060927_C005.mov` → `A001_C005`
- `A_0001C006_250116_101243_p1DTJ.mov` → `A001C006`
- `A001C003.mov` → `A001C003`

**Pattern Recognition:**
- Reel letters: A, B, C, D
- Reel digits: 3 or 4 (4-digit truncated to last 3)
- Clip digits: Exactly 3
- Patterns:
  - `[ABCD]###_[anything]_C###`
  - `[ABCD]_####C###`
  - `[ABCD]###C###`

**Operation:**
- Runs on current Media Pool bin
- Processes all clips in bin
- Skips clips already in correct format
- Returns original name if no pattern matches
- File extensions stripped automatically