-- Script to extract only reel and clip numbers (A###C###, B###C###, C###C###) from filenames
-- For use in DaVinci Resolve

function extractReelClipNumber()
   -- Check if we have access to resolve object
   if not resolve then
       print("ERROR: Unable to access Resolve API")
       return
   end

   print("Starting reel/clip number extraction process...")

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

   -- Function to extract reel/clip pattern
        local function extractReelClip(filename)
        -- Remove file extension first
        local nameWithoutExt = filename:match("(.+)%..+$") or filename
        
        -- Pattern 1: A###_..._C### (underscore before C - keep underscore in output)
        local reel, clip = nameWithoutExt:match("([ABCD]%d%d%d)_.*(C%d%d%d)")
        if reel and clip then
            return reel .. "" .. clip
        end
        
        -- Pattern 2: A_####C### (4 digits, no underscore before C)
        local letter, digits4, clip = nameWithoutExt:match("([ABCD])_(%d%d%d%d)(C%d%d%d)")
        if letter and digits4 and clip then
            -- Take last 3 digits of reel number
            local lastThree = digits4:sub(2, 4)
            return letter .. lastThree .. clip
        end
        
        -- Pattern 3: A###C### (3 digits, no underscore before C)
        local reel3, clip3 = nameWithoutExt:match("([ABCD]%d%d%d)(C%d%d%d)")
        if reel3 and clip3 then
            return reel3 .. clip3
        end
        
        return filename
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
               local newName = extractReelClip(currentName)

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
extractReelClipNumber()
print("Script finished")