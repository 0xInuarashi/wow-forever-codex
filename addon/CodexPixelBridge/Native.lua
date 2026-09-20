-- Checked non-executable font packets -> normal Lua strings and native UI text.
local ADDON_NAME,NS=...
local SIZE,INTERVAL=65535,5
local initialized=false
local slot,loaded,request=1,0,0
local active,deadline,watchUntil=false,0,0
local session,reading=nil,nil
local consecutiveFailures,missedSlots=0,0
local assembly=NS.NewNativeAssembly()
local panel=NS.Panel
panel.TitleText:SetText('Codex | Live text 0.4.7')
local body=CreateFrame('ScrollingMessageFrame',nil,panel)
body:SetPoint('TOPLEFT',16,-118);body:SetSize(515,512)
body:SetFontObject(GameFontHighlight);body:SetJustifyH('LEFT');body:SetFading(false);body:SetMaxLines(5000)
body:EnableMouseWheel(true)
body:SetScript('OnMouseWheel',function(self,d) if d>0 then self:ScrollUp() else self:ScrollDown() end end)
body:AddMessage('Send a prompt. Hover or click item links in replies for details.')
NS.NativeBody=body
NS.DisplayNativeReply=function(text)
    body:Clear();body:AddMessage((text:gsub('|','||')));body:ScrollToTop()
end
local meter=UIParent:CreateFontString(nil,'OVERLAY')
meter:SetPoint('TOPLEFT',UIParent,'TOPLEFT',0,0);meter:SetAlpha(0)
meter:SetWordWrap(false);meter:SetNonSpaceWrap(false)
local badge=NS.Minimap:CreateFontString(nil,'OVERLAY','GameFontNormalLarge')
badge:SetPoint('TOPRIGHT',NS.Minimap,'TOPRIGHT',8,8);badge:SetText('')
panel:HookScript('OnShow',function() badge:SetText('') end)
local function watch()
    if not initialized then NS.SetStatus('Waiting for addon settings to load.');return end
    -- Reconcile again at user submission/resume in case beta settings arrived
    -- after ADDON_LOADED. Never move the active reader backwards.
    if not active then
        local saved=tonumber(CodexPixelBridgeState.nextFontSlotV2)
        if saved and saved>=1 and saved<=SIZE+1 and saved==math.floor(saved) then
            slot=math.max(slot,saved);loaded=slot-1
        end
    end
    if slot>SIZE then NS.SetStatus('Text channel reached its session limit. Replies remain in the companion.');return end
    if not active then deadline=GetTime()+6 end
    active=true;watchUntil=GetTime()+1200
    NS.SetWatchState(true)
end
NS.IsVisualWatching=function() return active end
NS.PauseVisual=function()
    if reading then loaded=slot;slot=slot+1 end
    active=false;reading=nil;NS.SetWatchState(false)
end
NS.ResumeVisual=function() if request>0 then consecutiveFailures=0;watch() end end
NS.OnPromptSubmitted=function(sequence)
    -- A partially requested font must not be overwritten/reused after cancellation.
    if reading then loaded=slot;slot=slot+1;reading=nil end
    request=sequence;assembly=NS.NewNativeAssembly();badge:SetText('');consecutiveFailures=0;missedSlots=0
    if NS.ClearReplyLinks then NS.ClearReplyLinks() end
    body:Clear();body:AddMessage('Waiting for Codex...');watch()
end
NS.ChangeVisualPage=function(delta) if delta<0 then body:PageUp() else body:PageDown() end end
if NS.ConfigureNative then NS.ConfigureNative() end
local function u16(n) return string.char(math.floor(n/256)%256,n%256) end
NS.VisualControl=function(value)
    session=value
    local remaining=active and not reading and math.max(0,math.min(6000,math.floor((deadline-GetTime())*1000))) or 0
    local data=NS.U32(slot)..NS.U32(remaining)..u16(assembly.nextPart)..u16(active and 1 or 0)..NS.U32(request)..NS.U32(loaded)
    local payload='CPBN'..string.char(2,#data,0,1)..session..NS.U32(0)..data..string.rep(string.char(0),40-#data)
    return payload..NS.Adler(payload)
end
local function width(char)
    meter:SetText(char..'~');return meter:GetStringWidth()
end
local function finish(reason,text,state)
    loaded=slot;slot=slot+1;reading=nil;deadline=GetTime()+INTERVAL
    -- A zero-filled installation placeholder means no writer reached this slot
    -- before its first load (for example while another window hid the strip).
    -- Keep the assembled parts and retry a fresh slot, with bounded backoff.
    if reason=='Empty reply slot' and slot<=SIZE then
        missedSlots=missedSlots+1;consecutiveFailures=0
        deadline=GetTime()+math.min(30,INTERVAL*2^math.min(missedSlots,3))
        NS.SetStatus('Waiting for companion. Keep the top-left strip visible; retrying automatically.')
        return
    end
    if not reason then missedSlots=0 end
    -- Some Forever beta reloads restore no SavedVariables. A checksum-valid
    -- packet for an older session identifies a cached, already-used path.
    -- Read past these normally, without waiting for writes or counting them as
    -- new transport failures. The first unused slot may be a blank baseline;
    -- consuming it gives the following slot a normal companion write window.
    if reason=='Stale reply packet' and slot<=SIZE then
        deadline=GetTime();consecutiveFailures=0
        NS.SetStatus('Restoring the reply channel after reload...')
        return
    end
    consecutiveFailures=reason and consecutiveFailures+1 or 0
    if text then
        NS.LastNativeReply=text
        NS.DisplayNativeReply(text)
        if state>=4 then
            NS.PauseVisual()
            badge:SetText('!');badge:SetTextColor(state==4 and .35 or 1,state==4 and 1 or .5,.55)
            NS.SetStatus(state==4 and 'Reply ready. Link idle; Send starts the next request.' or 'Request finished with a problem. Link idle; details below.')
            return
        end
        NS.SetStatus(state==3 and 'Codex is writing...' or state==2 and 'Codex is working...' or 'Waiting for Codex...')
    elseif reason then NS.SetStatus('Retrying text reception: '..reason) end
    if consecutiveFailures>=3 then
        NS.PauseVisual()
        NS.SetStatus('Text reception paused after repeated errors: '..tostring(reason))
        body:AddMessage('The reply could not be fully received here. It remains available in the companion. Resume preview to retry.')
        return
    end
    if slot>SIZE then NS.PauseVisual();NS.SetStatus('Text channel reached its session limit. Replies remain in the companion.') end
end
local timer=CreateFrame('Frame',nil,UIParent)
timer:RegisterEvent('ADDON_LOADED')
timer:SetScript('OnEvent',function(self,event,name)
    if event~='ADDON_LOADED' or name~=ADDON_NAME then return end
    self:UnregisterEvent('ADDON_LOADED')
    -- SavedVariables are restored after Lua files execute, before this event.
    CodexPixelBridgeState=CodexPixelBridgeState or {}
    slot=tonumber(CodexPixelBridgeState.nextFontSlotV2) or 1
    if slot<1 or slot>SIZE+1 or slot~=math.floor(slot) then slot=SIZE+1 end
    loaded=slot-1;initialized=true
end)
timer:SetScript('OnUpdate',function()
    if not initialized or not active or not session then return end
    local now=GetTime()
    if now>=watchUntil then NS.PauseVisual();NS.SetStatus('Text checks paused after 20 minutes. Resume to check again.');return end
    if not reading then
        if now<deadline then return end
        -- Reserve before first font request; /reload must not reuse a cached path.
        CodexPixelBridgeState.nextFontSlotV2=math.max(tonumber(CodexPixelBridgeState.nextFontSlotV2) or 1,slot+1)
        reading={start=now,nextTry=0,bytes={},index=0}
    end
    if now-reading.start>8 then finish('Slot '..slot..': '..(reading.reason or 'font was not ready'));return end
    if not reading.ready then
        if now<reading.nextTry then return end
        -- The live probe succeeded with one-second retries; preserve that cadence.
        reading.nextTry=now+1
        local path='Interface\\AddOns\\CodexPixelBridge\\'..string.format('fontreply%04d.ttf',slot)
        local ok,result=pcall(meter.SetFont,meter,path,64,'')
        -- Match the working probe: request text layout even while SetFont is
        -- pending. Waiting on its return before setting any text can stall a
        -- lazy loader. A not-yet-assigned font may throw; retry next second.
        pcall(width,'!')
        local current=meter:GetFont()
        local matches=type(current)=='string' and current:lower()==path:lower()
        reading.reason='assignment='..tostring(ok and result)..', font='..tostring(current)
        if not ok or (not result and not matches) then return end
        local low,high=width('!'),width('"')
        reading.reason='calibration '..tostring(low)..' / '..tostring(high)
        if not low or not high or high-low<100 then return end
        reading.low=low;reading.range=high-low;reading.ready=true
    end
    -- Limit measurement work per game frame. No font instructions or game input.
    for _=1,32 do
        local i=reading.index
        local code=0xE000+i
        local char=string.char(224+math.floor(code/4096),128+math.floor(code/64)%64,128+code%64)
        local value=(width(char)-reading.low)*255/reading.range
        local rounded=math.floor(value+.5)
        if rounded<0 or rounded>255 or math.abs(value-rounded)>.20 then finish('Font byte measurement');return end
        reading.bytes[#reading.bytes+1]=string.char(rounded);reading.index=i+1
        if reading.index==512 then
            local packet,reason=NS.ParseNativePacket(table.concat(reading.bytes),session,request,slot)
            if not packet then finish(reason);return end
            local text,state=NS.AcceptNativeFragment(assembly,packet)
            finish(type(state)=='string' and state or nil,text,type(state)=='number' and state or 0)
            return
        end
    end
end)
