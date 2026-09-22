--[[
Resolution-Based Timeline Generator v3.0 - Proportional Scaling
Copies existing timelines (that have "Use Project Settings" disabled) and creates
new versions for each resolution found in the clips, optionally scaled to a target
height or width while preserving aspect ratio.

Preserves Color page version names and custom clip names from the source timeline.
- If clips have Color page version names (set by TimelineClipsRenamer), those will be preserved
- If clips have custom timeline names different from media names, those will be preserved as version names
- When "Set clip display names to shot names" is enabled, clip names are set directly — no manual Inspector step needed
]]--

function print_table(t, indentation)
    if indentation == nil then
        indentation = 0
    end
    local outer_prefix = string.rep("    ", indentation)
    local inner_prefix = string.rep("    ", indentation + 1)
    print(outer_prefix, "{")
    for k, v in pairs(t) do
        if type(v) == "table" then
            print(inner_prefix, k, ": ")
            print_table(v, indentation + 1)
        elseif type(v) == "string" then
            print(inner_prefix, k, string.format([[: "%s"]], v))
        else
            print(inner_prefix, k, ": ", v)
        end
    end
    print(outer_prefix, "}")
end

-- Function to get clip resolution
function getClipResolution(mediaPoolItem)
    if not mediaPoolItem then
        return "Unknown"
    end

    local width = nil
    local success = pcall(function()
        width = mediaPoolItem:GetClipProperty("Resolution")
    end)

    if success and width then
        return width
    end

    local clipWidth  = nil
    local clipHeight = nil

    pcall(function()
        clipWidth  = mediaPoolItem:GetClipProperty("Width")
        clipHeight = mediaPoolItem:GetClipProperty("Height")
    end)

    if clipWidth and clipHeight then
        return clipWidth .. "x" .. clipHeight
    end

    return "Unknown"
end

-- Function to get pixel aspect ratio
function getPixelAspectRatio(mediaPoolItem)
    if not mediaPoolItem then
        return 1.0
    end

    local par     = nil
    local success = pcall(function()
        par = mediaPoolItem:GetClipProperty("PAR")
        if not par then par = mediaPoolItem:GetClipProperty("Pixel Aspect Ratio") end
        if not par then par = mediaPoolItem:GetClipProperty("PixelAspectRatio")   end
    end)

    if success and par then
        local par_num = tonumber(par)
        if par_num and par_num > 0 then
            return par_num
        end
    end

    return 1.0
end

-- Function to calculate PAR-corrected resolution
function calculatePARCorrectedResolution(width, height, par)
    if not width or not height or not par or par <= 0 then
        return width, height, "Invalid parameters"
    end

    if par == 1.0 then
        return width, height, "Square pixels (PAR = 1.0)"
    end

    local corrected_height = math.floor(height / par)
    if corrected_height % 2 ~= 0 then
        corrected_height = corrected_height - 1
    end

    local reason = string.format("PAR correction: %dx%d (PAR %.2f) -> %dx%d",
                                 width, height, par, width, corrected_height)
    return width, corrected_height, reason
end

-- Function to parse resolution string and return width, height
function parseResolution(resolutionString)
    if not resolutionString or resolutionString == "Unknown" then
        print("  parseResolution: Invalid input - " .. tostring(resolutionString))
        return nil, nil
    end

    print("  parseResolution: Parsing '" .. resolutionString .. "'")

    local width, height = resolutionString:match("(%d+)x(%d+)")

    if width and height then
        local w = tonumber(width)
        local h = tonumber(height)
        print("  parseResolution: Successfully parsed to " .. w .. "x" .. h)
        return w, h
    else
        print("  parseResolution: Failed to match pattern for '" .. resolutionString .. "'")
        return nil, nil
    end
end

-- Return the largest even integer <= n
function floorEven(n)
    local f = math.floor(n)
    if f % 2 ~= 0 then f = f - 1 end
    return f
end

-- Calculate proportionally scaled resolution.
-- scale_mode : "No Scaling" | "Scale by Height" | "Scale by Width"
-- target_size: integer, desired dimension in pixels
-- keep_even  : boolean - when true, both output dimensions are even integers and
--              the pair is chosen to minimise aspect-ratio error vs the source,
--              with proximity to target_size as a secondary tiebreaker.
--              Independent per-axis rounding is NOT used because it breaks AR.
-- Returns    : new_width, new_height, reason_string
function calculateScaledResolution(width, height, scale_mode, target_size, keep_even)
    if not width or not height then
        return width, height, "Invalid resolution"
    end

    if scale_mode == "No Scaling" or not scale_mode then
        return width, height, "No scaling applied"
    end

    if not target_size or target_size <= 0 then
        return width, height, "Invalid target size"
    end

    local ar = width / height   -- original aspect ratio (W/H), kept as reference throughout

    local exact_width, exact_height, scale_factor

    if scale_mode == "Scale by Height" then
        scale_factor   = target_size / height
        exact_height   = target_size
        exact_width    = width * scale_factor
    elseif scale_mode == "Scale by Width" then
        scale_factor   = target_size / width
        exact_width    = target_size
        exact_height   = height * scale_factor
    else
        return width, height, "Unknown scale mode: " .. tostring(scale_mode)
    end

    local new_width  = math.floor(exact_width  + 0.5)
    local new_height = math.floor(exact_height + 0.5)

    local reason = string.format(
        "Scale by %s to %dpx: %dx%d -> %dx%d (factor %.4f)",
        (scale_mode == "Scale by Height") and "height" or "width",
        target_size, width, height, new_width, new_height, scale_factor
    )

    if keep_even then
        -- Search a range of even candidates for the non-target (derived) axis.
        -- For each candidate, derive the other axis by preserving AR and snap that
        -- to the nearest even value too.  Pick the (w, h) pair that minimises
        -- AR error; use proximity to target_size as a secondary tiebreaker.
        --
        -- This avoids independently rounding the two axes, which would silently
        -- change the aspect ratio (e.g. 4224x2240 -> 3620x1920 instead of 3628x1924).

        local SEARCH_STEPS = 10   -- ±SEARCH_STEPS even values around the initial estimate

        local best_w, best_h = new_width, new_height
        local best_score     = math.huge

        if scale_mode == "Scale by Height" then
            -- Width is the derived axis; search even widths around new_width.
            local w_center = floorEven(exact_width)
            for step = -SEARCH_STEPS, SEARCH_STEPS do
                local w = w_center + step * 2
                if w > 0 then
                    -- Derive height from w using original AR, then try the two
                    -- surrounding even values.
                    local h_exact = w / ar
                    local h_lo    = floorEven(h_exact)
                    for _, h in ipairs({h_lo, h_lo + 2}) do
                        if h > 0 then
                            local ar_err     = math.abs(w / h - ar)
                            local target_err = math.abs(h - target_size)
                            -- AR fidelity is primary; closeness to target is secondary.
                            local score = ar_err * 10000 + target_err * 0.001
                            if score < best_score then
                                best_score = score
                                best_w     = w
                                best_h     = h
                            end
                        end
                    end
                end
            end
        else  -- Scale by Width
            -- Height is the derived axis; search even heights around new_height.
            local h_center = floorEven(exact_height)
            for step = -SEARCH_STEPS, SEARCH_STEPS do
                local h = h_center + step * 2
                if h > 0 then
                    local w_exact = h * ar
                    local w_lo    = floorEven(w_exact)
                    for _, w in ipairs({w_lo, w_lo + 2}) do
                        if w > 0 then
                            local ar_err     = math.abs(w / h - ar)
                            local target_err = math.abs(w - target_size)
                            local score = ar_err * 10000 + target_err * 0.001
                            if score < best_score then
                                best_score = score
                                best_w     = w
                                best_h     = h
                            end
                        end
                    end
                end
            end
        end

        reason = reason .. string.format(
            " -> even AR-preserved: %dx%d (ar_score %.4f)", best_w, best_h, best_score
        )
        new_width  = best_w
        new_height = best_h
    end

    return new_width, new_height, reason
end

-- Wrapper that returns apply_scale flag alongside dimensions
function shouldApplyScaling(width, height, scale_mode, target_size, keep_even, no_upscale)
    if scale_mode == "No Scaling" or not scale_mode then
        return false, width, height, "No scaling requested"
    end
    if not width or not height then
        return false, width, height, "Invalid resolution values"
    end
    -- Never upscale: if the relevant source dimension is already <= target,
    -- keep the source resolution unchanged.
    if no_upscale then
        if scale_mode == "Scale by Height" and height <= target_size then
            return false, width, height,
                string.format("Source height %dpx <= target %dpx — no upscaling applied", height, target_size)
        end
        if scale_mode == "Scale by Width" and width <= target_size then
            return false, width, height,
                string.format("Source width %dpx <= target %dpx — no upscaling applied", width, target_size)
        end
    end
    local new_w, new_h, reason = calculateScaledResolution(width, height, scale_mode, target_size, keep_even)
    return true, new_w, new_h, reason
end

-- Function to get timeline item's version name (Color page version) or fallback to clip name
function getTimelineItemVersionName(timeline_item)
    if not timeline_item then return nil end

    local version_name = nil
    local debug_info   = ""

    local success = pcall(function()
        -- Method 1: current version
        local current_version = timeline_item:GetCurrentVersion()
        if current_version then
            debug_info = debug_info .. "Current version found. "
            if current_version.VersionName and current_version.VersionName ~= "" and current_version.VersionName ~= "Version 1" then
                version_name = current_version.VersionName
                debug_info = debug_info .. "Version name: " .. version_name .. ". "
            else
                debug_info = debug_info .. "Version name empty/default. "
            end
        else
            debug_info = debug_info .. "No current version. "
        end

        -- Method 2: version list
        if not version_name then
            local version_list = timeline_item:GetVersionNameList()
            if version_list and #version_list > 0 then
                debug_info = debug_info .. "Version list has " .. #version_list .. " items. "
                for _, v_name in ipairs(version_list) do
                    if v_name and v_name ~= "" and v_name ~= "Version 1" then
                        version_name = v_name
                        debug_info = debug_info .. "Found custom version: " .. v_name .. ". "
                        break
                    end
                end
            else
                debug_info = debug_info .. "No version list. "
            end
        end

        -- Method 3: clip name fallback
        if not version_name then
            local clip_name = timeline_item:GetName()
            if clip_name and clip_name ~= "" then
                local media_item = timeline_item:GetMediaPoolItem()
                local media_name = ""
                if media_item then media_name = media_item:GetName() or "" end
                if clip_name ~= media_name then
                    version_name = clip_name
                    debug_info = debug_info .. "Using clip name as fallback: " .. clip_name .. ". "
                else
                    debug_info = debug_info .. "Clip name matches media name, skipping. "
                end
            else
                debug_info = debug_info .. "No clip name. "
            end
        end
    end)

    if version_name or debug_info ~= "No current version. No version list. No clip name. " then
        print("    Debug: " .. debug_info)
    end

    if success and version_name and version_name ~= "" and version_name ~= "Version 1" then
        return version_name
    end
    return nil
end

-- Function to set timeline item's version name
function setTimelineItemVersionName(timeline_item, name)
    if not timeline_item or not name or name == "" then return false end

    local success = false
    pcall(function()
        timeline_item:DeleteVersionByName()
        success = timeline_item:AddVersion(name, 0)
    end)
    return success
end

-- Get all video timeline items (all tracks)
function getAllTimelineItems(timeline)
    local all_items = {}
    if not timeline then return all_items end

    pcall(function()
        local video_track_count = timeline:GetTrackCount("video")
        for track_idx = 1, video_track_count do
            local track_items = timeline:GetItemListInTrack("video", track_idx)
            if track_items then
                for _, item in ipairs(track_items) do
                    table.insert(all_items, item)
                end
            end
        end
    end)
    return all_items
end

-- Duplicate a timeline via export/import
function duplicateTimeline(project, media_pool, source_timeline, new_name)
    print("Attempting to duplicate timeline: " .. source_timeline:GetName() .. " to " .. new_name)

    local timeline_count_before = project:GetTimelineCount()

    local export_formats = {
        {format = resolve.EXPORT_DRT, ext = ".drt", name = "DRT"},
        {format = resolve.EXPORT_AAF, ext = ".aaf", name = "AAF"}
    }

    for _, export_info in ipairs(export_formats) do
        print("  Trying export format: " .. export_info.name)

        local temp_dir  = os.getenv("TEMP") or os.getenv("TMP") or os.getenv("TMPDIR") or "/tmp"
        local separator = package.config:sub(1,1)
        temp_file = temp_dir .. separator .. "resolve_timeline_" .. os.time() .. "_" .. math.random(1000,9999) .. export_info.ext

        local export_success = false
        pcall(function()
            export_success = source_timeline:Export(temp_file, export_info.format, resolve.EXPORT_NONE)
        end)

        if export_success then
            print("  Exported timeline to: " .. temp_file)

            pcall(function()
                media_pool:ImportTimelineFromFile(temp_file, {timelineName = new_name})
            end)

            pcall(function() os.remove(temp_file) end)

            local timeline_count_after = project:GetTimelineCount()
            if timeline_count_after > timeline_count_before then
                for i = 1, timeline_count_after do
                    local timeline = project:GetTimelineByIndex(i)
                    if timeline then
                        local tl_name = timeline:GetName()
                        if tl_name and (tl_name == new_name or string.find(tl_name, new_name)) then
                            print("  Successfully duplicated timeline as: " .. tl_name)
                            return timeline
                        end
                    end
                end

                -- Fallback: last timeline
                local new_timeline = project:GetTimelineByIndex(timeline_count_after)
                if new_timeline then
                    print("  Found new timeline, attempting to rename...")
                    local rename_success = false
                    for attempt = 1, 3 do
                        pcall(function()
                            if project:SetCurrentTimeline(new_timeline) then
                                if new_timeline:SetName(new_name) then
                                    rename_success = true
                                end
                            end
                        end)
                        if rename_success then
                            print("  Renamed timeline to: " .. new_name)
                            break
                        else
                            print("  Rename attempt " .. attempt .. " failed")
                        end
                    end
                    if not rename_success then
                        print("  WARNING: Could not rename timeline")
                    end
                    return new_timeline
                end
            end
        else
            print("  Failed to export with format: " .. export_info.name)
        end
    end

    print("  Failed to duplicate timeline via export/import")
    return nil
end

-- Remove all clips from a timeline
function clearTimelineClips(timeline)
    if not timeline then
        print("Error: No timeline provided.")
        return
    end

    print("Clearing all clips from timeline...")

    local status, err = pcall(function()
        local video_track_count = timeline:GetTrackCount("video")
        local audio_track_count = timeline:GetTrackCount("audio")

        for i = 1, video_track_count do
            local items = timeline:GetItemListInTrack("video", i)
            if items and #items > 0 then
                print("  Deleting " .. #items .. " video items from track " .. i)
                timeline:DeleteClips(items)
            end
        end

        for i = 1, audio_track_count do
            local items = timeline:GetItemListInTrack("audio", i)
            if items and #items > 0 then
                print("  Deleting " .. #items .. " audio items from track " .. i)
                timeline:DeleteClips(items)
            end
        end
    end)

    if status then
        print("  Successfully cleared all clips.")
    else
        print("  Error clearing clips: " .. tostring(err))
    end
end

-- Remove all audio content from a timeline.
-- Clears clips from every audio track first, then deletes tracks top-down.
-- Resolve may refuse to delete the very last audio track; that track is left empty.
function removeAllAudioTracks(timeline)
    if not timeline then
        print("Error: No timeline provided.")
        return
    end

    print("Removing audio content from timeline...")

    local status, err = pcall(function()
        local trackCount = timeline:GetTrackCount("audio")
        print("  Found " .. trackCount .. " audio track(s)")

        -- Step 1: delete all clips from every audio track (including track 1)
        for i = 1, trackCount do
            local items = timeline:GetItemListInTrack("audio", i)
            if items and #items > 0 then
                timeline:DeleteClips(items)
                print("  Cleared " .. #items .. " clip(s) from audio track " .. i)
            end
        end

        -- Step 2: delete tracks top-down; Resolve will reject the very last track,
        -- which is caught by the inner pcall and left as an empty track.
        for i = trackCount, 1, -1 do
            local ok = pcall(function()
                timeline:DeleteTrack("audio", i)
            end)
            if ok then
                print("  Deleted audio track " .. i)
            else
                print("  Could not delete audio track " .. i .. " (likely last track - left empty)")
            end
        end
    end)

    if not status then
        print("  Error in removeAllAudioTracks: " .. tostring(err))
    end
end

-- Find a direct subfolder of root by name, or create it if absent.
-- Returns the folder object, or nil on failure.

-- ─── MAIN ────────────────────────────────────────────────────────────────────
function main()
    local ui   = fu.UIManager
    local disp = bmd.UIDispatcher(ui)
    local win_w, win_h = 470, 520

    win = disp:AddWindow({
        ID          = "MyWin",
        WindowTitle = "Generate Resolution-Based Timelines v3.1",
        Geometry    = {100, 100, win_w, win_h},
        Spacing     = 8,
        ui:VGroup{
            ID = "root",

            -- Header
            ui:Label{
                ID   = "headerLabel",
                Text = "Resolution-Based Timeline Generator",
                Weight = 0,
                Font = ui:Font{ PixelSize = 13, StyleName = "Bold" }
            },
            ui:Label{ ID = "sep1", Text = string.rep(" ", 60), Weight = 0 },

            -- Selection
            ui:HGroup{
                Weight = 0,
                ui:Label{ Text = "Base Timelines:", MinimumSize = {130, 0} },
                ui:ComboBox{ ID = "selectionMethod" }
            },
            ui:HGroup{
                Weight = 0,
                ui:Label{ Text = "Sort Clips By:", MinimumSize = {130, 0} },
                ui:ComboBox{ ID = "sortingMethod" }
            },
            ui:Label{ ID = "sep1", Text = string.rep(" ", 60), Weight = 0 },

            -- Clip / track options
            ui:CheckBox{ ID = "includeDisabledItems", Text = "Include Disabled Clips",                       Weight = 0 },
            ui:CheckBox{ ID = "videoOnly",            Text = "Video Only (No Audio)",                        Weight = 0, Checked = true  },
            ui:CheckBox{ ID = "correctPAR",           Text = "Correct Non-Square Pixel Aspect Ratios",       Weight = 0, Checked = false },
            ui:Label{ ID = "sep1", Text = string.rep(" ", 60), Weight = 0 },

            -- Scaling section
            ui:Label{
                ID   = "scalingHeader",
                Text = "Resolution Scaling",
                Weight = 0,
                Font = ui:Font{ PixelSize = 11, StyleName = "Bold" }
            },
            ui:HGroup{
                Weight = 0,
                ui:Label{ Text = "Scale Mode:", MinimumSize = {130, 0} },
                ui:ComboBox{ ID = "scaleMode" }
                
            },
            ui:HGroup{
                Weight = 0,
                ui:Label{ Text = "Target Size (px):", MinimumSize = {130, 0} },
                ui:SpinBox{
                    ID         = "targetSize",
                    Minimum    = 1,
                    Maximum    = 32768,
                    Value      = 1920,
                    SingleStep = 2
                },
            },
            ui:Label{ ID = "sep1", Text = string.rep(" ", 60), Weight = 0 },
            ui:CheckBox{
                ID      = "keepEven",
                Text    = "Keep resolution numbers even (snap to nearest even px)",
                Weight  = 0,
                Checked = true
            },
            ui:CheckBox{
                ID      = "noUpscale",
                Text    = "Never upscale (keep source resolution if smaller than target)",
                Weight  = 0,
                Checked = true
            },
            
            ui:Label{ ID = "sep1", Text = string.rep(" ", 60), Weight = 0 },

            -- Output organisation
            ui:Label{
                ID   = "orgHeader",
                Text = "Output Organisation",
                Weight = 0,
                Font = ui:Font{ PixelSize = 11, StyleName = "Bold" }
            },

            ui:CheckBox{
                ID      = "autoRenameClips",
                Text    = "Set clip display names to shot names (from Color page version names)",
                Weight  = 0,
                Checked = true
            },
            ui:Label{ ID = "sep1", Text = string.rep(" ", 60), Weight = 0 },

            -- Buttons
            ui:HGroup{
                Weight = 0,
                ui:Button{ ID = "cancelButton", Text = "Cancel" },
                ui:Button{ ID = "goButton",     Text = "Generate Timelines" }
            }
        }
    })

    run_export = false

    function win.On.MyWin.Close(ev)
        disp:ExitLoop()
        run_export = false
    end

    function win.On.cancelButton.Clicked(ev)
        print("Cancelled.")
        disp:ExitLoop()
        run_export = false
    end

    function win.On.goButton.Clicked(ev)
        disp:ExitLoop()
        run_export = true
    end

    itm = win:GetItems()

    itm.selectionMethod:AddItem("Selected in Media Pool")
    itm.selectionMethod:AddItem("All in Current Bin")

    itm.sortingMethod:AddItem("Source Name")
    itm.sortingMethod:AddItem("Source Inpoint")
    itm.sortingMethod:AddItem("Inpoint on Timeline")
    itm.sortingMethod:AddItem("Reel Name")
    itm.sortingMethod:AddItem("None")

    itm.scaleMode:AddItem("No Scaling")
    itm.scaleMode:AddItem("Scale by Height")
    itm.scaleMode:AddItem("Scale by Width")
    itm.scaleMode.CurrentIndex = 1
    itm.targetSize.Value = 1920

    win:Show()
    disp:RunLoop()
    win:Hide()

    if not run_export then return end

    -- ── Read GUI values ───────────────────────────────────────────────────
    local allow_disabled_clips = itm.includeDisabledItems.Checked
    local video_only           = itm.videoOnly.Checked
    local correct_par          = itm.correctPAR.Checked
    local sorting_method       = itm.sortingMethod.CurrentText
    local scale_mode           = itm.scaleMode.CurrentText
    local target_size          = itm.targetSize.Value
    local keep_even            = itm.keepEven.Checked
    local no_upscale           = itm.noUpscale.Checked
    local auto_rename_clips    = itm.autoRenameClips.Checked

    -- ── Resolve context ───────────────────────────────────────────────────
    resolve        = Resolve()
    projectManager = resolve:GetProjectManager()
    project        = projectManager:GetCurrentProject()
    media_pool     = project:GetMediaPool()
    num_timelines  = project:GetTimelineCount()
    selected_bin   = media_pool:GetCurrentFolder()

    local clipsByResolution = {}

    -- Build project timeline lookup table
    project_timelines = {}
    for timeline_idx = 1, num_timelines do
        local runner_timeline = project:GetTimelineByIndex(timeline_idx)
        if runner_timeline then
            local timeline_name = nil
            pcall(function() timeline_name = runner_timeline:GetName() end)
            if timeline_name then
                project_timelines[timeline_name] = runner_timeline
            end
        end
    end

    -- Collect selected base timelines
    local selected_items = {}
    local base_timelines = {}

    if itm.selectionMethod.CurrentText == "All in Current Bin" then
        if selected_bin then
            local bin_clips = selected_bin:GetClipList()
            if bin_clips then selected_items = bin_clips end
        end
    else
        local sel_clips = media_pool:GetSelectedClips()
        if sel_clips then selected_items = sel_clips end
    end

    for _, item in pairs(selected_items) do
        if type(item) ~= "nil" and type(item) ~= "number" then
            local clip_type = ""
            pcall(function() clip_type = item:GetClipProperty("Type") end)

            if clip_type == "Timeline" then
                local timeline_name = nil
                pcall(function() timeline_name = item:GetName() end)

                if timeline_name and project_timelines[timeline_name] then
                    table.insert(base_timelines, project_timelines[timeline_name])
                    print("Found base timeline: " .. timeline_name)
                end
            end
        end
    end

    if #base_timelines == 0 then
        print("No base timelines selected. Please select timelines with 'Use Project Settings' disabled.")
        return
    end



    -- ── Assign a clip color per source timeline ───────────────────────────
    local timeline_colors = {}
    local color_palette = {
        "Orange", "Apricot", "Yellow", "Lime", "Olive", "Green",
        "Teal", "Navy", "Blue", "Purple", "Violet", "Pink",
        "Tan", "Beige", "Brown", "Chocolate"
    }
    for i, tl in ipairs(base_timelines) do
        local tl_name = tl:GetName()
        local color = color_palette[((i - 1) % #color_palette) + 1]
        timeline_colors[tl_name] = color
        print("Color assigned: " .. tl_name .. " -> " .. color)
    end

    print("Processing " .. #base_timelines .. " base timeline(s)...")
    print("Scale mode : " .. scale_mode)
    if scale_mode ~= "No Scaling" then
        print("Target size: " .. target_size .. "px")
        print("Keep even  : " .. tostring(keep_even))
    end

    -- ── Collect clips grouped by source resolution ────────────────────────
    for _, base_timeline in ipairs(base_timelines) do
        local timeline_name = base_timeline:GetName()
        print("\nProcessing base timeline: " .. timeline_name)

        local base_use_project, base_width, base_height
        pcall(function()
            base_use_project = base_timeline:GetSetting("useProjectSettings") or
                               base_timeline:GetSetting("UseProjectSettings")
            base_width  = base_timeline:GetSetting("timelineResolutionWidth")
            base_height = base_timeline:GetSetting("timelineResolutionHeight")
        end)

        print("  Use Project Settings: " .. tostring(base_use_project))
        print("  Current Resolution  : " .. tostring(base_width) .. "x" .. tostring(base_height))

        if base_use_project == "1" or base_use_project == 1 or base_use_project == true then
            print("  WARNING: 'Use Project Settings' is enabled on this base timeline - disable it first!")
        end

        local num_tracks = 0
        pcall(function() num_tracks = base_timeline:GetTrackCount("video") end)

        for track_idx = 1, num_tracks do
            local track_items = nil
            pcall(function() track_items = base_timeline:GetItemListInTrack("video", track_idx) end)

            if track_items then
                for _, track_item in ipairs(track_items) do
                    if track_item then
                        local item_name = "Unknown"
                        pcall(function() item_name = track_item:GetName() end)

                        local version_name = getTimelineItemVersionName(track_item)
                        if version_name then
                            print("    Found version name: " .. version_name)
                        else
                            print("    No version name for: " .. item_name)
                        end

                        local is_enabled = true
                        pcall(function() is_enabled = track_item:GetClipEnabled() end)

                        if allow_disabled_clips or is_enabled then
                            local media_item       = nil
                            local get_media_success = pcall(function()
                                media_item = track_item:GetMediaPoolItem()
                            end)

                            if get_media_success and media_item then
                                local resolution = getClipResolution(media_item)
                                local par        = getPixelAspectRatio(media_item)

                                if resolution ~= "Unknown" then
                                    local orig_width, orig_height = parseResolution(resolution)

                                    if orig_width and orig_height then
                                        local corrected_width  = orig_width
                                        local corrected_height = orig_height
                                        local par_reason = ""

                                        if correct_par then
                                            corrected_width, corrected_height, par_reason =
                                                calculatePARCorrectedResolution(orig_width, orig_height, par)
                                            print("  PAR Info: " .. par_reason)
                                        end

                                        -- Group key is the source (PAR-corrected) resolution.
                                        -- Scaling is applied per-group at timeline creation time.
                                        local group_key = corrected_width .. "x" .. corrected_height

                                        local start_frame, end_frame
                                        local frame_success = pcall(function()
                                            start_frame = track_item:GetSourceStartFrame()
                                            end_frame   = track_item:GetSourceEndFrame()
                                        end)

                                        -- Single-frame / still clips have startFrame == endFrame.
                                        -- AppendToTimeline silently skips them in that case.
                                        -- Use the timeline item's own duration to derive the
                                        -- correct endFrame instead.
                                        if frame_success and start_frame and end_frame then
                                            if start_frame == end_frame then
                                                local tl_duration = 0
                                                pcall(function()
                                                    tl_duration = track_item:GetDuration()
                                                end)
                                                if tl_duration and tl_duration > 1 then
                                                    end_frame = start_frame + tl_duration - 1
                                                else
                                                    end_frame = start_frame + 1
                                                end
                                                print("  Single-frame clip detected, adjusted endFrame to: " .. end_frame)
                                            end
                                        end

                                        if frame_success and start_frame and end_frame then
                                            local timeline_inpoint = 0
                                            pcall(function()
                                                timeline_inpoint = track_item:GetStart()
                                            end)

                                            local clip_info = {
                                                mediaPoolItem      = media_item,
                                                startFrame         = start_frame,
                                                endFrame           = end_frame,
                                                timelineInpoint    = timeline_inpoint,
                                                resolution         = group_key,
                                                originalResolution = resolution,
                                                par                = par,
                                                parCorrected       = correct_par and par ~= 1.0,
                                                sourceTimeline     = base_timeline,
                                                sourceTimelineName = base_timeline:GetName(),
                                                versionName        = version_name
                                            }

                                            if not clipsByResolution[group_key] then
                                                clipsByResolution[group_key] = {}
                                            end
                                            table.insert(clipsByResolution[group_key], clip_info)

                                            local display_info = item_name .. " (" .. resolution .. ")"
                                            if version_name then
                                                display_info = display_info .. " [Version: " .. version_name .. "]"
                                            end
                                            if correct_par and par ~= 1.0 then
                                                display_info = display_info .. " PAR:" ..
                                                               string.format("%.2f", par) .. " -> " .. group_key
                                            end
                                            print("  Found clip: " .. display_info)
                                        end
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    if next(clipsByResolution) == nil then
        print("No valid clips found to process.")
        return
    end

    -- ── Preview groups ────────────────────────────────────────────────────
    print("\nClips grouped by resolution:")
    for resolution, clips in pairs(clipsByResolution) do
        local display_res = resolution
        local sample_clip = clips[1]

        if sample_clip.parCorrected then
            display_res = sample_clip.originalResolution ..
                          " (PAR " .. string.format("%.2f", sample_clip.par) .. ") -> " .. resolution
        end

        if scale_mode ~= "No Scaling" then
            local orig_w, orig_h = parseResolution(resolution)
            if orig_w and orig_h then
                local _, fw, fh = shouldApplyScaling(orig_w, orig_h, scale_mode, target_size, keep_even, no_upscale)
                display_res = display_res .. " -> " .. fw .. "x" .. fh
            end
        end

        print("  " .. display_res .. ": " .. #clips .. " clip(s)")
    end

    -- ── Create one timeline per resolution group ───────────────────────────
    local created_timelines = 0
    local total_names_set   = 0

    for resolution, clip_infos in pairs(clipsByResolution) do
        print("\nProcessing resolution group: " .. resolution)

        local sample_clip = clip_infos[1]

        if sample_clip.parCorrected then
            print("  PAR-corrected: " .. sample_clip.originalResolution ..
                  " (PAR " .. string.format("%.2f", sample_clip.par) .. ") -> " .. resolution)
        end

        -- Sorting
        print("Sorting clips: " .. sorting_method)
        if sorting_method == "Source Inpoint" then
            table.sort(clip_infos, function(a, b) return a.startFrame < b.startFrame end)

        elseif sorting_method == "Source Name" then
            table.sort(clip_infos, function(a, b)
                local na, nb = "", ""
                pcall(function() na = a.mediaPoolItem:GetName() end)
                pcall(function() nb = b.mediaPoolItem:GetName() end)
                if na == nb then return a.timelineInpoint < b.timelineInpoint end
                return na < nb
            end)

        elseif sorting_method == "Inpoint on Timeline" then
            table.sort(clip_infos, function(a, b) return a.timelineInpoint < b.timelineInpoint end)

        elseif sorting_method == "Reel Name" then
            table.sort(clip_infos, function(a, b)
                local ra, rb, na, nb = "", "", "", ""
                pcall(function()
                    ra = a.mediaPoolItem:GetClipProperty("Reel Name") or ""
                    na = a.mediaPoolItem:GetName() or ""
                end)
                pcall(function()
                    rb = b.mediaPoolItem:GetClipProperty("Reel Name") or ""
                    nb = b.mediaPoolItem:GetName() or ""
                end)
                if ra ~= "" and rb ~= "" then
                    if ra ~= rb then return ra < rb end
                    return a.timelineInpoint < b.timelineInpoint
                elseif ra ~= "" then return true
                elseif rb ~= "" then return false
                else
                    if na ~= nb then return na < nb end
                    return a.timelineInpoint < b.timelineInpoint
                end
            end)
        end

        -- Determine final resolution
        local orig_w, orig_h = parseResolution(resolution)
        local apply_scale, final_width, final_height, scale_reason =
            shouldApplyScaling(orig_w, orig_h, scale_mode, target_size, keep_even, no_upscale)

        print(scale_reason)

        -- Build timeline name
        -- Format: <source_timeline>_EXPORT_<source_res>[_PAR][_<final_w>x<final_h>]
        local src_tl_name   = clip_infos[1].sourceTimelineName or ""
        local timeline_name = src_tl_name .. "_EXPORT_" .. resolution
        if sample_clip.parCorrected then
            timeline_name = timeline_name .. "_PAR"
        end
        if apply_scale then
            timeline_name = timeline_name .. "_" .. final_width .. "x" .. final_height
        end


        -- Detect existing export timeline or create a new one
        local base_timeline = clip_infos[1].sourceTimeline
        local new_timeline  = nil
        local was_rebuilt   = false

        -- Refresh project timeline lookup to catch timelines created earlier in this run
        local current_tl_count = project:GetTimelineCount()
        for tl_idx = 1, current_tl_count do
            local tl = project:GetTimelineByIndex(tl_idx)
            if tl then
                local tl_name = nil
                pcall(function() tl_name = tl:GetName() end)
                if tl_name then project_timelines[tl_name] = tl end
            end
        end

        if project_timelines[timeline_name] then
            -- Timeline already exists — clear and reuse it
            new_timeline = project_timelines[timeline_name]
            print("Existing timeline found, rebuilding: " .. timeline_name)
            pcall(function() project:SetCurrentTimeline(new_timeline) end)
            clearTimelineClips(new_timeline)
            was_rebuilt = true
        else
            -- Ensure new timeline lands in the same bin as the source timeline
            media_pool:SetCurrentFolder(selected_bin)
            new_timeline = duplicateTimeline(project, media_pool, base_timeline, timeline_name)

            if not new_timeline then
                print("Fallback: Creating new empty timeline")
                pcall(function()
                    new_timeline = media_pool:CreateEmptyTimeline(timeline_name)
                end)

                if new_timeline then
                    print("  Created new timeline (verify 'Use Project Settings' is disabled: " .. timeline_name .. ")")
                else
                    print("Failed to create timeline: " .. timeline_name)
                    goto continue_resolution
                end
            end
        end

        created_timelines = created_timelines + 1
        if was_rebuilt then
            print("Rebuilt timeline: " .. timeline_name)
        else
            print("Created timeline: " .. timeline_name)
        end

        pcall(function() project:SetCurrentTimeline(new_timeline) end)
        if not was_rebuilt then
            clearTimelineClips(new_timeline)
        end

        -- Apply resolution
        if final_width and final_height then
            print("Setting resolution to: " .. final_width .. "x" .. final_height)

            local use_project_settings = nil
            pcall(function()
                use_project_settings = new_timeline:GetSetting("useProjectSettings") or
                                       new_timeline:GetSetting("UseProjectSettings")
            end)

            print("  'Use Project Settings': " .. tostring(use_project_settings))

            if use_project_settings == "1" or use_project_settings == 1 or use_project_settings == true then
                print("  WARNING: 'Use Project Settings' still enabled - custom resolution will be ignored!")
            end

            local width_set  = false
            local height_set = false

            for _, prop in ipairs({"timelineResolutionWidth", "TimelineResolutionWidth", "resolutionWidth"}) do
                pcall(function()
                    if new_timeline:SetSetting(prop, tostring(final_width)) then
                        width_set = true
                        print("  Set width via property: " .. prop)
                    end
                end)
                if width_set then break end
            end

            for _, prop in ipairs({"timelineResolutionHeight", "TimelineResolutionHeight", "resolutionHeight"}) do
                pcall(function()
                    if new_timeline:SetSetting(prop, tostring(final_height)) then
                        height_set = true
                        print("  Set height via property: " .. prop)
                    end
                end)
                if height_set then break end
            end

            if width_set and height_set then
                print("  Resolution applied")
            else
                if not width_set  then print("  Could not set width")  end
                if not height_set then print("  Could not set height") end
            end
        end

        -- Append clips
        print("Adding " .. #clip_infos .. " clips to: " .. timeline_name)

        -- Re-assert the target as the current timeline here, immediately before
        -- appending. clearTimelineClips and SetSetting calls above can cause
        -- Resolve to silently switch the active timeline internally.
        pcall(function() project:SetCurrentTimeline(new_timeline) end)

        local append_success_count = 0
        local append_error_count   = 0
        local name_set_count       = 0

        for i, clip_info in ipairs(clip_infos) do
            local clip_name = "Unknown"
            pcall(function() clip_name = clip_info.mediaPoolItem:GetName() end)
            print("  Adding clip #" .. i .. ": " .. clip_name)

            local items_before = getAllTimelineItems(new_timeline)

            local clean_clip_info = {
                mediaPoolItem = clip_info.mediaPoolItem,
                startFrame    = clip_info.startFrame,
                endFrame      = clip_info.endFrame,
            }

            local appended = nil
            pcall(function()
                appended = media_pool:AppendToTimeline({clean_clip_info})
            end)

            local items_after = getAllTimelineItems(new_timeline)

            if appended and type(appended) == "table" and #appended > 0 then
                -- AppendToTimeline returned the new item(s) directly — use them
                append_success_count = append_success_count + 1
                local new_item = appended[1]

                local clip_color = timeline_colors[clip_info.sourceTimelineName]
                if clip_color then
                    pcall(function() new_item:SetClipColor(clip_color) end)
                end

                if clip_info.versionName then
                    local name_ok = setTimelineItemVersionName(new_item, clip_info.versionName)
                    if name_ok then
                        print("    Set version name: " .. clip_info.versionName)
                        name_set_count = name_set_count + 1
                        if auto_rename_clips then
                            pcall(function() new_item:SetName(clip_info.versionName) end)
                        end
                    else
                        print("    Failed to set version name: " .. clip_info.versionName)
                    end
                end

            elseif #items_after > #items_before then
                -- AppendToTimeline did not return items but the count grew — fall back
                -- to grabbing the last item on the timeline
                append_success_count = append_success_count + 1
                local new_item = items_after[#items_after]

                local clip_color = timeline_colors[clip_info.sourceTimelineName]
                if clip_color then
                    pcall(function() new_item:SetClipColor(clip_color) end)
                end

                if clip_info.versionName then
                    local name_ok = setTimelineItemVersionName(new_item, clip_info.versionName)
                    if name_ok then
                        print("    Set version name (fallback): " .. clip_info.versionName)
                        name_set_count = name_set_count + 1
                        if auto_rename_clips then
                            pcall(function() new_item:SetName(clip_info.versionName) end)
                        end
                    else
                        print("    Failed to set version name: " .. clip_info.versionName)
                    end
                end

            else
                print("    FAILED to add clip (silent reject): " .. clip_name ..
                    " | start=" .. tostring(clip_info.startFrame) ..
                    " end=" .. tostring(clip_info.endFrame))
                append_error_count = append_error_count + 1
            end
        end

        print("Timeline " .. timeline_name .. ": added " .. append_success_count ..
              ", failed " .. append_error_count)
        if name_set_count > 0 then
            print("  Version names set: " .. name_set_count .. " / " .. append_success_count)
            if auto_rename_clips then
                print("  Clip display names set to shot names: " .. name_set_count)
            end
            total_names_set = total_names_set + name_set_count
        end

        if video_only then
            print("Removing audio tracks from: " .. timeline_name)
            removeAllAudioTracks(new_timeline)
        end

        -- Final verification
        if final_width and final_height then
            pcall(function()
                local fw_check   = new_timeline:GetSetting("timelineResolutionWidth")
                local fh_check   = new_timeline:GetSetting("timelineResolutionHeight")
                local use_proj   = new_timeline:GetSetting("useProjectSettings")

                print("Verification for " .. timeline_name .. ":")
                print("  Resolution        : " .. tostring(fw_check) .. "x" .. tostring(fh_check))
                if sample_clip.parCorrected then
                    print("  (PAR-corrected from " .. sample_clip.originalResolution ..
                          " PAR " .. string.format("%.2f", sample_clip.par) .. ")")
                end
                if apply_scale then
                    print("  (Proportional scaling: " .. scale_reason .. ")")
                end
                print("  Use Project Settings: " .. tostring(use_proj))

                if fw_check == tostring(final_width) and fh_check == tostring(final_height) then
                    print("  Timeline resolution OK")
                else
                    print("  MISMATCH - Expected: " .. final_width .. "x" .. final_height ..
                          ", Got: " .. tostring(fw_check) .. "x" .. tostring(fh_check))
                    print("  Ensure 'Use Project Settings' is disabled on the base timeline.")
                end
            end)
        end


        ::continue_resolution::
    end


    -- ── Summary ───────────────────────────────────────────────────────────
    print("\nDone. Processed " .. created_timelines .. " timeline(s) (created new or rebuilt existing).")
    if scale_mode ~= "No Scaling" then
        print("Scaling: " .. scale_mode .. " to " .. target_size .. "px" ..
              (keep_even and " (even-snapped)" or ""))
    end
    print("Note: If resolutions were not applied, verify 'Use Project Settings' is disabled on base timelines.")
    if total_names_set > 0 then
        if auto_rename_clips then
            print("Version names preserved and clip display names set to shot names.")
        else
            print("Version names set: " .. total_names_set ..
                  " - apply as clip names with %{Version} in Inspector.")
        end
    end
end

-- Run
main()
