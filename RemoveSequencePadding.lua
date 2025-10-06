-- Revised script to remove frame numbering, preceding dots/underscores, and file extensions from filenames
-- For use in DaVinci Resolve

function removeFrameNumbering()
    -- Check if we have access to resolve object
    if not resolve then
        print("ERROR: Unable to access Resolve API")
        return
    end

    print("Starting frame numbering and extension removal process...")

    -- Get the project manager
    local projectManager = resolve:GetProjectManager()
    if not projectManager then
        print("ERROR: Unable to access Project Manager")
        return
    end

    -- Get the current project
    local project = projectManager:GetCurrentProject()
    if not project then
        print("ERROR: No project is currently open")
        return
    end

    -- Get the Media Pool
    local mediaPool = project:GetMediaPool()
    if not mediaPool then
        print("ERROR: Unable to access Media Pool")
        return
    end

    -- Get the current bin
    local currentBin = mediaPool:GetCurrentFolder()
    if not currentBin then
        print("ERROR: Unable to access current bin")
        return
    end

    -- Improved function to clean filename
    local function cleanFilename(filename)
        -- Remove frame range patterns like _[1001-1130] or .[1001-1130]
        local cleanName = filename:gsub("[%.%_]%[%d+%-%d+%]", "")

        -- Optionally trim trailing underscores or dots before file extension
        cleanName = cleanName:gsub("([%._]+)(%.[%w]+)$", "%2")

        -- Remove file extension and its dot (e.g., .mov, .mp4, etc.)
        cleanName = cleanName:gsub("%.[%w]+$", "")

        return cleanName
    end

    -- Track changes made
    local changesCount = 0

    -- Keep track of processed clips to avoid duplicates
    local processedClips = {}

    -- Get all clips in the current bin
    local clips = currentBin:GetClipList()
    if clips then
        print(string.format("Found %d clips in current bin", #clips))

        for _, clip in ipairs(clips) do
            local currentName = clip:GetClipProperty("Clip Name")

            -- Only process if we haven't seen this clip before
            if not processedClips[currentName] then
                processedClips[currentName] = true

                print(string.format("Processing clip: %s", currentName))
                local newName = cleanFilename(currentName)

                -- Only update if the name actually changed
                if currentName ~= newName then
                    -- Try to rename and verify the change
                    clip:SetClipProperty("Clip Name", newName)

                    -- Verify the change by reading back the new name
                    local verifyName = clip:GetClipProperty("Clip Name")
                    if verifyName == newName then
                        changesCount = changesCount + 1
                        print(string.format("Successfully renamed: %s -> %s", currentName, newName))
                    else
                        print(string.format("Warning: Rename may have failed for: %s", currentName))
                    end
                else
                    print("No change needed for: " .. currentName)
                end
            end
        end
    else
        print("No clips found in current bin")
    end

    print(string.format("Process complete. Successfully renamed %d clips.", changesCount))
end

-- Execute the function
print("Script starting...")
removeFrameNumbering()
print("Script finished")
