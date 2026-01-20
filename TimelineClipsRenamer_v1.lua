fusion = fusion or Fusion()
local ui = fusion.UIManager
local disp = bmd.UIDispatcher(ui)

local width, height = 450, 500

win = disp:AddWindow({
    ID = "RenameWin",
    WindowTitle = "Rename Shots",
    Geometry = { 100, 50, width, height },
    ui:VGroup {
        ui:HGroup {
            ui:Label { Text = "Scene:" },
            ui:TextEdit { ID = "SceneText", Text = "sc01" }
        },
        ui:HGroup {
            ui:Label { Text = "Shot Pattern:" },
            ui:TextEdit { ID = "PatternText", Text = "sh####" }
        },
        ui:HGroup {
            ui:Label { Text = "Start by:" },
            ui:TextEdit { ID = "StartNumber", Text = "10" }
        },
        ui:HGroup {
            ui:Label { Text = "Increment:" },
            ui:TextEdit { ID = "Increment", Text = "10" }
        },
        ui:HGroup {
            ui:Label { Text = "Layer Suffix Pattern:" },
            ui:TextEdit { ID = "StackedPattern", Text = "_L##" }
        },
        ui:VGroup {
            ui:Label { Text = "Processing Mode:" },
            ui:HGroup {
                ui:CheckBox { ID = "FromTimelineStart", Text = "All Clips (Timeline Start)", Checked = true },
                ui:CheckBox { ID = "FromPlayhead", Text = "Start from Playhead Position", Checked = false }
            }
        },
        ui:HGroup {
            ui:Button { ID = "PreviewButton", Text = "Preview" },
            ui:Button { ID = "RenameButton", Text = "Rename" },
            ui:Button { ID = "CancelButton", Text = "Cancel" }
        }
    }
})

local itm = win:GetItems()

function win.On.FromTimelineStart.Clicked(ev)
    if itm.FromTimelineStart.Checked then
        itm.FromPlayhead.Checked = false
    else
        itm.FromPlayhead.Checked = true
    end
end

function win.On.FromPlayhead.Clicked(ev)
    if itm.FromPlayhead.Checked then
        itm.FromTimelineStart.Checked = false
    else
        itm.FromTimelineStart.Checked = true
    end
end

function win.On.RenameWin.Close(ev)
    disp:ExitLoop()
end

function win.On.CancelButton.Clicked(ev)
    disp:ExitLoop()
end

function FormatNumber(number, padding)
    return string.format("%0" .. padding .. "d", number)
end

function ApplySuffixPattern(pattern, number)
    local hashCount = select(2, pattern:gsub("#", "#"))
    local formatted = FormatNumber(number, hashCount)
    return pattern:gsub("#+", formatted)
end

function TimecodeToFrame(timecode, frameRate)
    -- Parse timecode in format "HH:MM:SS:FF"
    local h, m, s, f = timecode:match("(%d+):(%d+):(%d+):(%d+)")
    if not h then return 0 end
    
    local totalFrames = (tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)) * frameRate + tonumber(f)
    return totalFrames
end

function FindClipAtFrame(clips, targetFrame)
    for i, clip in ipairs(clips) do
        local start = clip:GetStart()
        local duration = clip:GetDuration()
        local endFrame = start + duration - 1
        
        if targetFrame >= start and targetFrame <= endFrame then
            return i
        end
    end
    return 1 -- Default to first clip if not found
end

function GeneratePreviewNames()
    local scene = itm.SceneText.PlainText or ""
    local pattern = itm.PatternText.PlainText
    local start_num = tonumber(itm.StartNumber.PlainText) or 1
    local increment = tonumber(itm.Increment.PlainText) or 10
    local stackedPattern = itm.StackedPattern.PlainText or "_L##"
    local fromPlayhead = itm.FromPlayhead.Checked

    if not pattern or not string.find(pattern, "#") then
        ui:MessageBox("Pattern Error", "Pattern must include at least one '#' symbol to insert numbers.", { "OK" }, false)
        return {}
    end

    local prefix = string.match(pattern, "^(.-)#")
    local padding = #string.match(pattern, "#+")

    local resolve = Resolve()
    local project = resolve:GetProjectManager():GetCurrentProject()
    local timeline = project:GetCurrentTimeline()
    local clips = timeline:GetItemListInTrack('video', 1)

    if not clips or #clips == 0 then
        return { "No clips found on video track 1." }
    end

    local startIndex = 1
    local clipCnt = start_num
    local videoTrackCount = timeline:GetTrackCount("video")
    local previewNames = {}

    -- If starting from playhead, find the clip at playhead position
    if fromPlayhead then
        local currentTimecode = timeline:GetCurrentTimecode()
        local frameRate = timeline:GetSetting("timelineFrameRate") or 25
        local currentFrame = TimecodeToFrame(currentTimecode, frameRate)
        
        startIndex = FindClipAtFrame(clips, currentFrame)
        
        table.insert(previewNames, "Starting from playhead at " .. currentTimecode .. " (clip " .. startIndex .. ")")
        table.insert(previewNames, "")
    end

    -- Process clips starting from the determined index
    for i = startIndex, #clips do
        local clipItem = clips[i]
        local props = clipItem:GetProperty()
        local is_enabled = props and props["Enabled"] ~= false

        if is_enabled then
            local shotName = prefix .. FormatNumber(clipCnt, padding)
            local fullName = scene ~= "" and (scene .. "_" .. shotName) or shotName
            local hasStackedClip = false
            local cStart = clipItem:GetStart()
            local cEnd = clipItem:GetEnd()

            for j = 2, videoTrackCount do
                local track_clips = timeline:GetItemListInTrack('video', j)
                for _, track_clip in ipairs(track_clips) do
                    local tStart = track_clip:GetStart()
                    local tEnd = track_clip:GetEnd()
                    if tStart < cEnd and tEnd > cStart then
                        hasStackedClip = true
                        table.insert(previewNames, fullName .. ApplySuffixPattern(stackedPattern, j))
                    end
                end
            end

            local baseName = hasStackedClip and (fullName .. ApplySuffixPattern(stackedPattern, 1)) or fullName
            table.insert(previewNames, baseName)

            clipCnt = clipCnt + increment
        end
    end

    return previewNames
end

function win.On.PreviewButton.Clicked(ev)
    local names = GeneratePreviewNames()
    local previewText = table.concat(names, "\n")

    local previewWin = disp:AddWindow({
        ID = "PreviewWin",
        WindowTitle = "Preview Clip Names",
        Geometry = { 150, 100, 400, 500 },
        ui:VGroup {
            ui:TextEdit {
                ID = "PreviewText",
                ReadOnly = true,
                Text = previewText
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
    local scene = itm.SceneText.PlainText or ""
    local pattern = itm.PatternText.PlainText
    local start_num = tonumber(itm.StartNumber.PlainText) or 1
    local increment = tonumber(itm.Increment.PlainText) or 10
    local stackedPattern = itm.StackedPattern.PlainText or "_L#"
    local fromPlayhead = itm.FromPlayhead.Checked

    if not pattern or not string.find(pattern, "#") then
        ui:MessageBox("Pattern Error", "Pattern must include at least one '#' symbol to insert numbers.", { "OK" }, false)
        return
    end

    local prefix = string.match(pattern, "^(.-)#")
    local padding = #string.match(pattern, "#+")

    local resolve = Resolve()
    local project = resolve:GetProjectManager():GetCurrentProject()
    local timeline = project:GetCurrentTimeline()
    local clips = timeline:GetItemListInTrack('video', 1)

    if not clips or #clips == 0 then
        print("Empty timeline found! Script can't do anything with empty timeline!")
        return
    end

    local startIndex = 1
    local clipCnt = start_num
    local videoTrackCount = timeline:GetTrackCount("video")

    -- If starting from playhead, find the clip at playhead position
    if fromPlayhead then
        local currentTimecode = timeline:GetCurrentTimecode()
        local frameRate = timeline:GetSetting("timelineFrameRate") or 25
        local currentFrame = TimecodeToFrame(currentTimecode, frameRate)
        
        startIndex = FindClipAtFrame(clips, currentFrame)
        
        print("Starting from playhead at " .. currentTimecode .. " (clip " .. startIndex .. ")")
    end

    -- Process clips starting from the determined index
    for i = startIndex, #clips do
        local clipItem = clips[i]
        local props = clipItem:GetProperty()
        local is_enabled = props and props["Enabled"] ~= false

        if is_enabled then
            local shotName = prefix .. FormatNumber(clipCnt, padding)
            local fullName = scene ~= "" and (scene .. "_" .. shotName) or shotName
            local hasStackedClip = false
            local cStart = clipItem:GetStart()
            local cEnd = clipItem:GetEnd()

            for j = 2, videoTrackCount do
                local track_clips = timeline:GetItemListInTrack('video', j)
                for _, track_clip in ipairs(track_clips) do
                    local tStart = track_clip:GetStart()
                    local tEnd = track_clip:GetEnd()
                    if tStart < cEnd and tEnd > cStart then
                        hasStackedClip = true
                        local trackName = fullName .. ApplySuffixPattern(stackedPattern, j)
                        track_clip:DeleteVersionByName()
                        track_clip:AddVersion(trackName, 0)
                    end
                end
            end

            local baseName = hasStackedClip and (fullName .. ApplySuffixPattern(stackedPattern, 1)) or fullName
            clipItem:DeleteVersionByName()
            clipItem:AddVersion(baseName, 0)

            clipCnt = clipCnt + increment
        end
    end

    print("Renaming complete.")
    win:Hide()

    local confirmWin = disp:AddWindow({
        ID = "ConfirmWin",
        WindowTitle = "Done!",
        Geometry = { 200, 200, 600, 150 },
        ui:VGroup {
            ui:Label {
                ID = "ConfirmLabel",
                Text = "Clips renamed! Now select all of them and rename them with %{Version} name in Inspector.",
                WordWrap = true
            },
            ui:Button { ID = "CloseConfirm", Text = "OK" }
        }
    })

    function confirmWin.On.CloseConfirm.Clicked(ev)
        confirmWin:Hide()
        disp:ExitLoop()
    end

    confirmWin:Show()
end

win:Show()
disp:RunLoop()
win:Hide()