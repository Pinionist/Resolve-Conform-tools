--[[
Resolution-Based Timeline Generator v2.1 - Modified to Preserve Version Names
This script copies existing timelines (that have "Use Project Settings" disabled)
and creates new versions for each resolution found in the clips.
Each timeline will be named EXPORT_<resolution> and contain only clips matching that resolution.

IMPORTANT: Before running this script, create your base timelines and manually:
1. Right-click timeline > Timeline Settings
2. Uncheck "Use Project Settings"
3. Set any custom resolution (this will be overwritten by the script)

MODIFICATION: Now preserves Color page version names and custom clip names from the source timeline.
- If clips have Color page version names (set by TimelineClipsRenamer), those will be preserved
- If clips have custom timeline names different from media names, those will be preserved as version names
- After running, select all clips and use %{Version} in Inspector to apply as clip names
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

    -- Try alternative methods to get resolution
    local clipWidth = nil
    local clipHeight = nil

    -- Try to get width and height separately
    pcall(function()
        clipWidth = mediaPoolItem:GetClipProperty("Width")
        clipHeight = mediaPoolItem:GetClipProperty("Height")
    end)

    if clipWidth and clipHeight then
        return clipWidth .. "x" .. clipHeight
    end

    -- If we can't get resolution, return "Unknown"
    return "Unknown"
end

-- Function to get pixel aspect ratio
function getPixelAspectRatio(mediaPoolItem)
    if not mediaPoolItem then
        return 1.0
    end
    
    local par = nil
    local success = pcall(function()
        par = mediaPoolItem:GetClipProperty("PAR")
        if not par then
            par = mediaPoolItem:GetClipProperty("Pixel Aspect Ratio")
        end
        if not par then
            par = mediaPoolItem:GetClipProperty("PixelAspectRatio")
        end
    end)
    
    if success and par then
        local par_num = tonumber(par)
        if par_num and par_num > 0 then
            return par_num
        end
    end
    
    -- Default to square pixels if we can't get PAR
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
    
    -- Calculate corrected height: new_height = original_height / PAR
    local corrected_height = math.floor(height / par)
    
    -- Make sure height is even for codec compatibility
    if corrected_height % 2 ~= 0 then
        corrected_height = corrected_height - 1
    end
    
    local reason = string.format("PAR correction: %dx%d (PAR %.2f) → %dx%d", 
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

    -- Try to match WIDTHxHEIGHT pattern
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

-- Function to calculate half resolution with even numbers
function calculateHalfResolution(width, height)
    -- Divide by 2 and ensure even numbers for codec compatibility
    local half_width = math.floor(width / 2)
    local half_height = math.floor(height / 2)
    
    -- Make sure dimensions are even
    if half_width % 2 ~= 0 then
        half_width = half_width - 1
    end
    if half_height % 2 ~= 0 then
        half_height = half_height - 1
    end
    
    return half_width, half_height
end

-- Function to determine if half resolution should be applied
function shouldApplyHalfResolution(width, height, half_resolution, keep_source_if_small)
    if not half_resolution then
        return false, width, height, "Half resolution not requested"
    end
    
    if not width or not height then
        return false, width, height, "Invalid resolution values"
    end
    
    local half_width, half_height = calculateHalfResolution(width, height)
    
    if keep_source_if_small and half_height < 1080 then
        return false, width, height, "Half resolution height (" .. half_height .. ") would be less than 1080px, keeping source resolution"
    end
    
    return true, half_width, half_height, "Applying half resolution: " .. width .. "x" .. height .. " → " .. half_width .. "x" .. half_height
end

-- Function to get timeline item's version name (Color page version) or fallback to clip name
function getTimelineItemVersionName(timeline_item)
    if not timeline_item then
        return nil
    end
    
    local version_name = nil
    local debug_info = ""
    
    local success = pcall(function()
        -- Method 1: Try to get current version
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
        
        -- Method 2: Try to get version list
        if not version_name then
            local version_list = timeline_item:GetVersionNameList()
            if version_list and #version_list > 0 then
                debug_info = debug_info .. "Version list has " .. #version_list .. " items. "
                for i, v_name in ipairs(version_list) do
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
        
        -- Method 3: Fallback to regular clip name if no custom version name found
        if not version_name then
            local clip_name = timeline_item:GetName()
            if clip_name and clip_name ~= "" then
                -- Check if this looks like a custom name (not just the media file name)
                local media_item = timeline_item:GetMediaPoolItem()
                local media_name = ""
                if media_item then
                    media_name = media_item:GetName() or ""
                end
                
                -- If clip name is different from media name, it's likely a custom name
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
    
    -- Debug output only if we have interesting info
    if version_name or debug_info ~= "No current version. No version list. No clip name. " then
        print("    Debug: " .. debug_info)
    end
    
    if success and version_name and version_name ~= "" and version_name ~= "Version 1" then
        return version_name
    end
    
    return nil
end

-- Function to set timeline item's version name (Color page version)
function setTimelineItemVersionName(timeline_item, name)
    if not timeline_item or not name or name == "" then
        return false
    end
    
    local success = false
    pcall(function()
        -- Delete existing version name and create new one
        timeline_item:DeleteVersionByName()
        success = timeline_item:AddVersion(name, 0)
    end)
    
    return success
end

-- Function to get all timeline items (helper for tracking new clips)
function getAllTimelineItems(timeline)
    local all_items = {}
    if not timeline then
        return all_items
    end
    
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

-- Function to duplicate a timeline
function duplicateTimeline(project, media_pool, source_timeline, new_name)
    print("Attempting to duplicate timeline: " .. source_timeline:GetName() .. " to " .. new_name)
    
    -- Get current timeline count before import
    local timeline_count_before = project:GetTimelineCount()
    
    -- Try different export formats
    local export_formats = {
        {format = resolve.EXPORT_DRT, ext = ".drt", name = "DRT"},
        {format = resolve.EXPORT_AAF, ext = ".aaf", name = "AAF"}
    }
    
    for _, export_info in ipairs(export_formats) do
        print("  Trying export format: " .. export_info.name)
        
        -- Create a more reliable temp file name
        local temp_dir = os.getenv("TEMP") or os.getenv("TMP") or os.getenv("TMPDIR") or "/tmp"
        local separator = package.config:sub(1,1) -- Gets the OS path separator
        temp_file = temp_dir .. separator .. "resolve_timeline_" .. os.time() .. "_" .. math.random(1000,9999) .. export_info.ext
        
        local export_success = false
        pcall(function()
            export_success = source_timeline:Export(temp_file, export_info.format, resolve.EXPORT_NONE)
        end)
        
        if export_success then
            print("  Exported timeline to: " .. temp_file)
            
            -- Import the timeline
            local import_result = nil
            pcall(function()
                import_result = media_pool:ImportTimelineFromFile(temp_file, {timelineName = new_name})
            end)
            
            -- Clean up temp file
            pcall(function() os.remove(temp_file) end)
            
            -- Check if import was successful by comparing timeline counts
            local timeline_count_after = project:GetTimelineCount()
            if timeline_count_after > timeline_count_before then
                -- Find the newly created timeline
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
                
                -- If we can't find by name, return the last timeline (most likely the new one)
                local new_timeline = project:GetTimelineByIndex(timeline_count_after)
                if new_timeline then
                    print("  Found new timeline, attempting to rename...")
                    
                    -- Try multiple times to rename as it sometimes fails on first attempt
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
                            print("  ✓ Renamed timeline to: " .. new_name)
                            break
                        else
                            print("  Rename attempt " .. attempt .. " failed")
                        end
                    end
                    
                    if not rename_success then
                        print("  ⚠ Could not rename timeline - using temporary name")
                    end
                    
                    return new_timeline
                end
            end
        else
            print("  Failed to export with format: " .. export_info.name)
        end
    end
    
    print("  Failed to duplicate timeline using export/import method")
    return nil
end

-- Function to remove all clips from a timeline
function clearTimelineClips(timeline)
    if not timeline then
        print("Error: No timeline provided.")
        return
    end

    print("Clearing all clips from timeline...")

    local status, err = pcall(function()
        -- Get track counts
        local video_track_count = timeline:GetTrackCount("video")
        local audio_track_count = timeline:GetTrackCount("audio")
        
        -- Delete all video clips
        for i = 1, video_track_count do
            local items = timeline:GetItemListInTrack("video", i)
            if items and #items > 0 then
                print("  Deleting " .. #items .. " video items from track " .. i)
                timeline:DeleteClips(items)
            end
        end
        
        -- Delete all audio clips
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

-- Function to remove all audio tracks from a timeline
function removeAllAudioTracks(timeline)
    if timeline == nil then
        print("Error: No timeline provided.")
        return
    end

    print("Removing audio tracks from timeline...")

    local status, err = pcall(function()
        -- Get current track count
        local trackCount = timeline:GetTrackCount("audio")
        print("  Found " .. trackCount .. " audio tracks")

        -- Delete all tracks except track 1
        for i = trackCount, 2, -1 do
            timeline:DeleteTrack("audio", i)
            print("  Deleted track " .. i)
        end
    end)

    if status then
        print("  Successfully removed audio tracks.")
    else
        print("  Error: " .. tostring(err))
    end
end

-- MAIN SCRIPT EXECUTION
function main()
    -- Draw window to get user parameters.
    local ui = fu.UIManager
    local disp = bmd.UIDispatcher(ui)
    local width, height = 450, 340

    win = disp:AddWindow({
        ID = "MyWin",
        WindowTitle = "Generate Resolution-Based Timelines v2.1",
        Geometry = {100, 100, width, height},
        Spacing = 10,
        ui:VGroup{
            ID = "root",
            ui:Label{
                ID = "instructionLabel",
                Text = "Select base timelines with 'Use Project Settings' disabled.",
                Weight = 0,
                Font = ui:Font{
                    PixelSize = 12,
                    StyleName = "Bold"
                }
            },
            ui:Label{
                ID = "instructionLabel2",
                Text = "Script will copy them and set resolution based on clips.",
                Weight = 0,
                Font = ui:Font{
                    PixelSize = 11
                }
            },
            ui:HGroup{
                ui:Label{
                    ID = "selectionMethodLabel",
                    Text = "Select Base Timelines:"
                },
                ui:ComboBox{
                    ID = "selectionMethod",
                    Text = "Selected in Media Pool"
                }
            },
            ui:HGroup{
                ui:Label{
                    ID = "sortingMethodLabel",
                    Text = "Sort Clips By:"
                },
                ui:ComboBox{
                    ID = "sortingMethod",
                    Text = "Source Name"
                }
            },
            ui:CheckBox{
                ID = "includeDisabledItems",
                Text = "Include Disabled Clips"
            },
            ui:CheckBox{
                ID = "videoOnly",
                Text = "Video Only (No Audio)",
                Checked = true
            },
            ui:CheckBox{
                ID = "halfResolution",
                Text = "Create Half Resolution Timelines (50%)",
                Checked = false
            },
            ui:CheckBox{
                ID = "keepSourceIfSmall",
                Text = "Keep source resolution if half < 1080p height",
                Checked = true
            },
            ui:CheckBox{
                ID = "correctPAR",
                Text = "Correct non-square pixel aspect ratios",
                Checked = false
            },
            ui:HGroup{
                ID = "buttons",
                ui:Button{
                    ID = "cancelButton",
                    Text = "Cancel"
                },
                ui:Button{
                    ID = "goButton",
                    Text = "Go"
                }
            }
        }
    })

    run_export = false

    -- The window was closed
    function win.On.MyWin.Close(ev)
        disp:ExitLoop()
        run_export = false
    end

    function win.On.cancelButton.Clicked(ev)
        print("Cancel Clicked")
        disp:ExitLoop()
        run_export = false
    end

    function win.On.goButton.Clicked(ev)
        print("Go Clicked")
        disp:ExitLoop()
        run_export = true
    end

    -- Add your GUI element based event functions here:
    itm = win:GetItems()
    itm.selectionMethod:AddItem('Selected in Media Pool')
    itm.selectionMethod:AddItem('All in Current Bin')

    -- Add sorting method options
    itm.sortingMethod:AddItem('Source Name')
    itm.sortingMethod:AddItem('Source Inpoint')
    itm.sortingMethod:AddItem('Inpoint on Timeline')
    itm.sortingMethod:AddItem('Reel Name')
    itm.sortingMethod:AddItem('None')

    win:Show()
    disp:RunLoop()
    win:Hide()

    if run_export then
        allow_disabled_clips = itm.includeDisabledItems.Checked
        video_only = itm.videoOnly.Checked
        half_resolution = itm.halfResolution.Checked
        keep_source_if_small = itm.keepSourceIfSmall.Checked
        correct_par = itm.correctPAR.Checked
        sorting_method = itm.sortingMethod.CurrentText

        -- Get timelines
        resolve = Resolve()
        projectManager = resolve:GetProjectManager()
        project = projectManager:GetCurrentProject()
        media_pool = project:GetMediaPool()
        num_timelines = project:GetTimelineCount()
        selected_bin = media_pool:GetCurrentFolder()

        -- Initialize table to store clips grouped by resolution
        local clipsByResolution = {}

        -- Get all project timelines
        project_timelines = {}
        for timeline_idx = 1, num_timelines do
            runner_timeline = project:GetTimelineByIndex(timeline_idx)
            if runner_timeline then
                local timeline_name = nil
                pcall(function()
                    timeline_name = runner_timeline:GetName()
                end)
                if timeline_name then
                    project_timelines[timeline_name] = runner_timeline
                end
            end
        end

        -- Get selected timelines (base timelines to copy)
        local selected_items = {}
        local base_timelines = {}
        
        if itm.selectionMethod.CurrentText == "All in Current Bin" then
            if selected_bin then
                local bin_clips = selected_bin:GetClipList()
                if bin_clips then
                    selected_items = bin_clips
                end
            end
        else -- "Selected in Media Pool"
            local sel_clips = media_pool:GetSelectedClips()
            if sel_clips then
                selected_items = sel_clips
            end
        end

        -- Filter selected items to get only timelines
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

        print("Processing " .. #base_timelines .. " base timelines...")

        -- Process each base timeline to collect clips and their resolutions
        for _, base_timeline in ipairs(base_timelines) do
            local timeline_name = base_timeline:GetName()
            print("\nProcessing base timeline: " .. timeline_name)
            
            -- Check base timeline settings
            print("Checking base timeline settings:")
            local base_use_project = nil
            local base_width = nil
            local base_height = nil
            
            pcall(function()
                base_use_project = base_timeline:GetSetting("useProjectSettings") or base_timeline:GetSetting("UseProjectSettings")
                base_width = base_timeline:GetSetting("timelineResolutionWidth")
                base_height = base_timeline:GetSetting("timelineResolutionHeight")
            end)
            
            print("  Use Project Settings: " .. tostring(base_use_project))
            print("  Current Resolution: " .. tostring(base_width) .. "x" .. tostring(base_height))
            
            if base_use_project == "1" or base_use_project == 1 or base_use_project == true then
                print("  ⚠ WARNING: Base timeline has 'Use Project Settings' enabled!")
                print("  ⚠ Please disable it manually before running the script")
            end

            local num_tracks = 0
            pcall(function() num_tracks = base_timeline:GetTrackCount("video") end)
            
            for track_idx = 1, num_tracks do
                local track_items = nil
                pcall(function() track_items = base_timeline:GetItemListInTrack("video", track_idx) end)
                
                if track_items then
                    for item_index, track_item in ipairs(track_items) do
                        if track_item then
                            -- Try to get name for better error reporting
                            local item_name = "Unknown"
                            pcall(function() item_name = track_item:GetName() end)

                            -- Get the version name (Color page version) instead of timeline clip name
                            local version_name = getTimelineItemVersionName(track_item)
                            if version_name then
                                print("    ✓ Found version name: " .. version_name)
                            else
                                print("    • No version name found for: " .. item_name)
                            end

                            -- Check if clip is enabled
                            local is_enabled = true
                            pcall(function() is_enabled = track_item:GetClipEnabled() end)

                            if allow_disabled_clips or is_enabled then
                                local media_item = nil
                                local get_media_success = pcall(function()
                                    media_item = track_item:GetMediaPoolItem()
                                end)

                                if get_media_success and media_item then
                                    -- Get clip resolution and PAR
                                    local resolution = getClipResolution(media_item)
                                    local par = getPixelAspectRatio(media_item)
                                    
                                    if resolution ~= "Unknown" then
                                        -- Parse the original resolution
                                        local orig_width, orig_height = parseResolution(resolution)
                                        
                                        if orig_width and orig_height then
                                            -- Calculate PAR-corrected resolution if enabled
                                            local corrected_width = orig_width
                                            local corrected_height = orig_height
                                            local par_reason = ""
                                            
                                            if correct_par then
                                                corrected_width, corrected_height, par_reason = calculatePARCorrectedResolution(orig_width, orig_height, par)
                                                print("  PAR Info: " .. par_reason)
                                            end
                                            
                                            -- Create the corrected resolution string for grouping
                                            local final_resolution = corrected_width .. "x" .. corrected_height
                                            
                                            -- Get source frame range
                                            local start_frame, end_frame
                                            local frame_success = pcall(function()
                                                start_frame = track_item:GetSourceStartFrame()
                                                end_frame = track_item:GetSourceEndFrame()
                                            end)

                                            if frame_success and start_frame and end_frame then
                                                -- Get timeline inpoint
                                                local timeline_inpoint = 0
                                                pcall(function()
                                                    timeline_inpoint = track_item:GetStart()
                                                end)

                                                -- Create the clip info
                                                local clip_info = {
                                                    mediaPoolItem = media_item,
                                                    startFrame = start_frame,
                                                    endFrame = end_frame,
                                                    timelineInpoint = timeline_inpoint,
                                                    resolution = final_resolution,
                                                    originalResolution = resolution,
                                                    par = par,
                                                    parCorrected = correct_par and par ~= 1.0,
                                                    sourceTimeline = base_timeline,
                                                    versionName = version_name  -- NEW: Store version name instead of custom clip name
                                                }

                                                -- Add to resolution group (using final corrected resolution)
                                                if not clipsByResolution[final_resolution] then
                                                    clipsByResolution[final_resolution] = {}
                                                end

                                                table.insert(clipsByResolution[final_resolution], clip_info)
                                                
                                                local display_info = item_name .. " (" .. resolution .. ")"
                                                if version_name then
                                                    display_info = display_info .. " [Version: " .. version_name .. "]"
                                                end
                                                if correct_par and par ~= 1.0 then
                                                    display_info = display_info .. " PAR:" .. string.format("%.2f", par) .. " → " .. final_resolution
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

        print("\nClips grouped by resolution:")
        for resolution, clips in pairs(clipsByResolution) do
            local display_res = resolution
            local sample_clip = clips[1] -- Get first clip to check for PAR correction
            
            -- Show PAR correction info if applicable
            if sample_clip.parCorrected then
                display_res = sample_clip.originalResolution .. " (PAR " .. string.format("%.2f", sample_clip.par) .. ") → " .. resolution
            end
            
            -- Show half resolution info if applicable
            if half_resolution then
                local w, h = parseResolution(resolution)
                if w and h then
                    local apply_half, final_w, final_h, reason = shouldApplyHalfResolution(w, h, half_resolution, keep_source_if_small)
                    if apply_half then
                        display_res = display_res .. " → " .. final_w .. "x" .. final_h .. " (half)"
                    else
                        display_res = display_res .. " (keeping resolution - " .. reason .. ")"
                    end
                end
            end
            print("  " .. display_res .. ": " .. #clips .. " clips")
        end

        -- Create timelines for each resolution
        local created_timelines = 0
        local total_names_set = 0  -- Initialize properly at the right scope
        for resolution, clip_infos in pairs(clipsByResolution) do
            print("\nCreating timeline for resolution: " .. resolution)
            
            local sample_clip = clip_infos[1] -- Get first clip to check for PAR correction info
            
            -- Show what resolution processing is happening
            if sample_clip.parCorrected then
                print("  PAR-corrected resolution: " .. sample_clip.originalResolution .. 
                      " (PAR " .. string.format("%.2f", sample_clip.par) .. ") → " .. resolution)
            else
                print("  Source resolution: " .. resolution)
            end

            -- Apply the selected sorting method
            print("Sorting clips using method: " .. sorting_method)
            if sorting_method == "Source Inpoint" then
                table.sort(clip_infos, function(a, b)
                    return a.startFrame < b.startFrame
                end)
            elseif sorting_method == "Source Name" then
                table.sort(clip_infos, function(a, b)
                    local name_a = ""
                    local name_b = ""
                    pcall(function() name_a = a.mediaPoolItem:GetName() end)
                    pcall(function() name_b = b.mediaPoolItem:GetName() end)

                    if name_a == name_b then
                        return a.timelineInpoint < b.timelineInpoint
                    end

                    return name_a < name_b
                end)
            elseif sorting_method == "Inpoint on Timeline" then
                table.sort(clip_infos, function(a, b)
                    return a.timelineInpoint < b.timelineInpoint
                end)
            elseif sorting_method == "Reel Name" then
                table.sort(clip_infos, function(a, b)
                    local reel_name_a = ""
                    local reel_name_b = ""
                    local name_a = ""
                    local name_b = ""
                    
                    pcall(function() 
                        reel_name_a = a.mediaPoolItem:GetClipProperty("Reel Name") or ""
                        name_a = a.mediaPoolItem:GetName() or ""
                    end)
                    pcall(function() 
                        reel_name_b = b.mediaPoolItem:GetClipProperty("Reel Name") or ""
                        name_b = b.mediaPoolItem:GetName() or ""
                    end)

                    if reel_name_a ~= "" and reel_name_b ~= "" then
                        if reel_name_a ~= reel_name_b then
                            return reel_name_a < reel_name_b
                        end
                        return a.timelineInpoint < b.timelineInpoint
                    elseif reel_name_a ~= "" and reel_name_b == "" then
                        return true
                    elseif reel_name_a == "" and reel_name_b ~= "" then
                        return false
                    else
                        if name_a ~= name_b then
                            return name_a < name_b
                        end
                        return a.timelineInpoint < b.timelineInpoint
                    end
                end)
            elseif sorting_method == "None" then
                print("No sorting applied")
            end

            -- Parse resolution to get width and height
            local original_width, original_height = parseResolution(resolution)
            
            -- Determine final resolution based on half resolution settings
            local apply_half, final_width, final_height, reason = shouldApplyHalfResolution(original_width, original_height, half_resolution, keep_source_if_small)
            
            print(reason)

            -- Create timeline name
            local timeline_name = "EXPORT_" .. resolution
            if sample_clip.parCorrected then
                timeline_name = timeline_name .. "_PAR"
            end
            if apply_half then
                timeline_name = timeline_name .. "_HALF"
            end

            -- Use the first clip's source timeline as the base to duplicate
            local base_timeline = clip_infos[1].sourceTimeline
            
            -- Duplicate the base timeline
            local new_timeline = duplicateTimeline(project, media_pool, base_timeline, timeline_name)
            
            if not new_timeline then
                -- Fallback: Create a new timeline directly
                print("Fallback: Creating new timeline directly")
                pcall(function()
                    new_timeline = media_pool:CreateEmptyTimeline(timeline_name)
                end)
                
                if new_timeline then
                    print("  Created new timeline (Note: 'Use Project Settings' may be enabled)")
                    print("  You may need to manually disable 'Use Project Settings' for: " .. timeline_name)
                else
                    print("Failed to create timeline: " .. timeline_name)
                    goto continue_resolution
                end
            end

            created_timelines = created_timelines + 1
            print("Created timeline: " .. timeline_name)

            -- Set as current timeline
            pcall(function()
                project:SetCurrentTimeline(new_timeline)
            end)

            -- Clear existing clips from the duplicated timeline
            clearTimelineClips(new_timeline)

            -- Now set the resolution (should work since "Use Project Settings" is disabled)
            if final_width and final_height then
                print("Setting resolution to: " .. final_width .. "x" .. final_height)
                
                -- First check if Use Project Settings is disabled
                local use_project_settings = nil
                pcall(function()
                    use_project_settings = new_timeline:GetSetting("useProjectSettings")
                    if not use_project_settings then
                        use_project_settings = new_timeline:GetSetting("UseProjectSettings")
                    end
                end)
                
                print("  'Use Project Settings' status: " .. tostring(use_project_settings))
                
                if use_project_settings == "1" or use_project_settings == 1 or use_project_settings == true then
                    print("  ⚠ WARNING: 'Use Project Settings' is still enabled!")
                    print("  ⚠ Timeline will use project resolution instead of custom resolution")
                    print("  ⚠ Please manually disable 'Use Project Settings' for timeline: " .. timeline_name)
                end
                
                -- Try to set resolution anyway
                local width_set = false
                local height_set = false
                
                -- Try different property names
                local width_properties = {"timelineResolutionWidth", "TimelineResolutionWidth", "resolutionWidth"}
                local height_properties = {"timelineResolutionHeight", "TimelineResolutionHeight", "resolutionHeight"}
                
                for _, prop in ipairs(width_properties) do
                    pcall(function()
                        if new_timeline:SetSetting(prop, tostring(final_width)) then
                            width_set = true
                            print("  Set width using property: " .. prop)
                        end
                    end)
                    if width_set then break end
                end
                
                for _, prop in ipairs(height_properties) do
                    pcall(function()
                        if new_timeline:SetSetting(prop, tostring(final_height)) then
                            height_set = true
                            print("  Set height using property: " .. prop)
                        end
                    end)
                    if height_set then break end
                end
                
                if width_set and height_set then
                    print("  ✓ Resolution settings applied")
                else
                    print("  ✗ Failed to set resolution")
                    if not width_set then print("    Could not set width") end
                    if not height_set then print("    Could not set height") end
                end
            end

            -- Add clips to the timeline
            print("Adding " .. #clip_infos .. " clips to timeline: " .. timeline_name)

            local append_success_count = 0
            local append_error_count = 0
            local name_set_count = 0  -- Make sure this is properly initialized

            for i, clip_info in ipairs(clip_infos) do
                local clip_name = "Unknown"
                pcall(function() clip_name = clip_info.mediaPoolItem:GetName() end)
                print("  Adding clip #" .. i .. ": " .. clip_name)

                -- Get timeline items before adding new clip
                local items_before = getAllTimelineItems(new_timeline)

                local success = pcall(function()
                    media_pool:AppendToTimeline({clip_info})
                end)

                if success then
                    append_success_count = append_success_count + 1
                    
                    -- If there's a version name, try to set it on the newly added clip
                    if clip_info.versionName then
                        -- Get timeline items after adding new clip
                        local items_after = getAllTimelineItems(new_timeline)
                        
                        -- Find the newly added item (should be the last one if items_after is longer)
                        if #items_after > #items_before then
                            local new_item = items_after[#items_after]
                            if new_item then
                                local name_success = setTimelineItemVersionName(new_item, clip_info.versionName)
                                if name_success then
                                    print("    ✓ Set version name: " .. clip_info.versionName)
                                    name_set_count = name_set_count + 1
                                else
                                    print("    ⚠ Failed to set version name: " .. clip_info.versionName)
                                end
                            end
                        end
                    end
                else
                    print("    Failed to add clip: " .. clip_name)
                    append_error_count = append_error_count + 1
                end
            end

            print("Timeline " .. timeline_name .. " - Added " .. append_success_count ..
                  " clips successfully, " .. append_error_count .. " failed")
            if name_set_count > 0 then
                print("  Version names set: " .. name_set_count .. " out of " .. append_success_count)
                total_names_set = (total_names_set or 0) + name_set_count
            end

            -- Remove audio if video only option is selected
            if video_only then
                print("Removing audio tracks from timeline: " .. timeline_name)
                removeAllAudioTracks(new_timeline)
            end

            -- Final verification of timeline resolution
            print("Final verification for timeline: " .. timeline_name)
            if final_width and final_height then
                pcall(function()
                    local final_width_check = new_timeline:GetSetting("timelineResolutionWidth")
                    local final_height_check = new_timeline:GetSetting("timelineResolutionHeight")
                    local use_project = new_timeline:GetSetting("useProjectSettings")

                    print("  Final settings:")
                    print("    Resolution: " .. tostring(final_width_check) .. "x" .. tostring(final_height_check))
                    
                    if sample_clip.parCorrected then
                        print("    (PAR-corrected from " .. sample_clip.originalResolution .. 
                              " with PAR " .. string.format("%.2f", sample_clip.par) .. ")")
                    end
                    
                    if apply_half then
                        print("    (Half resolution applied)")
                    end
                    
                    print("    Use Project Settings: " .. tostring(use_project))

                    if final_width_check == tostring(final_width) and final_height_check == tostring(final_height) then
                        print("  ✓ Timeline resolution correctly set!")
                    else
                        print("  ⚠ Resolution mismatch - Expected: " .. final_width .. "x" .. final_height .. 
                              ", Got: " .. tostring(final_width_check) .. "x" .. tostring(final_height_check))
                        print("  ⚠ Make sure 'Use Project Settings' is disabled on the base timeline!")
                    end
                end)
            end

            ::continue_resolution::
        end

        print("\nDone! Created " .. created_timelines .. " resolution-based timelines.")
        if half_resolution then
            if keep_source_if_small then
                print("Half resolution applied only when result would be ≥ 1080p height")
            else
                print("All timelines created at HALF resolution (50%)")
            end
        end
        print("Note: If resolutions weren't set correctly, ensure base timelines have 'Use Project Settings' disabled.")
        print("Color page version names have been preserved where possible.")
        if total_names_set and total_names_set > 0 then
            print("To apply version names as clip names: Select all clips in timeline, then in Inspector use %{Version} in the clip name field.")
        end
    end
end

-- Run the main function
main()