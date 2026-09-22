-- CreateTimelinesFromBinMedia.lua
-- GUI tool. Scans the current Media Pool bin (or only the selected clips)
-- for video files and image sequences (mp4, mov, mxf, exr).
-- Creates one timeline per clip. User selects: selected clips only, keep
-- source FPS, keep source resolution, keep source start timecode, strip file
-- extension from timeline name.
-- Ignored clips are printed to the console with their metadata.
-- Run inside DaVinci Resolve via Workspace > Scripts.

local VALID_EXTENSIONS = {
    mp4 = true,
    mov = true,
    mxf = true,
    exr = true,
}

local resolve = Resolve()
local fusion = resolve:Fusion()
local ui = fusion.UIManager
local disp = bmd.UIDispatcher(ui)

local function GetFileExtension(filePath)
    if not filePath or filePath == "" then
        return nil
    end
    local ext = filePath:match("%.([%a%d]+)$")
    if ext then
        return ext:lower()
    end
    return nil
end

local function ParseResolution(resString)
    if not resString then
        return nil, nil
    end
    local w, h = resString:match("(%d+)x(%d+)")
    if w and h then
        return tonumber(w), tonumber(h)
    end
    return nil, nil
end

local function StripExtension(name)
    return (name:gsub("%.[%a%d]+$", ""))
end

-- Returns a clean timecode string, or nil if the value is missing or invalid.
local function ParseTimecode(tcString)
    if not tcString then
        return nil
    end
    local tc = tostring(tcString):gsub("^%s+", ""):gsub("%s+$", "")
    if tc:match("^%d%d[:;]%d%d[:;]%d%d[:;]%d%d$") then
        return tc
    end
    return nil
end

-- Converts any table returned by the Resolve API into a sequential array of
-- Resolve objects. Drops non-object values (counts, indices) that the API can
-- mix into returned tables, and preserves ordering by sorted key.
local function ToArray(tbl)
    local out = {}
    if type(tbl) ~= "table" then
        return out
    end

    local keys = {}
    for k in pairs(tbl) do
        keys[#keys + 1] = k
    end
    table.sort(keys, function(a, b)
        local ta, tb = type(a), type(b)
        if ta == tb and (ta == "number" or ta == "string") then
            return a < b
        end
        return ta < tb
    end)

    for _, k in ipairs(keys) do
        local v = tbl[k]
        local tv = type(v)
        if tv == "userdata" or tv == "table" then
            out[#out + 1] = v
        end
    end
    return out
end

-- Returns an array of clips (either the selection or the current bin), or nil plus an error message.
local function GetSourceClips(mediaPool, selectedOnly)
    if selectedOnly then
        if type(mediaPool.GetSelectedClips) ~= "function" and not mediaPool.GetSelectedClips then
            return nil, "ERROR: GetSelectedClips not available (requires Resolve 18.5+)."
        end
        local selected = ToArray(mediaPool:GetSelectedClips())
        if #selected == 0 then
            return nil, "No clips selected in the Media Pool."
        end
        return selected, nil
    end

    local currentFolder = mediaPool:GetCurrentFolder()
    if not currentFolder then
        return nil, "ERROR: Cannot access current bin."
    end
    local clips = ToArray(currentFolder:GetClipList())
    if #clips == 0 then
        return nil, "No clips found in the current bin."
    end
    return clips, nil
end

-- Build the GUI window.
local win = disp:AddWindow({
    ID = "CreateTimelinesWin",
    WindowTitle = "Create Timelines From Bin Media",
    Geometry = {100, 100, 420, 290},

    ui:VGroup{
        ID = "root",
        ui:VGap(10),

        ui:CheckBox{
            ID = "SelectedOnly",
            Text = "Process selected clips only",
            Checked = false,
        },
        ui:CheckBox{
            ID = "PreserveFPS",
            Text = "Preserve source FPS",
            Checked = true,
        },
        ui:CheckBox{
            ID = "PreserveResolution",
            Text = "Preserve source resolution",
            Checked = true,
        },
        ui:CheckBox{
            ID = "PreserveTimecode",
            Text = "Preserve source start timecode",
            Checked = true,
        },
        ui:CheckBox{
            ID = "StripExtension",
            Text = "Remove file extension from timeline name",
            Checked = true,
        },

        ui:VGap(15),

        ui:HGroup{
            Weight = 0,
            ui:Button{ID = "RunButton", Text = "Create Timelines"},
            ui:Button{ID = "CancelButton", Text = "Cancel"},
        },

        ui:VGap(5),
        ui:Label{ID = "StatusLabel", Text = ""},
    },
})

local itm = win:GetItems()

local function SetStatus(text)
    itm.StatusLabel.Text = text
end

local function CreateTimelines(selectedOnly, preserveFPS, preserveResolution, preserveTimecode, stripExtension)
    local project = resolve:GetProjectManager():GetCurrentProject()
    if not project then
        SetStatus("ERROR: No project is open.")
        return
    end

    local mediaPool = project:GetMediaPool()

    -- Snapshot the clip list before any timeline is created.
    local clips, err = GetSourceClips(mediaPool, selectedOnly)
    if not clips then
        SetStatus(err)
        print(err)
        return
    end

    print(string.format(
        "Source: %s | Clips: %d",
        selectedOnly and "selection" or "current bin",
        #clips
    ))

    local createdCount = 0
    local skippedCount = 0
    local ignoredCount = 0
    local warnCount = 0

    for _, clip in ipairs(clips) do
        local filePath = clip:GetClipProperty("File Path")
        local ext = GetFileExtension(filePath)

        if ext and VALID_EXTENSIONS[ext] then
            local sourceName = clip:GetName()
            local timelineName = sourceName
            if stripExtension then
                timelineName = StripExtension(sourceName)
            end

            local width, height
            local fpsString
            local startTC

            if preserveResolution then
                local resString = clip:GetClipProperty("Resolution")
                width, height = ParseResolution(resString)
                if not width or not height then
                    print(string.format(
                        "SKIP: '%s' — missing resolution metadata.",
                        sourceName
                    ))
                    skippedCount = skippedCount + 1
                    goto continue
                end
            end

            if preserveFPS then
                fpsString = clip:GetClipProperty("FPS")
                if not tonumber(fpsString) then
                    print(string.format(
                        "SKIP: '%s' — missing FPS metadata.",
                        sourceName
                    ))
                    skippedCount = skippedCount + 1
                    goto continue
                end
            end

            if preserveTimecode then
                startTC = ParseTimecode(clip:GetClipProperty("Start TC"))
                if not startTC then
                    print(string.format(
                        "SKIP: '%s' — missing or invalid start timecode.",
                        sourceName
                    ))
                    skippedCount = skippedCount + 1
                    goto continue
                end
            end

            local newTimeline = mediaPool:CreateEmptyTimeline(timelineName)
            if not newTimeline then
                print(string.format(
                    "SKIP: '%s' — timeline creation failed (name may already exist).",
                    timelineName
                ))
                skippedCount = skippedCount + 1
                goto continue
            end

            if preserveFPS or preserveResolution or preserveTimecode then
                newTimeline:SetSetting("useCustomSettings", "1")
                if preserveResolution then
                    newTimeline:SetSetting("timelineResolutionWidth", tostring(width))
                    newTimeline:SetSetting("timelineResolutionHeight", tostring(height))
                end
                if preserveFPS then
                    newTimeline:SetSetting("timelineFrameRate", tostring(fpsString))
                end
            end

            -- Frame rate is set. Now set drop frame, then start timecode.
            if preserveTimecode then
                local isDropFrame = startTC:find(";", 1, true) ~= nil
                newTimeline:SetSetting("timelineDropFrameTimecode", isDropFrame and "1" or "0")

                if not newTimeline:SetStartTimecode(startTC) then
                    print(string.format(
                        "WARN: '%s' — could not set start timecode %s.",
                        timelineName, startTC
                    ))
                    warnCount = warnCount + 1
                end
            end

            project:SetCurrentTimeline(newTimeline)
            mediaPool:AppendToTimeline({clip})

            print(string.format("OK: '%s' created (start TC: %s).", timelineName, tostring(startTC)))
            createdCount = createdCount + 1
        else
            ignoredCount = ignoredCount + 1
            print(string.format(
                "IGNORED: '%s' | path='%s' | ext='%s' | type='%s' | format='%s'",
                tostring(clip:GetName()),
                tostring(filePath),
                tostring(ext),
                tostring(clip:GetClipProperty("Type")),
                tostring(clip:GetClipProperty("Format"))
            ))
        end

        ::continue::
    end

    SetStatus(string.format(
        "Done. Created: %d. Skipped: %d. Ignored: %d. Timecode warnings: %d.",
        createdCount, skippedCount, ignoredCount, warnCount
    ))
end

function win.On.RunButton.Clicked(ev)
    local selectedOnly = itm.SelectedOnly.Checked
    local preserveFPS = itm.PreserveFPS.Checked
    local preserveResolution = itm.PreserveResolution.Checked
    local preserveTimecode = itm.PreserveTimecode.Checked
    local stripExtension = itm.StripExtension.Checked
    SetStatus("Working...")
    CreateTimelines(selectedOnly, preserveFPS, preserveResolution, preserveTimecode, stripExtension)
end

function win.On.CancelButton.Clicked(ev)
    disp:ExitLoop()
end

function win.On.CreateTimelinesWin.Close(ev)
    disp:ExitLoop()
end

win:Show()
disp:RunLoop()
win:Hide()