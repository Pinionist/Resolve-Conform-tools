# DaVinci Resolve Scripts

These are some of the tools I use to speed up conforming & plate publishing in DaVinci Resolve.

## Installation

Place `.lua` files in:
- **Windows**: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\`
- **macOS**: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/`
- **Linux**: `~/.local/share/DaVinciResolve/Fusion/Scripts/Edit/`

The same folder also accepts `.py` scripts (see `Grid_Timeline_Builder.py` below) - Resolve runs either from the same menu.

Access via Workspace > Scripts > Edit

## ExportTimelineGenerator.lua

Duplicates one or more base timelines (via a DRT/AAF export-import round trip) and splits each into per-resolution copies. Each output timeline contains only the clips matching its resolution and is configured to that resolution.
Some of the script logic based on Thatcher Freeman's "Generate All Clips Timeline" lua script. 

**Base timeline selection:** timelines selected in the Media Pool, or every timeline in the current bin. Each selected base timeline is processed independently and gets its own set of output timelines.

**Features:**
- Groups clips by native resolution, one output timeline per source-timeline/resolution pair
- Optional PAR (Pixel Aspect Ratio) correction for non-square pixels
- Resolution scaling: No Scaling, Scale by Height, or Scale by Width to an arbitrary target size in px (not a fixed half-resolution step). Options to snap results to even pixel dimensions and to never upscale a clip smaller than the target
- Video-only mode (strips audio tracks)
- Include/exclude disabled clips
- Multiple sorting methods (source name, source inpoint, inpoint on timeline, reel name, or unsorted)
- Preserves Color page version names and custom clip names from the source timeline as version names on the output
- Optional: set clip display names directly to those shot names (no manual `%{Version}` step in the Inspector)
- Clips are colored per source timeline (cycled from Resolve's standard clip-color palette), so multi-timeline output stays visually traceable to its source
- Post-build verification per timeline (checks the applied resolution and warns if "Use Project Settings" is still enabled and overriding it)

**Output:**
- Timeline name format: `<source_timeline>_EXPORT_<source_resolution>[_PAR][_<final_w>x<final_h>]`
- `_PAR` appended when PAR-corrected; `_<width>x<height>` appended when scaling was applied (e.g. `EditTimeline_EXPORT_4096x2304_PAR_1920x1080`)

**Requirement:** base timelines must have "Use Project Settings" disabled, or the custom resolution is silently ignored (the script warns about this in the console, but won't fix it for you).

## TimelinePerFile.lua

Creates one timeline per clip from the current Media Pool bin (or just the current selection) - useful for turning a bin of individual plates/files into per-shot timelines in one pass, rather than one at a time.

**Scans for:** `.mp4`, `.mov`, `.mxf`, `.exr` (image sequences and video files); anything else in the bin is skipped and logged to the console with its path, extension, type, and format.

**Per-clip options:**
- Process selected clips only, or the whole current bin
- Preserve source FPS (skips a clip if FPS metadata is missing)
- Preserve source resolution (skips a clip if resolution metadata is missing)
- Preserve source start timecode, including drop-frame detection (skips a clip if the start TC is missing or malformed)
- Strip the file extension from the resulting timeline name

**Output:** one new timeline per clip, named after the source clip (minus extension, if that option is on). Skipped/ignored clips don't block the rest of the batch - the run finishes and reports created/skipped/ignored/timecode-warning counts.

**Requirement:** "Process selected clips only" needs `MediaPool:GetSelectedClips()`, added in Resolve 18.5+.


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

Batch renames timeline clips using customizable naming patterns. Handles multi-layer stacks and audio tracks.

**Pattern Syntax:**
- `#` = Number placeholder (padding determined by count: `##` = 2 digits, `####` = 4 digits)
- Scene + Shot pattern: `sc01` + `sh####` → `sc01_sh0010`, `sc01_sh0020`
- Layer suffix: `_L##` appended to stacked clips → `sc01_sh0010_L01`, `sc01_sh0010_L02`

**Features:**
- Preview before execution
- Start/increment values for numbering
- Process either the current timeline selection, or all clips from timeline start (no longer supports starting from the playhead position)
- Rename method: direct clip name, or a matching Color page version (audio clips always use the direct name - there's no Color page version system for audio)
- Separate processing for video/audio tracks
- Automatic detection of vertically stacked clips (shares naming across layers)
- Skips disabled clips

**Use Case:**
Standardize shot naming for editorial handoff or VFX plate organization.

**Requirement:** "Process selected clips only" mode requires `Timeline:GetSelectedClips()`, added in Resolve Studio 21.0.4 - older builds can still use the "all clips from timeline start" mode.

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

## ExtractReelName.lua

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

## Grid_Timeline_Builder.py

Builds a mosaic/contact-sheet timeline from a Media Pool bin: every clip scaled into its own cell in an auto-solved grid, all clips starting at timeline start. Runs from Workspace > Scripts > Edit like the `.lua` tools above, despite being Python (see Installation note above).

**Grid layout:**
- Auto-solves column/row count for the clip count and canvas resolution, or fixed column count
- Configurable gap (px, or % of timeline width/height), outer margin (half gap / full gap / none), minimum grid size (NxN), vertical anchor (top/center)
- "Fill empty space with random shots" pads incomplete rows and trailing space by repeating random bin shots (forces top anchor)

**Ordering:** by clip name, random, or by source (embedded) timecode.

**Aspect handling:**
- **Letterbox (fit)**: preserves each clip's own aspect inside its cell; mixed-aspect bins show pillarbox/letterbox bars
- **Crop to fill**: uses Resolve's native `Scaling = Fill` so mixed-resolution/aspect clips fill their cell edge-to-edge, no manual crop math. Crop basis: dominant source aspect, timeline resolution, or custom W:H. Guaranteed clean and undistorted only when the chosen basis matches the canvas's own aspect ratio; a mismatched basis fills with a slight non-uniform stretch instead of a gap (logged as a warning, not silent)

**Per-track color:** none, cycle through Resolve's standard clip-color palette, or random.

**Timing:** loop, bounce (ping-pong), or native length for clips shorter than the target; target length in frames (0 = length of the longest clip).

**Timeline:** configurable resolution (presets or custom W/H), optional frame-rate override, auto-generated name (`<bin>_grid_<W>x<H>`, editable), replace-existing or auto-version with a `_v001`, `_v002`, ... suffix.

**Persistence:** remembers last-used settings (grid, timing, aspect, color, resolution, bin, timeline name) between sessions in `~/.grid_timeline_builder_state.json`. Restoring the timeline name bypasses the auto-name logic, so reopening the GUI and rebuilding with different settings targets the same timeline unless you type a new name.

**Resolution filter:** restrict to bin clips matching one native resolution; warns when the bin has mixed resolutions.

**Requirements:**
- DaVinci Resolve Studio (uses TimelineItem Scaling/Zoom/Pan properties not exposed the same way in the Free edition)
- No external Python packages - built on Resolve's Fusion UI toolkit and the standard library only

**Known limitations:**
- Crop-to-fill is only guaranteed distortion-free when the crop basis equals the canvas aspect ratio; a true distortion-free arbitrary-aspect crop would need a compound clip per source clip - not implemented
- The `timelineFrameRate` setting key used for the frame-rate override is unverified against the scripting API beyond this build

## CompDeploy.py

Generates Fusion Studio `.comp` and Foundry Nuke `.nk` files from selected Media Pool clips with automatic version control and VFX notes integration.

**Output Formats:**
- Fusion Studio `.comp` files
- Foundry Nuke `.nk` scripts with ACES 1.2 or custom OCIO support
- Depth pass Fusion comps (separate versioning)
- Motion mask (MMask) Fusion comps (separate versioning)

**Features:**
- Independent version tracking per format (Fusion, Nuke, Depth, MMask)
- EXR export configuration (compression, bit depth, DWAA/DWAB quality)
- VFX notes extraction from clip Comments and Description fields
- Notes imported as StickyNote nodes in Fusion/Nuke
- Multi-layer stack support (clips share shot name, layers numbered sequentially)
- Primary layer auto-connected to Saver/Write nodes
- Configurable OCIO color management for Nuke
- Customizable output paths per format
- Settings persistence across sessions
- Atomic file writes (no partial/corrupted files)
- Debug mode for clip property inspection

**Workflow:**
1. Select clips in Media Pool (stacked clips detected automatically)
2. Configure EXR settings and output paths
3. Enable desired formats (Fusion/Nuke/Depth/MMask)
4. Generate - files created with auto-incremented versions

**Version Control:**
Each format maintains independent versioning. If `shot_010_comp_v003.comp` exists:
- Next Fusion file: `shot_010_comp_v004.comp`
- Next Nuke file: `shot_010_comp_v001.nk` (independent counter)
- Next Depth file: `shot_010_depth_v001.comp`
- Next MMask file: `shot_010_mmask_v001.comp`

**VFX Notes:**
Extracts notes from clip metadata fields:
- **Comments** field: Full text extracted
- **Description** field: Full text extracted
- **Format**: StickyNote nodes positioned left of primary Loader node
- Color-coded by source (Comments vs Description)

**Layer Handling:**
Stacked clips share base shot name with layer suffixes:
- Single clip: `shot_010_comp_v001.comp`
- Stack: `shot_010_L01_comp_v001.comp`, `shot_010_L02_comp_v001.comp`
- Primary layer (lowest track) connects to output

**Color Management:**
Nuke scripts support:
- ACES 1.2 (default): Input Device Transform (IDT) + RRT/ODT for sRGB
- Custom OCIO: User-specified config file path
- Default: Linear workflow without LUTs

**Output Path Defaults:**
- Fusion: `~/Desktop/fusion_comps/`
- Nuke: `~/Desktop/nuke_comps/`
- Depth: `~/Desktop/fusion_comps/depth/`
- MMask: `~/Desktop/fusion_comps/mmask/`

**Requirements:**
- PySide6 or PySide2
- DaVinci Resolve API access
- Write permissions to output directories

## PlateOrganizer.py

Reorganizes flat directory structures into hierarchical scene/shot/asset folders based on naming patterns.

**Pattern Recognition:**
Parses folder names following: `<scene>_sh<shot>_L<layer>_<asset>_v<version>`

**Examples:**
- `bz_av_sh0030_L01_input_v000` → `bz_av/bz_av_sh0030/input/`
- `sc01_sh0010_plate_v000` → `sc01/sc01_sh0010/plate/`
- `seq01_sh0050_L02_comp_v003` → `seq01/seq01_sh0050/comp/`

**Features:**
- Scene name detection (captures everything before `_sh`)
- Multi-layer sequence support (L01, L02, etc.)
- Version preservation in folder structure
- Dry run mode (preview changes without moving files)
- Progress tracking with visual feedback
- Settings persistence (remembers last source path)
- Duplicate detection (warns if target exists)
- Unmatched folder reporting

**Workflow:**
1. Select source directory containing flat folder structure
2. Scan to analyze naming patterns
3. Review detected scenes/shots/assets in table view
4. Enable/disable dry run mode
5. Organize - folders moved into hierarchy

**Output Structure:**
```
source_directory/
├── scene_name/
│   ├── scene_name_sh0010/
│   │   ├── asset_name/
│   │   │   ├── scene_name_sh0010_L01_asset_name_v000/
│   │   │   └── scene_name_sh0010_L02_asset_name_v001/
│   │   └── another_asset/
│   │       └── scene_name_sh0010_another_asset_v000/
│   └── scene_name_sh0020/
│       └── asset_name/
│           └── scene_name_sh0020_asset_name_v000/
```

**Dry Run Mode:**
Preview operations without modifying filesystem. Operations logged with visual indicators:
- `📁 CREATE: path/` - Directory creation
- `🚚 MOVE: source → destination` - File/folder move
- `⚠️ SKIP: reason` - Skipped operation

**Operation:**
- Scans directories recursively
- Matches folders against regex patterns
- Groups by scene → shot → asset
- Creates hierarchy if missing
- Moves folders preserving contents
- Reports unmatched folders (non-conforming names)

**GUI Elements:**
- Source path browser with settings persistence
- Scene/Shot/Asset table summary
- Progress bar for long operations
- Detailed operation log
- Statistics display (scene count, shot count, asset count)

**Limitations:**
- Requires consistent naming convention
- Does not handle files outside folders
- Scene name must precede `_sh` pattern
- Cannot recover from interrupted operations

**Requirements:**
- PySide6 or PySide2
- Write permissions to source directory
- Sufficient disk space for reorganization

## Notes

These scripts modify project data. Test on non-critical projects first. No undo functionality beyond Resolve's native history.

Version Control's plate/comp features assume specific folder structure (`/plate/` and `/comp/` directories). Modify `find_plate_sequence_path()` function if your structure differs.

CompDeploy uses atomic file writes to prevent corruption. Temporary files (`.tmp` extension) indicate incomplete operations.

PlateOrganizer dry run mode is enabled by default. Disable before executing actual file moves.
