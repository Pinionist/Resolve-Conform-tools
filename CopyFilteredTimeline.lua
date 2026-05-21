--[[
Copy Filtered Timeline v1.1
Creates a copy of the current timeline containing only clips
that have a specific clip color assigned.

Two output modes:
  • Keep Positions (default)
      Clips are deleted from the duplicate, leaving gaps.
      Original track number and timeline position are preserved exactly.

  • Delete Gaps (compact)
      After filtering, remaining clips are collected, the timeline is cleared,
      and clips are re-appended sequentially on V1, sorted by their original
      timeline inpoint across all tracks.
      NOTE: track assignment is NOT preserved in this mode — all clips land on V1.

Workflow:
  1. In Resolve's Edit page, assign a clip color to every clip you want to keep.
  2. Run this script.
  3. Choose the clip color and output mode in the dialog.
  4. A new timeline is created with the result.

Limitations:
  - The Resolve Lua API does not expose Edit-page clip selection state, so clip
    color is used as the selection proxy.
  - Audio tracks are duplicated in full; only video track clips are filtered.
    Audio is not re-sequenced in Delete Gaps mode — use "Remove Audio" if unwanted.
  - Generators and adjustment clips (no media pool item) are preserved
    unconditionally in Keep Positions mode; skipped in Delete Gaps mode.
]]--

-- ─── Helpers ─────────────────────────────────────────────────────────────────

-- Duplicate a timeline via export/import (DRT preferred, AAF fallback).
-- Returns the new timeline object, or nil on failure.
function duplicateTimeline(project, media_pool, source_timeline, new_name)
    print("Duplicating '" .. source_timeline:GetName() .. "' -> '" .. new_name .. "'")

    local timeline_count_before = project:GetTimelineCount()

    local export_formats = {
        { format = resolve.EXPORT_DRT, ext = ".drt", name = "DRT" },
        { format = resolve.EXPORT_AAF, ext = ".aaf", name = "AAF" },
    }

    for _, fmt in ipairs(export_formats) do
        print("  Trying format: " .. fmt.name)

        local temp_dir  = os.getenv("TEMP") or os.getenv("TMP") or os.getenv("TMPDIR") or "/tmp"
        local sep       = package.config:sub(1, 1)
        local temp_file = temp_dir .. sep .. "resolve_tl_" .. os.time() ..
                          "_" .. math.random(1000, 9999) .. fmt.ext

        local export_ok = false
        pcall(function()
            export_ok = source_timeline:Export(temp_file, fmt.format, resolve.EXPORT_NONE)
        end)

        if export_ok then
            print("  Exported to: " .. temp_file)

            pcall(function()
                media_pool:ImportTimelineFromFile(temp_file, { timelineName = new_name })
            end)
            pcall(function() os.remove(temp_file) end)

            local timeline_count_after = project:GetTimelineCount()
            if timeline_count_after > timeline_count_before then
                -- Search by exact name first
                for i = 1, timeline_count_after do
                    local tl = project:GetTimelineByIndex(i)
                    if tl then
                        local tl_name = nil
                        pcall(function() tl_name = tl:GetName() end)
                        if tl_name and (tl_name == new_name or string.find(tl_name, new_name, 1, true)) then
                            print("  Success: '" .. tl_name .. "'")
                            return tl
                        end
                    end
                end

                -- Fallback: last timeline in project
                local new_tl = project:GetTimelineByIndex(timeline_count_after)
                if new_tl then
                    pcall(function()
                        project:SetCurrentTimeline(new_tl)
                        new_tl:SetName(new_name)
                    end)
                    print("  Fallback: using last timeline, renamed to '" .. new_name .. "'")
                    return new_tl
                end
            end
        else
            print("  Export failed for format: " .. fmt.name)
        end
    end

    print("  ERROR: Could not duplicate timeline.")
    return nil
end

-- Generate a timeline name that does not already exist in the project.
function uniqueTimelineName(project, new_name)
    local num_timelines = project:GetTimelineCount()
    local existing = {}
    for i = 1, num_timelines do
        local tl = project:GetTimelineByIndex(i)
        if tl then
            local name = nil
            pcall(function() name = tl:GetName() end)
            if name then existing[name] = true end
        end
    end

    if not existing[new_name] then return new_name end

    local counter = 2
    while true do
        local candidate = new_name .. "_" .. counter
        if not existing[candidate] then return candidate end
        counter = counter + 1
    end
end

-- Remove all clips from a timeline (all video and audio tracks).
function clearTimelineClips(timeline)
    print("Clearing all clips from timeline...")
    pcall(function()
        local video_track_count = timeline:GetTrackCount("video")
        local audio_track_count = timeline:GetTrackCount("audio")
        for i = 1, video_track_count do
            local items = timeline:GetItemListInTrack("video", i)
            if items and #items > 0 then
                timeline:DeleteClips(items)
            end
        end
        for i = 1, audio_track_count do
            local items = timeline:GetItemListInTrack("audio", i)
            if items and #items > 0 then
                timeline:DeleteClips(items)
            end
        end
    end)
end

-- Remove all audio tracks from a timeline.
-- Clears clips first, then deletes tracks top-down.
-- The last audio track cannot be deleted by Resolve; it is left empty.
function removeAllAudioTracks(timeline)
    print("Removing audio content from timeline...")
    pcall(function()
        local atc = timeline:GetTrackCount("audio")
        print("  Found " .. atc .. " audio track(s)")
        for i = 1, atc do
            local items = timeline:GetItemListInTrack("audio", i)
            if items and #items > 0 then
                timeline:DeleteClips(items)
                print("  Cleared audio track " .. i)
            end
        end
        for i = atc, 1, -1 do
            local ok = pcall(function() timeline:DeleteTrack("audio", i) end)
            if ok then
                print("  Deleted audio track " .. i)
            else
                print("  Could not delete audio track " .. i .. " (last track — left empty)")
            end
        end
    end)
end

-- ─── MAIN ────────────────────────────────────────────────────────────────────
function main()
    local ui   = fu.UIManager
    local disp = bmd.UIDispatcher(ui)

    local clip_colors = {
        "Orange", "Apricot", "Yellow", "Lime",   "Olive",     "Green",
        "Teal",   "Navy",    "Blue",   "Purple",  "Violet",    "Pink",
        "Tan",    "Beige",   "Brown",  "Chocolate"
    }

    local win = disp:AddWindow({
        ID          = "CopyFilteredTLWin",
        WindowTitle = "Copy Filtered Timeline v1.1",
        Geometry    = { 100, 100, 480, 300 },
        Spacing     = 8,
        ui:VGroup{
            ID = "root",

            ui:Label{
                ID     = "header",
                Text   = "Copy Timeline — Keep Clips by Color",
                Weight = 0,
                Font   = ui:Font{ PixelSize = 13, StyleName = "Bold" }
            },
            ui:Label{
                ID     = "desc",
                Text   = "Assign a clip color to clips you want to keep, then run.",
                Weight = 0,
            },
            ui:Label{ ID = "sep1", Text = " ", Weight = 0 },

            ui:HGroup{
                Weight = 0,
                ui:Label{ Text = "Keep Clips With Color:", MinimumSize = { 180, 0 } },
                ui:ComboBox{ ID = "clipColor" },
            },

            ui:HGroup{
                Weight = 0,
                ui:Label{ Text = "New Timeline Suffix:", MinimumSize = { 180, 0 } },
                ui:LineEdit{
                    ID          = "suffix",
                    Text        = "_FILTERED",
                    MinimumSize = { 180, 0 },
                },
            },

            ui:CheckBox{
                ID      = "includeDisabled",
                Text    = "Treat Disabled Clips as Candidates (include in color check)",
                Weight  = 0,
                Checked = false,
            },

            ui:CheckBox{
                ID      = "deleteGaps",
                Text    = "Delete Gaps — compact clips sequentially (V1 only, track order lost)",
                Weight  = 0,
                Checked = false,
            },

            ui:CheckBox{
                ID      = "removeAudio",
                Text    = "Remove All Audio Tracks from Result",
                Weight  = 0,
                Checked = false,
            },

            ui:Label{ ID = "sep2", Text = " ", Weight = 0 },

            ui:HGroup{
                Weight = 0,
                ui:Button{ ID = "cancelBtn", Text = "Cancel" },
                ui:Button{ ID = "goBtn",     Text = "Create Filtered Timeline" },
            },
        }
    })

    local run = false

    function win.On.CopyFilteredTLWin.Close(ev)
        disp:ExitLoop()
        run = false
    end

    function win.On.cancelBtn.Clicked(ev)
        print("Cancelled.")
        disp:ExitLoop()
        run = false
    end

    function win.On.goBtn.Clicked(ev)
        disp:ExitLoop()
        run = true
    end

    local itm = win:GetItems()

    for _, color in ipairs(clip_colors) do
        itm.clipColor:AddItem(color)
    end
    itm.clipColor.CurrentIndex = 0   -- default: Orange

    win:Show()
    disp:RunLoop()
    win:Hide()

    if not run then return end

    -- ── Read GUI values ───────────────────────────────────────────────────────
    local target_color     = itm.clipColor.CurrentText
    local suffix           = itm.suffix.Text
    local include_disabled = itm.includeDisabled.Checked
    local delete_gaps      = itm.deleteGaps.Checked
    local remove_audio     = itm.removeAudio.Checked

    if suffix == "" then suffix = "_FILTERED" end

    -- ── Resolve context ───────────────────────────────────────────────────────
    resolve        = Resolve()
    projectManager = resolve:GetProjectManager()
    project        = projectManager:GetCurrentProject()
    media_pool     = project:GetMediaPool()

    local source_timeline = project:GetCurrentTimeline()
    if not source_timeline then
        print("ERROR: No active timeline. Open a timeline in the Edit page first.")
        return
    end

    local source_name = source_timeline:GetName()
    local raw_name    = source_name .. suffix
    local new_name    = uniqueTimelineName(project, raw_name)

    if new_name ~= raw_name then
        print("Name collision: '" .. raw_name .. "' already exists. Using '" .. new_name .. "'.")
    end

    print("Source timeline : " .. source_name)
    print("Filter color    : " .. target_color)
    print("New timeline    : " .. new_name)
    print("Include disabled: " .. tostring(include_disabled))
    print("Delete gaps     : " .. tostring(delete_gaps))
    print("Remove audio    : " .. tostring(remove_audio))

    -- ── Scan source timeline: build keep_set and ordered clip list ────────────
    --
    -- keep_set   : used in Keep Positions mode.
    --              key = "video_<track>_<tl_start>", value = clip display name
    --
    -- kept_clips : used in Delete Gaps mode.
    --              ordered list of {mediaPoolItem, startFrame, endFrame,
    --                               timelineInpoint, versionName, clipColor}
    --              sorted by timelineInpoint (ascending) after collection.

    local keep_set    = {}
    local kept_clips  = {}
    local keep_count  = 0
    local total_count = 0

    local video_track_count = 0
    pcall(function() video_track_count = source_timeline:GetTrackCount("video") end)

    for track_idx = 1, video_track_count do
        local items = nil
        pcall(function() items = source_timeline:GetItemListInTrack("video", track_idx) end)

        if items then
            for _, item in ipairs(items) do
                local media_item = nil
                pcall(function() media_item = item:GetMediaPoolItem() end)

                -- Generators / adjustment clips: no media pool item.
                if not media_item then
                    if not delete_gaps then
                        -- Keep Positions mode: preserve unconditionally.
                        local start_frame = nil
                        pcall(function() start_frame = item:GetStart() end)
                        if start_frame ~= nil then
                            local key = "video_" .. track_idx .. "_" .. start_frame
                            keep_set[key] = "(generator/adjustment)"
                            keep_count    = keep_count + 1
                        end
                    end
                    -- Delete Gaps mode: skip generators — cannot re-append them.
                else
                    local is_enabled = true
                    pcall(function() is_enabled = item:GetClipEnabled() end)

                    if include_disabled or is_enabled then
                        total_count = total_count + 1

                        local color = ""
                        pcall(function() color = item:GetClipColor() end)

                        local start_frame = nil
                        pcall(function() start_frame = item:GetStart() end)

                        local item_name = "?"
                        pcall(function() item_name = item:GetName() end)

                        if start_frame ~= nil and color == target_color then

                            -- Keep Positions mode: record lookup key
                            if not delete_gaps then
                                local key = "video_" .. track_idx .. "_" .. start_frame
                                keep_set[key] = item_name
                            end

                            -- Delete Gaps mode: record clip info for re-append
                            if delete_gaps then
                                local src_start, src_end = nil, nil
                                pcall(function()
                                    src_start = item:GetSourceStartFrame()
                                    src_end   = item:GetSourceEndFrame()
                                end)

                                -- Fix single-frame / still clips
                                if src_start and src_end and src_start == src_end then
                                    local dur = 0
                                    pcall(function() dur = item:GetDuration() end)
                                    src_end = src_start + (dur > 1 and dur - 1 or 1)
                                    print("  Single-frame clip adjusted: endFrame -> " .. src_end)
                                end

                                if src_start and src_end then
                                    -- Read version name (Color page) or custom clip name
                                    local version_name = nil
                                    pcall(function()
                                        local cv = item:GetCurrentVersion()
                                        if cv and cv.VersionName and cv.VersionName ~= ""
                                                and cv.VersionName ~= "Version 1" then
                                            version_name = cv.VersionName
                                        end
                                    end)
                                    if not version_name then
                                        pcall(function()
                                            local vl = item:GetVersionNameList()
                                            if vl then
                                                for _, vn in ipairs(vl) do
                                                    if vn and vn ~= "" and vn ~= "Version 1" then
                                                        version_name = vn
                                                        break
                                                    end
                                                end
                                            end
                                        end)
                                    end
                                    if not version_name then
                                        pcall(function()
                                            local cn = item:GetName()
                                            local mn = media_item:GetName()
                                            if cn and cn ~= "" and cn ~= mn then
                                                version_name = cn
                                            end
                                        end)
                                    end

                                    table.insert(kept_clips, {
                                        mediaPoolItem  = media_item,
                                        startFrame     = src_start,
                                        endFrame       = src_end,
                                        timelineInpoint = start_frame,
                                        versionName    = version_name,
                                        clipColor      = color,
                                        displayName    = item_name,
                                    })
                                end
                            end

                            keep_count = keep_count + 1
                            print("  KEEP  [V" .. track_idx .. " @" .. tostring(start_frame) ..
                                  "] " .. item_name .. "  (color: " .. color .. ")")
                        else
                            print("  SKIP  [V" .. track_idx .. " @" .. tostring(start_frame) ..
                                  "] " .. item_name .. "  (color: '" .. color .. "')")
                        end
                    end
                end
            end
        end
    end

    print("\nCandidates scanned : " .. total_count)
    print("Clips to keep      : " .. keep_count)

    if keep_count == 0 then
        print("\nERROR: No clips with color '" .. target_color ..
              "' found in timeline '" .. source_name .. "'.")
        print("Assign the clip color in the Edit page (right-click clip > Clip Color) and re-run.")
        return
    end

    -- ── Duplicate the source timeline ─────────────────────────────────────────
    local new_timeline = duplicateTimeline(project, media_pool, source_timeline, new_name)

    if not new_timeline then
        print("ERROR: Timeline duplication failed. Check console output above.")
        return
    end

    pcall(function() project:SetCurrentTimeline(new_timeline) end)

    -- ═══════════════════════════════════════════════════════════════════════════
    -- MODE A: Keep Positions — delete unwanted clips from the duplicate
    -- ═══════════════════════════════════════════════════════════════════════════
    if not delete_gaps then
        print("\nMode: Keep Positions — removing unwanted clips from duplicate...")

        local removed_count = 0
        local kept_count    = 0
        local error_count   = 0

        local dup_video_track_count = 0
        pcall(function() dup_video_track_count = new_timeline:GetTrackCount("video") end)

        for track_idx = 1, dup_video_track_count do
            local items = nil
            pcall(function() items = new_timeline:GetItemListInTrack("video", track_idx) end)

            if items then
                local to_delete = {}

                for _, item in ipairs(items) do
                    local start_frame = nil
                    pcall(function() start_frame = item:GetStart() end)

                    if start_frame ~= nil then
                        local key = "video_" .. track_idx .. "_" .. start_frame

                        if keep_set[key] then
                            kept_count = kept_count + 1
                            local item_name = "?"
                            pcall(function() item_name = item:GetName() end)
                            print("  Keeping  [V" .. track_idx .. " @" .. start_frame ..
                                  "] " .. item_name)
                        else
                            table.insert(to_delete, item)
                            removed_count = removed_count + 1
                        end
                    end
                end

                if #to_delete > 0 then
                    pcall(function() project:SetCurrentTimeline(new_timeline) end)
                    local ok, err = pcall(function()
                        new_timeline:DeleteClips(to_delete)
                    end)
                    if ok then
                        print("  Removed " .. #to_delete .. " clip(s) from video track " .. track_idx)
                    else
                        print("  ERROR on track " .. track_idx .. ": " .. tostring(err))
                        error_count = error_count + #to_delete
                    end
                end
            end
        end

        print("\n── Keep Positions result ────────────────────────────────────────────────")
        print("Clips kept   : " .. kept_count)
        print("Clips removed: " .. removed_count)
        if error_count > 0 then
            print("Errors       : " .. error_count .. " clip(s) could not be removed — check manually.")
        end

    -- ═══════════════════════════════════════════════════════════════════════════
    -- MODE B: Delete Gaps — clear timeline and re-append sorted clips
    -- ═══════════════════════════════════════════════════════════════════════════
    else
        print("\nMode: Delete Gaps — clearing timeline and re-appending " ..
              #kept_clips .. " clip(s) sequentially...")

        -- Sort by original timeline inpoint across all tracks
        table.sort(kept_clips, function(a, b)
            return a.timelineInpoint < b.timelineInpoint
        end)

        -- Clear the duplicate (all tracks)
        pcall(function() project:SetCurrentTimeline(new_timeline) end)
        clearTimelineClips(new_timeline)

        -- Re-assert active timeline after clear
        pcall(function() project:SetCurrentTimeline(new_timeline) end)

        local appended_count = 0
        local failed_count   = 0

        for i, clip_info in ipairs(kept_clips) do
            print("  Appending #" .. i .. ": " .. clip_info.displayName ..
                  " (src " .. clip_info.startFrame .. "-" .. clip_info.endFrame ..
                  ", original tl pos " .. clip_info.timelineInpoint .. ")")

            local items_before = {}
            pcall(function()
                items_before = new_timeline:GetItemListInTrack("video", 1) or {}
            end)

            local appended = nil
            pcall(function()
                appended = media_pool:AppendToTimeline({
                    {
                        mediaPoolItem = clip_info.mediaPoolItem,
                        startFrame    = clip_info.startFrame,
                        endFrame      = clip_info.endFrame,
                    }
                })
            end)

            local items_after = {}
            pcall(function()
                items_after = new_timeline:GetItemListInTrack("video", 1) or {}
            end)

            local new_item = nil
            if appended and type(appended) == "table" and #appended > 0 then
                new_item = appended[1]
                appended_count = appended_count + 1
            elseif #items_after > #items_before then
                new_item = items_after[#items_after]
                appended_count = appended_count + 1
            else
                print("    FAILED (silent reject): " .. clip_info.displayName)
                failed_count = failed_count + 1
            end

            -- Restore clip color and version name on the new item
            if new_item then
                pcall(function()
                    if clip_info.clipColor and clip_info.clipColor ~= "" then
                        new_item:SetClipColor(clip_info.clipColor)
                    end
                end)
                if clip_info.versionName then
                    pcall(function()
                        new_item:DeleteVersionByName()
                        new_item:AddVersion(clip_info.versionName, 0)
                        new_item:SetName(clip_info.versionName)
                    end)
                    print("    Version name restored: " .. clip_info.versionName)
                end
            end
        end

        print("\n── Delete Gaps result ───────────────────────────────────────────────────")
        print("Clips appended: " .. appended_count)
        if failed_count > 0 then
            print("Clips failed  : " .. failed_count .. " — check console output above.")
        end
    end

    -- ── Optionally remove all audio tracks ───────────────────────────────────
    if remove_audio then
        pcall(function() project:SetCurrentTimeline(new_timeline) end)
        removeAllAudioTracks(new_timeline)
    end

    -- ── Final summary ─────────────────────────────────────────────────────────
    print("\n── Done ─────────────────────────────────────────────────────────────────")
    print("New timeline : " .. new_name)
    print("Mode         : " .. (delete_gaps and "Delete Gaps (sequential, V1)" or "Keep Positions"))
    if not delete_gaps then
        print("Gaps remain where clips were removed, preserving timeline positions.")
    end
end

-- Run
main()
