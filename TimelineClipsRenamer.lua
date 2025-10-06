fusion = fusion or Fusion()
local ui = fusion.UIManager
local disp = bmd.UIDispatcher(ui)

local width, height = 450, 550

win = disp:AddWindow({
    ID = "RenameWin",
    WindowTitle = "Rename Timeline Clips",
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
            ui:TextEdit { ID = "StackedPattern", Text = "_L#" }
        },
        ui:VGroup {
            ui:Label { Text = "Processing Mode:" },
            ui:HGroup {
                ui:CheckBox { ID = "FromTimelineStart", Text = "All Clips (Timeline Start)", Checked = true },
                ui:CheckBox { ID = "FromPlayhead", Text = "Start from Playhead Position", Checked = false }
            }
        },
        ui:VGroup {
            ui:Label { Text = "Track Processing:" },
            ui:HGroup {
                ui:CheckBox { ID = "ProcessVideoTracks", Text = "Video Tracks", Checked = true },
                ui:CheckBox { ID = "ProcessAudioTracks", Text = "Audio Tracks", Checked = false }
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
    local h, m, s, f = timecode:match("(%d+):(%d+):(%d+):(%d+)")
    if not h then return 0 end
    
    local totalFrames = (tonumber(h) * 3600 + tonumber(m) * 60 + tonumber(s)) * frameRate + tonumber(f)
    return totalFrames
end

function ClipsOverlap(clip1, clip2)
    local start1, end1 = clip1:GetStart(), clip1:GetEnd()
    local start2, end2 = clip2:GetStart(), clip2:GetEnd()
    return start1 < end2 and start2 < end1
end

function ProcessVideoTracks(timeline, scene, prefix, padding, start_num, increment, stackedPattern, startIndex)
    local videoTrackCount = timeline:GetTrackCount("video")
    local v1Clips = timeline:GetItemListInTrack('video', 1)
    
    if not v1Clips or #v1Clips == 0 then
        return {}, 0
    end
    
    local clipCnt = start_num
    local renamedCount = 0
    local previewNames = {}
    
    for i = startIndex, #v1Clips do
        local v1Clip = v1Clips[i]
        local props = v1Clip:GetProperty()
        local is_enabled = props and props["Enabled"] ~= false
        
        if is_enabled then
            local shotName = prefix .. FormatNumber(clipCnt, padding)
            local baseName = scene ~= "" and (scene .. "_" .. shotName) or shotName
            
            local stackedClips = {}
            
            for trackNum = 2, videoTrackCount do
                local trackClips = timeline:GetItemListInTrack('video', trackNum)
                if trackClips then
                    for _, trackClip in ipairs(trackClips) do
                        local trackProps = trackClip:GetProperty()
                        local trackEnabled = trackProps and trackProps["Enabled"] ~= false
                        
                        if trackEnabled and ClipsOverlap(v1Clip, trackClip) then
                            table.insert(stackedClips, {
                                clip = trackClip,
                                trackNum = trackNum
                            })
                        end
                    end
                end
            end
            
            table.sort(stackedClips, function(a, b)
                return a.trackNum < b.trackNum
            end)
            
            local v1Name = #stackedClips > 0 and (baseName .. ApplySuffixPattern(stackedPattern, 1)) or baseName
            local success = v1Clip:SetName(v1Name)
            if success then
                renamedCount = renamedCount + 1
                table.insert(previewNames, v1Name .. " (video track 1)")
            end
            
            for j, stackedData in ipairs(stackedClips) do
                local layerName = baseName .. ApplySuffixPattern(stackedPattern, j + 1)
                local stackSuccess = stackedData.clip:SetName(layerName)
                if stackSuccess then
                    renamedCount = renamedCount + 1
                    table.insert(previewNames, layerName .. " (video track " .. stackedData.trackNum .. ")")
                end
            end
            
            clipCnt = clipCnt + increment
        end
    end
    
    return previewNames, renamedCount
end

function ProcessAudioTracks(timeline, scene, prefix, padding, start_num, increment, stackedPattern, startIndex)
    local audioTrackCount = timeline:GetTrackCount("audio")
    local v1Clips = timeline:GetItemListInTrack('video', 1)
    
    if not v1Clips or #v1Clips == 0 then
        return {}, 0
    end
    
    local clipCnt = start_num
    local renamedCount = 0
    local previewNames = {}
    
    for i = startIndex, #v1Clips do
        local v1Clip = v1Clips[i]
        local props = v1Clip:GetProperty()
        local is_enabled = props and props["Enabled"] ~= false
        
        if is_enabled then
            local shotName = prefix .. FormatNumber(clipCnt, padding)
            local baseName = scene ~= "" and (scene .. "_" .. shotName) or shotName
            
            local audioClips = {}
            
            for trackNum = 1, audioTrackCount do
                local trackClips = timeline:GetItemListInTrack('audio', trackNum)
                if trackClips then
                    for _, audioClip in ipairs(trackClips) do
                        local audioProps = audioClip:GetProperty()
                        local audioEnabled = audioProps and audioProps["Enabled"] ~= false
                        
                        if audioEnabled and ClipsOverlap(v1Clip, audioClip) then
                            table.insert(audioClips, {
                                clip = audioClip,
                                trackNum = trackNum
                            })
                        end
                    end
                end
            end
            
            table.sort(audioClips, function(a, b)
                return a.trackNum < b.trackNum
            end)
            
            for j, audioData in ipairs(audioClips) do
                local audioName
                if #audioClips > 1 then
                    audioName = baseName .. ApplySuffixPattern(stackedPattern, j)
                else
                    audioName = baseName
                end
                
                local success = audioData.clip:SetName(audioName)
                if success then
                    renamedCount = renamedCount + 1
                    table.insert(previewNames, audioName .. " (audio track " .. audioData.trackNum .. ")")
                end
            end
            
            clipCnt = clipCnt + increment
        end
    end
    
    return previewNames, renamedCount
end

function GetUISettings()
    return {
        scene = itm.SceneText.PlainText or "",
        pattern = itm.PatternText.PlainText,
        start_num = tonumber(itm.StartNumber.PlainText) or 1,
        increment = tonumber(itm.Increment.PlainText) or 10,
        stackedPattern = itm.StackedPattern.PlainText or "_L#",
        fromPlayhead = itm.FromPlayhead.Checked,
        processVideo = itm.ProcessVideoTracks.Checked,
        processAudio = itm.ProcessAudioTracks.Checked
    }
end

function win.On.PreviewButton.Clicked(ev)
    local settings = GetUISettings()
    
    if not settings.pattern or not string.find(settings.pattern, "#") then
        ui:MessageBox("Pattern Error", "Pattern must include at least one '#' symbol to insert numbers.", { "OK" }, false)
        return
    end

    if not settings.processVideo and not settings.processAudio then
        ui:MessageBox("Selection Error", "Please select at least one track type to process.", { "OK" }, false)
        return
    end

    local prefix = string.match(settings.pattern, "^(.-)#")
    local padding = #string.match(settings.pattern, "#+")

    local resolve = Resolve()
    local project = resolve:GetProjectManager():GetCurrentProject()
    local timeline = project:GetCurrentTimeline()
    
    local startIndex = 1
    local previewNames = {}

    if settings.fromPlayhead then
        local currentTimecode = timeline:GetCurrentTimecode()
        local frameRate = timeline:GetSetting("timelineFrameRate") or 25
        local currentFrame = TimecodeToFrame(currentTimecode, frameRate)
        
        if settings.processVideo then
            local v1Clips = timeline:GetItemListInTrack('video', 1)
            if v1Clips then
                for i, clip in ipairs(v1Clips) do
                    local start = clip:GetStart()
                    local duration = clip:GetDuration()
                    local endFrame = start + duration - 1
                    
                    if currentFrame >= start and currentFrame <= endFrame then
                        startIndex = i
                        break
                    end
                end
            end
        end
        
        table.insert(previewNames, "Starting from playhead at " .. currentTimecode .. " (clip " .. startIndex .. ")")
        table.insert(previewNames, "")
    end

    if settings.processVideo then
        local videoPreview, _ = ProcessVideoTracks(timeline, settings.scene, prefix, padding, settings.start_num, settings.increment, settings.stackedPattern, startIndex)
        for _, name in ipairs(videoPreview) do
            table.insert(previewNames, name)
        end
    end
    
    if settings.processAudio then
        local audioPreview, _ = ProcessAudioTracks(timeline, settings.scene, prefix, padding, settings.start_num, settings.increment, settings.stackedPattern, startIndex)
        for _, name in ipairs(audioPreview) do
            table.insert(previewNames, name)
        end
    end

    local previewText = table.concat(previewNames, "\n")

    local previewWin = disp:AddWindow({
        ID = "PreviewWin",
        WindowTitle = "Preview Clip Names",
        Geometry = { 150, 100, 500, 600 },
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
    local settings = GetUISettings()

    if not settings.pattern or not string.find(settings.pattern, "#") then
        ui:MessageBox("Pattern Error", "Pattern must include at least one '#' symbol to insert numbers.", { "OK" }, false)
        return
    end

    if not settings.processVideo and not settings.processAudio then
        ui:MessageBox("Selection Error", "Please select at least one track type to process.", { "OK" }, false)
        return
    end

    local prefix = string.match(settings.pattern, "^(.-)#")
    local padding = #string.match(settings.pattern, "#+")

    local resolve = Resolve()
    local project = resolve:GetProjectManager():GetCurrentProject()
    local timeline = project:GetCurrentTimeline()

    local startIndex = 1
    local totalRenamed = 0

    if settings.fromPlayhead then
        local currentTimecode = timeline:GetCurrentTimecode()
        local frameRate = timeline:GetSetting("timelineFrameRate") or 25
        local currentFrame = TimecodeToFrame(currentTimecode, frameRate)
        
        if settings.processVideo then
            local v1Clips = timeline:GetItemListInTrack('video', 1)
            if v1Clips then
                for i, clip in ipairs(v1Clips) do
                    local start = clip:GetStart()
                    local duration = clip:GetDuration()
                    local endFrame = start + duration - 1
                    
                    if currentFrame >= start and currentFrame <= endFrame then
                        startIndex = i
                        break
                    end
                end
            end
        end
        
        print("Starting from playhead at " .. currentTimecode .. " (clip " .. startIndex .. ")")
    end

    if settings.processVideo then
        local _, videoRenamed = ProcessVideoTracks(timeline, settings.scene, prefix, padding, settings.start_num, settings.increment, settings.stackedPattern, startIndex)
        totalRenamed = totalRenamed + videoRenamed
        print("Video tracks processed: " .. videoRenamed .. " clips renamed")
    end
    
    if settings.processAudio then
        local _, audioRenamed = ProcessAudioTracks(timeline, settings.scene, prefix, padding, settings.start_num, settings.increment, settings.stackedPattern, startIndex)
        totalRenamed = totalRenamed + audioRenamed
        print("Audio tracks processed: " .. audioRenamed .. " clips renamed")
    end

    print("Renaming complete. " .. totalRenamed .. " clips renamed total.")
    
    disp:ExitLoop()
end

win:Show()
disp:RunLoop()
win:Hide()