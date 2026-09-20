-- Opt-in discovery test. Only documented font/layout APIs; no executable input.
local _,NS=...
local panel,readout,run
local used=false
local names={'control','late1','late2'}
local starts={30,50,100}
local function stop(message)
    if run then run.active=false;run.reading=nil end
    if message and readout then readout:SetText(message) end
end
local function finish(status,text)
    local r=run.reading
    run.results[r.case]={status=status,text=text}
    run.reading=nil
end
local function step(now)
    local r=run.reading
    if not r then return end
    local function width(char)
        r.meter:SetText(char..'~');return r.meter:GetStringWidth()
    end
    if now-r.start>=12 then finish(2,r.reason or 'Font load timed out');return end
    if not r.ready then
        if now<r.nextTry then return end
        r.nextTry=now+1
        local ok,assigned=pcall(r.meter.SetFont,r.meter,r.path,64,'')
        -- Trigger lazy layout even when the setter has not resolved yet.
        pcall(width,'!')
        local current=r.meter:GetFont()
        local matches=type(current)=='string' and current:lower()==r.path:lower()
        r.reason='SetFont='..tostring(ok and assigned)..'; path='..(matches and 'match' or 'missing')
        if not ok or not matches then return end
        local good,low,high=pcall(function() return width('!'),width('"') end)
        if not good or not low or not high or high-low<100 then r.reason='Calibration not ready';return end
        r.low=low;r.range=high-low;r.ready=true
    end
    for _=1,32 do
        local code=0xE000+r.index
        local char=string.char(224+math.floor(code/4096),128+math.floor(code/64)%64,128+code%64)
        local ok,w=pcall(width,char)
        if not ok or not w then finish(2,'Measurement API failed');return end
        local value=(w-r.low)*255/r.range
        local rounded=math.floor(value+.5)
        if rounded<0 or rounded>255 or math.abs(value-rounded)>.20 then finish(2,'Invalid byte measurement');return end
        r.bytes[#r.bytes+1]=string.char(rounded);r.index=r.index+1
        if r.index==512 then
            local packet,reason=NS.ParseNativePacket(table.concat(r.bytes),run.token,1,r.case)
            if not packet then finish(2,reason);return end
            if packet.state~=4 or packet.part~=1 or packet.total~=1 or #packet.text>40 then
                finish(2,'Invalid discovery payload');return
            end
            finish(1,packet.text);return
        end
    end
end
NS.ShowLateFontProbe=function()
    if used then
        if panel then panel:Show() end
        return
    end
    if NS.IsVisualWatching and NS.IsVisualWatching() then
        NS.SetStatus('Finish or pause the reply before starting the font discovery test.');return
    end
    local token=NS.FontDiscoveryToken
    if type(token)~='string' or #token~=8 or not token:match('^[0-9a-f]+$') then
        NS.SetStatus('Prepare the font discovery test in the companion tools first.');return
    end
    used=true
    panel=CreateFrame('Frame',nil,UIParent,'BasicFrameTemplateWithInset')
    panel:SetSize(380,165);panel:SetPoint('TOPLEFT',UIParent,'TOPLEFT',12,-52)
    panel:SetMovable(true);panel:EnableMouse(true);panel:RegisterForDrag('LeftButton')
    panel:SetScript('OnDragStart',panel.StartMoving);panel:SetScript('OnDragStop',panel.StopMovingOrSizing)
    panel.TitleText:SetText('Codex new-font discovery 1')
    readout=panel:CreateFontString(nil,'OVERLAY','GameFontHighlightSmall')
    readout:SetPoint('TOPLEFT',12,-32);readout:SetWidth(356);readout:SetJustifyH('LEFT')
    run={token=token,start=GetTime(),active=true,results={},nextCase=1,elapsed=0}
    panel:SetScript('OnHide',function() stop('Test closed. Prepare fresh filenames before repeating.') end)
    panel:SetScript('OnUpdate',function()
        if not run.active then return end
        if NS.IsVisualWatching and NS.IsVisualWatching() then stop('Test cancelled: chat reception started.');return end
        local now=GetTime();local elapsed=now-run.start;run.elapsed=math.floor(elapsed)
        if elapsed>=140 then stop();return end
        if run.nextCase<=3 and elapsed>=starts[run.nextCase] and not run.reading then
            local case=run.nextCase;run.nextCase=case+1
            local meter=panel:CreateFontString(nil,'OVERLAY')
            meter:SetPoint('TOPLEFT',0,0);meter:SetAlpha(0)
            meter:SetWordWrap(false);meter:SetNonSpaceWrap(false)
            run.reading={case=case,start=now,nextTry=0,index=0,bytes={},meter=meter,
                path='Interface\\AddOns\\CodexPixelBridge\\fontdiscover_'..token..'_'..names[case]..'.ttf'}
        end
        step(now)
        local lines={elapsed<120 and ('Testing '..math.floor(elapsed)..' / 120 seconds. Keep the strip visible.') or 'Test complete. Results sent to the desktop.'}
        for i,name in ipairs(names) do
            local r=run.results[i]
            lines[#lines+1]=name..': '..(r and ((r.status==1 and 'DECODED ' or 'FAIL ')..r.text:gsub('|','||')) or 'waiting')
        end
        lines[#lines+1]='Only diagnostic font assets are written. No chat is sent.'
        readout:SetText(table.concat(lines,'\n'))
    end)
    readout:SetText('Waiting for the desktop test writer. Keep the top-left strip visible.')
    panel:Show()
end
NS.FontDiscoveryControl=function()
    if not run or not run.active then return end
    if NS.IsVisualWatching and NS.IsVisualWatching() then stop('Test cancelled: chat reception started.');return end
    local case=math.floor((GetTime()-run.start)*4)%4
    local r=run.results[case]
    local phase=run.elapsed>=120 and 3 or run.elapsed>=70 and 2 or 1
    local payload=r and r.text:sub(1,40) or ''
    local body='CPFD'..string.char(1,phase,case,r and r.status or 0)..run.token..NS.U32(run.elapsed)
        ..payload..string.rep(string.char(0),40-#payload)
    return body..NS.Adler(body)
end
