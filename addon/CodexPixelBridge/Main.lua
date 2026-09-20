local _, NS = ...
local panel = CreateFrame('Frame', 'CodexPixelBridgePanel', UIParent, 'BasicFrameTemplateWithInset')
panel:SetSize(550,740); panel:SetPoint('CENTER'); panel:SetMovable(true); panel:EnableMouse(true)
panel:RegisterForDrag('LeftButton')
panel:SetScript('OnDragStart', panel.StartMoving); panel:SetScript('OnDragStop', panel.StopMovingOrSizing)
panel.TitleText:SetText('Codex | Reply preview')
NS.Panel=panel
local status=panel:CreateFontString(nil,'OVERLAY','GameFontNormalSmall')
status:SetPoint('TOPLEFT',16,-34); status:SetText('Send a prompt. Replies update here while the companion is running.')
NS.SetStatus=function(text) status:SetText(text) end
local history=CreateFrame('ScrollingMessageFrame',nil,panel)
history:SetPoint('TOPLEFT',16,-58); history:SetSize(515,48); history:SetFontObject(GameFontHighlightSmall)
history:SetJustifyH('LEFT'); history:SetMaxLines(100); history:EnableMouseWheel(true)
history:SetFading(false)
history:SetScript('OnMouseWheel',function(self,d) if d>0 then self:ScrollUp() else self:ScrollDown() end end)
local edit=CreateFrame('EditBox',nil,panel,'InputBoxTemplate')
NS.PromptEditBox=edit
edit:SetPoint('BOTTOMLEFT',22,44); edit:SetSize(400,28); edit:SetAutoFocus(false); edit:SetMaxBytes(1280)
edit:SetCountInvisibleLetters(true)
edit:SetScript('OnEscapePressed',function(self) self:ClearFocus() end)
panel:SetScript('OnHide',function() edit:ClearFocus() end)
function CodexPixelBridgeToggle()
    panel:SetShown(not panel:IsShown())
end
BINDING_HEADER_CODEXPIXELBRIDGE='Codex'
BINDING_NAME_CODEXPIXELBRIDGE_TOGGLE='Show / hide Codex panel'
local hide=CreateFrame('Button',nil,panel,'UIPanelButtonTemplate')
hide:SetSize(70,22); hide:SetPoint('BOTTOMRIGHT',-16,10); hide:SetText('Hide')
hide:SetScript('OnClick',function() panel:Hide() end)
local hint=panel:CreateFontString(nil,'OVERLAY','GameFontNormalSmall')
hint:SetPoint('BOTTOMLEFT',16,16); hint:SetText('/codex show/hide | Shift-click items to ask; hover reply links for details')
local minimap=CreateFrame('Button','CodexPixelBridgeMinimapButton',Minimap or UIParent,'UIPanelButtonTemplate')
NS.Minimap=minimap
minimap:SetSize(26,26); minimap:SetText('C')
if Minimap then minimap:SetPoint('BOTTOMLEFT',Minimap,'BOTTOMLEFT',-6,-6)
else minimap:SetPoint('TOPRIGHT',UIParent,'TOPRIGHT',-24,-200) end
minimap:SetScript('OnClick',CodexPixelBridgeToggle)
minimap:SetScript('OnEnter',function(self)
    GameTooltip:SetOwner(self,'ANCHOR_LEFT')
    GameTooltip:SetText('Codex')
    GameTooltip:AddLine('Click to show or hide the chat panel.',1,1,1)
    GameTooltip:AddLine('Reply alerts come from the desktop companion.',1,0.82,0,true)
    GameTooltip:Show()
end)
minimap:SetScript('OnLeave',function() GameTooltip:Hide() end)
local previous=CreateFrame('Button',nil,panel,'UIPanelButtonTemplate')
previous:SetSize(120,24); previous:SetPoint('BOTTOMLEFT',16,76); previous:SetText('Previous page')
previous:SetScript('OnClick',function() if NS.ChangeVisualPage then NS.ChangeVisualPage(-1) end end)
local nextPage=CreateFrame('Button',nil,panel,'UIPanelButtonTemplate')
nextPage:SetSize(120,24); nextPage:SetPoint('LEFT',previous,'RIGHT',10,0); nextPage:SetText('Next page')
nextPage:SetScript('OnClick',function() if NS.ChangeVisualPage then NS.ChangeVisualPage(1) end end)
NS.ConfigureNative=function()
    previous:SetText('Scroll up');nextPage:SetText('Scroll down')
end
local pause=CreateFrame('Button',nil,panel,'UIPanelButtonTemplate')
pause:SetSize(140,24); pause:SetPoint('BOTTOMRIGHT',-16,76); pause:SetText('Resume preview')
NS.SetWatchState=function(active) pause:SetText(active and 'Pause preview' or 'Resume preview') end
local function pausePreview()
    if NS.PauseVisual then NS.PauseVisual() end
    status:SetText('Preview paused; the strip is steady. Resume or Send to continue.')
end
local function resumePreview()
    if NS.ResumeVisual then NS.ResumeVisual() end
    status:SetText('Preview checks resumed. Strip activity does not mean Codex is still working.')
end
pause:SetScript('OnClick',function()
    if NS.IsVisualWatching and NS.IsVisualWatching() then pausePreview() else resumePreview() end
end)
local send=CreateFrame('Button',nil,panel,'UIPanelButtonTemplate')
send:SetPoint('LEFT',edit,'RIGHT',10,0); send:SetSize(90,26); send:SetText('Send')
local strip=CreateFrame('Frame',nil,UIParent)
strip:SetFrameStrata('TOOLTIP'); strip:SetSize(512,16); strip:SetPoint('TOPLEFT',UIParent,'TOPLEFT',8,-8)
strip:SetScale(1/UIParent:GetEffectiveScale()); strip:EnableMouse(false)
local cells={}
for i=0,511 do
    local t=strip:CreateTexture(nil,'OVERLAY'); t:SetSize(4,4)
    t:SetPoint('TOPLEFT',strip,'TOPLEFT',(i%128)*4,-math.floor(i/128)*4)
    t:SetColorTexture(0,0,0,1); cells[i+1]=t
end
local session=NS.U32(GetServerTime())..NS.U32(math.floor(GetTime()*1000)%4294967296)
local messages, frames, cursor, sequence, elapsed = {}, {}, 1, 0, 0
local controlTurn=false
local lastData
local function submit()
    local text=edit:GetText()
    if not text:find('%S') then return end
    if NS.MakePromptText then text=NS.MakePromptText(text) end
    if #text>1280 then
        status:SetText('Message plus item details is too long. Shorten it or link fewer items.');return
    end
    sequence=sequence+1
    messages[#messages+1]=NS.Encode(text,session,sequence)
    if #messages>8 then table.remove(messages,1) end
    frames={}
    for _, group in ipairs(messages) do for _, frame in ipairs(group) do frames[#frames+1]=frame end end
    cursor=1
    history:AddMessage('You #'..sequence..': '..text:gsub('|','||'))
    status:SetText('Prompt #'..sequence..' broadcasting. Strip activity means preview checks, not agent progress.')
    if NS.OnPromptSubmitted then NS.OnPromptSubmitted(sequence) end
    edit:SetText(''); edit:ClearFocus()
end
send:SetScript('OnClick',submit); edit:SetScript('OnEnterPressed',submit)
strip:SetScript('OnUpdate',function(self,dt)
    elapsed=elapsed+dt
    if elapsed<0.25 then return end
    elapsed=0
    self:SetScale(1/UIParent:GetEffectiveScale())
    local data
    controlTurn=not controlTurn
    local watching=not NS.IsVisualWatching or NS.IsVisualWatching()
    if NS.VisualControl and (not watching or controlTurn or #frames==0) then data=NS.VisualControl(session)
    elseif #frames>0 then data=frames[cursor]; cursor=cursor%#frames+1 end
    -- An opt-in, bounded diagnostic can report through the same optical strip.
    -- It cancels itself if normal reception starts. These are never prompt frames.
    if NS.FontDiscoveryControl then data=NS.FontDiscoveryControl() or data end
    if not data or data==lastData then return end
    lastData=data
    for i=0,511 do
        local v=math.floor(data:byte(math.floor(i/8)+1)/2^(7-i%8))%2
        cells[i+1]:SetColorTexture(v,v,v,1)
    end
end)
SLASH_CODEXPIXELBRIDGE1='/cpb'
SLASH_CODEXPIXELBRIDGE2='/codex'
SlashCmdList.CODEXPIXELBRIDGE=function(arg)
    arg=arg:lower():match('^%s*(.-)%s*$')
    if arg=='show' then panel:Show(); return end
    if arg=='hide' then panel:Hide(); return end
    if arg=='probe' then NS.ShowProbe(); return end
    if arg=='fontprobe' then NS.ShowFontProbe(); return end
    if arg=='latefontprobe' and NS.ShowLateFontProbe then NS.ShowLateFontProbe(); return end
    if arg=='fontmatrix' and NS.ShowFontMatrixProbe then NS.ShowFontMatrixProbe(); return end
    if arg=='pause' then pausePreview(); return end
    if arg=='resume' then resumePreview(); return end
    if arg=='clear' then
        messages={}; frames={}; pausePreview()
        status:SetText('Prompt repeats and preview paused. Received jobs continue in the companion.'); return
    end
    CodexPixelBridgeToggle()
end
history:AddMessage('Click the message box, then Shift-click an item to link it. You can also drop an item into the box.')
