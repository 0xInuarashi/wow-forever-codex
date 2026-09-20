-- First-use texture bank, consumed only while watching for a submitted reply.
-- No URL API, external Lua, memory access or generated input.
local _,NS=...
local SIZE,BLOCK,INTERVAL=4096,32,5
local slot,loaded,request,page=1,0,0,1
local active,deadline,watchUntil=false,0,0
local textures,badges={},{}
local panel=NS.Panel
local viewport=CreateFrame('Frame',nil,panel)
viewport:SetSize(512,512); viewport:SetPoint('TOPLEFT',16,-118)
local empty=viewport:CreateFontString(nil,'BACKGROUND','GameFontHighlight')
empty:SetPoint('CENTER'); empty:SetWidth(460)
empty:SetText('Send a prompt to see its reply here.\nKeep the desktop companion running.')
local badge=CreateFrame('Frame',nil,NS.Minimap)
badge:SetSize(18,18); badge:SetPoint('TOPRIGHT',NS.Minimap,'TOPRIGHT',7,7)
for i=1,BLOCK do
    local t=viewport:CreateTexture(nil,'ARTWORK')
    t:SetAllPoints(viewport); t:Hide(); textures[i]=t
    local b=badge:CreateTexture(nil,'ARTWORK')
    b:SetAllPoints(badge); b:SetTexCoord(0,0.0625,0,0.0625); b:Hide(); badges[i]=b
end
local function watch()
    if slot>SIZE then
        NS.SetStatus('Reply preview reached its session limit. Replies remain in the companion.')
        return
    end
    if not active then deadline=GetTime()+6 end
    active=true; watchUntil=GetTime()+630
    if NS.SetWatchState then NS.SetWatchState(true) end
end
NS.IsVisualWatching=function() return active end
NS.PauseVisual=function()
    active=false
    if NS.SetWatchState then NS.SetWatchState(false) end
end
NS.ResumeVisual=function()
    if request>0 then watch() end
end
NS.OnPromptSubmitted=function(sequence)
    request=sequence; page=1; watch()
end
NS.ChangeVisualPage=function(delta)
    page=math.max(1,math.min(128,page+delta))
    if request>0 then watch() end
end
local function u16(n) return string.char(math.floor(n/256)%256,n%256) end
NS.VisualControl=function(session)
    local remaining=active and math.max(0,math.min(6000,math.floor((deadline-GetTime())*1000))) or 0
    local data=NS.U32(slot)..NS.U32(remaining)..u16(page)..u16(active and 1 or 0)..NS.U32(request)..NS.U32(loaded)
    local body='CPBC'..string.char(1,#data,0,1)..session..NS.U32(0)..data..string.rep(string.char(0),40-#data)
    return body..NS.Adler(body)
end
local timer=CreateFrame('Frame',nil,UIParent)
timer:SetScript('OnUpdate',function()
    if not active then return end
    local now=GetTime()
    if now>=watchUntil or slot>SIZE then
        NS.PauseVisual()
        NS.SetStatus('Preview paused after 10.5 minutes. Resume preview to check for updates.')
        return
    end
    if now<deadline then return end
    local index=(slot-1)%BLOCK+1
    if index==1 then
        for i=1,BLOCK do textures[i]:Hide(); textures[i]:SetTexture(nil); badges[i]:Hide(); badges[i]:SetTexture(nil) end
    end
    local path='Interface\\AddOns\\CodexPixelBridge\\'..string.format('reply%04d.tga',slot)
    textures[index]:SetTexture(path); textures[index]:Show()
    badges[index]:SetTexture(path); badges[index]:Show()
    loaded=slot; slot=slot+1; deadline=now+INTERVAL
    if slot>SIZE then
        NS.PauseVisual()
        NS.SetStatus('Reply preview reached its session limit. Replies remain in the companion.')
    end
end)
