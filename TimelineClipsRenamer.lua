fusion = fusion or Fusion()
local ui = fusion.UIManager
local disp = bmd.UIDispatcher(ui)

local width, height = 660, 400

win = disp:AddWindow({
    ID = "RenameWin",
    WindowTitle = "Rename Timeline Clips",
    Geometry = { 100, 50, width, height },
    ui:VGroup {
        -- Row 1: Scene + Shot Pattern
        ui:HGroup {
            ui:Label { Text = "Scene:", MinimumSize = { 110, 0 } },
            ui:TextEdit { ID = "SceneText", Text = "sc01" },
            ui:Label { Text = "Shot Pattern:", MinimumSize = { 110, 0 } },
            ui:TextEdit { ID = "PatternText", Text = "sh####" }
        },
        -- Row 2: Start + Increment
        ui:HGroup {
            ui:Label { Text = "Start by:", MinimumSize = { 110, 0 } },
            ui:TextEdit { ID = "StartNumber", Text = "10" },
            ui:Label { Text = "Increment by:", MinimumSize = { 110, 0 } },
            ui:TextEdit { ID = "Increment", Text = "10" }
        },
        -- Row 3: Layer Suffix (left column only, right column empty to match grid)
        ui:HGroup {
            ui:Label { Text = "Layer Suffix:", MinimumSize = { 110, 0 } },
            ui:TextEdit { ID = "StackedPattern", Text = "_L##" },
            ui:Label { Text = "", MinimumSize = { 110, 0 } },
            ui:HGap {}
        },
        -- Row 4: Three option groups side by side
        ui:HGroup {
            ui:VGroup {
                ui:Label { Text = "Processing Mode:" },
                ui:CheckBox { ID = "SelectedOnly", Text = "Selected Clips Only", Checked = true },
                ui:CheckBox { ID = "FromTimelineStart", Text = "All Clips (Timeline Start)", Checked = false }
            },
            ui:VGroup {
                ui:Label { Text = "Track Processing:" },
                ui:CheckBox { ID = "ProcessVideoTracks", Text = "Video Tracks", Checked = true },
                ui:CheckBox { ID = "ProcessAudioTracks", Text = "Audio Tracks", Checked = false }
            },
            ui:VGroup {
                ui:Label { Text = "Rename Method:" },
                ui:CheckBox { ID = "UseDirectNames", Text = "Direct Clip Name", Checked = true },
                ui:CheckBox { ID = "UseVersionNames", Text = "Color Page Version Name", Checked = false }
            }
        },
        ui:Label {
            ID = "MethodNote",
            Text = "Direct: renames clip in timeline.  \nVersion: renames clip in timeline AND creates a matching Color page version (audio always uses Direct).",
            WordWrap = true
        },
        ui:HGroup {
            ui:Button { ID = "PreviewButton", Text = "Preview" },
            ui:Button { ID = "RenameButton", Text = "Rename" },
            ui:Button { ID = "CancelButton", Text = "Close" }
        }
    }
})

local itm = win:GetItems()

-- Mutex checkboxes: Processing Mode
function win.On.FromTimelineStart.Clicked(ev)
    if itm.FromTimelineStart.Checked then
        itm.SelectedOnly.Checked = false
    else
        itm.FromTimelineStart.Checked = true
    end
end

function win.On.SelectedOnly.Clicked(ev)
    if itm.SelectedOnly.Checked then
        itm.FromTimelineStart.Checked = false
    else
        itm.SelectedOnly.Checked = true
    end
end

-- Mutex checkboxes: Rename Method
function win.On.UseVersionNames.Clicked(ev)
    itm.UseDirectNames.Checked = not itm.UseVersionNames.Checked
end

function win.On.UseDirectNames.Clicked(ev)
    itm.UseVersionNames.Checked = not itm.UseDirectNames.Checked
end

function win.On.RenameWin.Close(ev)
    disp:ExitLoop()
end

function win.On.CancelButton.Clicked(ev)
    disp:ExitLoop()
end

-- ── Helpers ────────────────────────────────────────────────────────────────

function FormatNumber(number, padding)
    return string.format("%0" .. padding .. "d", number)
end

function ApplySuffixPattern(pattern, number)
    local hashCount = select(2, pattern:gsub("#", "#"))
    local formatted = FormatNumber(number, hashCount)
    return pattern:gsub("#+", formatted)
end

function ClipsOverlap(clip1, clip2)
    return clip1:GetStart() < clip2:GetEnd() and clip2:GetStart() < clip1:GetEnd()
end

-- Applies a name to a clip.
-- Always sets the direct clip name via SetName, so the timeline label updates immediately
-- regardless of mode.
-- useVersions=true additionally creates a matching Color page version with the same name,
-- so the artist does not need to invoke %{Version} manually afterward.
-- Returns the SetName result (the direct rename is the operation being counted/logged).
function RenameClip(clip, name, useVersions)
    if useVersions then
        clip:DeleteVersionByName()
        clip:AddVersion(name, 0)
    end
    return clip:SetName(name)
end

-- Builds a lookup table of unique IDs for all currently selected timeline items.
-- Returns nil if GetSelectedClips is unavailable (pre-21.0.4 Resolve build).
function GetSelectedIdSet(timeline)
    local ok, selected = pcall(function() return timeline:GetSelectedClips() end)
    if not ok or not selected then
        return nil
    end
    local idSet = {}
    for _, clip in ipairs(selected) do
        idSet[clip:GetUniqueId()] = true
    end
    return idSet
end

-- ── Core processing functions ───────────────────────────────────────────────

function ProcessVideoTracks(timeline, scene, prefix, padding, start_num, increment, stackedPattern, startIndex, useVersions, dryRun, selectedIds)
    local videoTrackCount = timeline:GetTrackCount("video")
    local v1Clips = timeline:GetItemListInTrack('video', 1)

    if not v1Clips or #v1Clips == 0 then return {}, 0 end

    local clipCnt = start_num
    local renamedCount = 0
    local log = {}

    for i = startIndex, #v1Clips do
        local v1Clip = v1Clips[i]
        local v1Selected = (not selectedIds) or selectedIds[v1Clip:GetUniqueId()]

        if v1Clip:GetClipEnabled() and v1Selected then

            local shotName = prefix .. FormatNumber(clipCnt, padding)
            local baseName = scene ~= "" and (scene .. "_" .. shotName) or shotName

            -- Collect overlapping clips from V2+
            local stackedClips = {}
            for trackNum = 2, videoTrackCount do
                local trackClips = timeline:GetItemListInTrack('video', trackNum)
                if trackClips then
                    for _, tClip in ipairs(trackClips) do
                        local tSelected = (not selectedIds) or selectedIds[tClip:GetUniqueId()]
                        if tClip:GetClipEnabled() and tSelected and ClipsOverlap(v1Clip, tClip) then
                            table.insert(stackedClips, { clip = tClip, trackNum = trackNum })
                        end
                    end
                end
            end
            table.sort(stackedClips, function(a, b) return a.trackNum < b.trackNum end)

            local v1Name = #stackedClips > 0 and (baseName .. ApplySuffixPattern(stackedPattern, 1)) or baseName

            if dryRun then
                table.insert(log, v1Name .. "  [V1]")
            else
                if RenameClip(v1Clip, v1Name, useVersions) then renamedCount = renamedCount + 1 end
                table.insert(log, v1Name .. "  [V1]")
            end

            for j, sd in ipairs(stackedClips) do
                local layerName = baseName .. ApplySuffixPattern(stackedPattern, j + 1)
                if dryRun then
                    table.insert(log, layerName .. "  [V" .. sd.trackNum .. "]")
                else
                    if RenameClip(sd.clip, layerName, useVersions) then renamedCount = renamedCount + 1 end
                    table.insert(log, layerName .. "  [V" .. sd.trackNum .. "]")
                end
            end

            clipCnt = clipCnt + increment
        end
    end

    return log, renamedCount
end

-- Audio clips have no version system; always uses SetName regardless of useVersions flag.
function ProcessAudioTracks(timeline, scene, prefix, padding, start_num, increment, stackedPattern, startIndex, dryRun, selectedIds)
    local audioTrackCount = timeline:GetTrackCount("audio")
    local v1Clips = timeline:GetItemListInTrack('video', 1)

    if not v1Clips or #v1Clips == 0 then return {}, 0 end

    local clipCnt = start_num
    local renamedCount = 0
    local log = {}

    for i = startIndex, #v1Clips do
        local v1Clip = v1Clips[i]
        local v1Selected = (not selectedIds) or selectedIds[v1Clip:GetUniqueId()]

        if v1Clip:GetClipEnabled() and v1Selected then

            local shotName = prefix .. FormatNumber(clipCnt, padding)
            local baseName = scene ~= "" and (scene .. "_" .. shotName) or shotName

            local audioClips = {}
            for trackNum = 1, audioTrackCount do
                local trackClips = timeline:GetItemListInTrack('audio', trackNum)
                if trackClips then
                    for _, aClip in ipairs(trackClips) do
                        local aSelected = (not selectedIds) or selectedIds[aClip:GetUniqueId()]
                        if aClip:GetClipEnabled() and aSelected and ClipsOverlap(v1Clip, aClip) then
                            table.insert(audioClips, { clip = aClip, trackNum = trackNum })
                        end
                    end
                end
            end
            table.sort(audioClips, function(a, b) return a.trackNum < b.trackNum end)

            for j, ad in ipairs(audioClips) do
                local audioName = #audioClips > 1 and (baseName .. ApplySuffixPattern(stackedPattern, j)) or baseName
                if dryRun then
                    table.insert(log, audioName .. "  [A" .. ad.trackNum .. "]")
                else
                    if ad.clip:SetName(audioName) then renamedCount = renamedCount + 1 end
                    table.insert(log, audioName .. "  [A" .. ad.trackNum .. "]")
                end
            end

            clipCnt = clipCnt + increment
        end
    end

    return log, renamedCount
end

-- ── Settings helper ─────────────────────────────────────────────────────────

function GetUISettings()
    return {
        scene          = itm.SceneText.PlainText or "",
        pattern        = itm.PatternText.PlainText,
        start_num      = tonumber(itm.StartNumber.PlainText) or 1,
        increment      = tonumber(itm.Increment.PlainText) or 10,
        stackedPattern = itm.StackedPattern.PlainText or "_L##",
        selectedOnly   = itm.SelectedOnly.Checked,
        processVideo   = itm.ProcessVideoTracks.Checked,
        processAudio   = itm.ProcessAudioTracks.Checked,
        useVersions    = itm.UseVersionNames.Checked
    }
end

function ValidateSettings(settings)
    if not settings.pattern or not string.find(settings.pattern, "#") then
        ui:MessageBox("Pattern Error", "Pattern must include at least one '#' symbol.", { "OK" }, false)
        return false
    end
    if not settings.processVideo and not settings.processAudio then
        ui:MessageBox("Selection Error", "Select at least one track type to process.", { "OK" }, false)
        return false
    end
    return true
end

function GetPrefixAndPadding(pattern)
    return string.match(pattern, "^(.-)#"), #string.match(pattern, "#+")
end

-- ── Run shared logic ─────────────────────────────────────────────────────────

function RunProcessing(dryRun)
    local settings = GetUISettings()
    if not ValidateSettings(settings) then return end

    local prefix, padding = GetPrefixAndPadding(settings.pattern)

    local resolve = Resolve()
    local timeline = resolve:GetProjectManager():GetCurrentProject():GetCurrentTimeline()
    local v1Clips = timeline:GetItemListInTrack('video', 1)

    if not v1Clips or #v1Clips == 0 then
        ui:MessageBox("Error", "No clips on video track 1.", { "OK" }, false)
        return
    end

    local selectedIds = nil
    if settings.selectedOnly then
        selectedIds = GetSelectedIdSet(timeline)
        if selectedIds == nil then
            ui:MessageBox("API Error", "This Resolve build has no Timeline:GetSelectedClips(). Requires Resolve Studio 21.0.4 or later.", { "OK" }, false)
            return
        end
        if next(selectedIds) == nil then
            ui:MessageBox("Selection Error", "No clips selected on the timeline.", { "OK" }, false)
            return
        end
    end

    local startIndex = 1
    local allLog = {}
    local totalRenamed = 0

    if settings.selectedOnly then
        table.insert(allLog, "Mode: Selected Clips Only")
        table.insert(allLog, "")
    end

    local methodLabel = settings.useVersions and "Version Names (Color Page)" or "Direct Clip Names"
    table.insert(allLog, "Method: " .. methodLabel)
    table.insert(allLog, "")

    if settings.processVideo then
        local log, count = ProcessVideoTracks(
            timeline, settings.scene, prefix, padding,
            settings.start_num, settings.increment,
            settings.stackedPattern, startIndex,
            settings.useVersions, dryRun, selectedIds
        )
        for _, l in ipairs(log) do table.insert(allLog, l) end
        totalRenamed = totalRenamed + count
    end

    if settings.processAudio then
        if settings.processVideo and #allLog > 0 then
            table.insert(allLog, "")
        end
        local log, count = ProcessAudioTracks(
            timeline, settings.scene, prefix, padding,
            settings.start_num, settings.increment,
            settings.stackedPattern, startIndex,
            dryRun, selectedIds
        )
        for _, l in ipairs(log) do table.insert(allLog, l) end
        totalRenamed = totalRenamed + count
    end

    return allLog, totalRenamed
end

-- ── Button handlers ──────────────────────────────────────────────────────────

function win.On.PreviewButton.Clicked(ev)
    local log, _ = RunProcessing(true)
    if not log then return end

    local previewWin = disp:AddWindow({
        ID = "PreviewWin",
        WindowTitle = "Preview Clip Names",
        Geometry = { 150, 100, 500, 600 },
        ui:VGroup {
            ui:TextEdit {
                ID = "PreviewText",
                ReadOnly = true,
                Text = table.concat(log, "\n")
            },
            ui:Button { ID = "ClosePreview", Text = "Close" }
        }
    })

    function previewWin.On.ClosePreview.Clicked(ev)
        previewWin:Hide()
    end

    previewWin:Show()
end

function win.On.RenameButton.Clicked(ev)
    local log, totalRenamed = RunProcessing(false)
    if not log then return end

    for _, l in ipairs(log) do print(l) end
    print("Renaming complete. " .. totalRenamed .. " clips renamed.")

    local confirmMsg = totalRenamed .. " clips renamed."

    disp:ExitLoop()

    local confirmWin = disp:AddWindow({
        ID = "ConfirmWin",
        WindowTitle = "Done",
        Geometry = { 200, 200, 500, 150 },
        ui:VGroup {
            ui:Label { ID = "ConfirmLabel", Text = confirmMsg, WordWrap = true },
            ui:Button { ID = "CloseConfirm", Text = "OK" }
        }
    })

    function confirmWin.On.CloseConfirm.Clicked(ev)
        confirmWin:Hide()
        disp:ExitLoop()
    end

    confirmWin:Show()
    disp:RunLoop()
end

-- ── Run ───────────────────────────────────────────────────────────────────────

win:Show()
disp:RunLoop()
win:Hide()
