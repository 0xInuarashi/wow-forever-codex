-- Bounded public-API comparisons; ordinary font data only, never executable input.
local _,NS=...
local previousControl=NS.FontDiscoveryControl
local panel,readout,run,used
local specs={
    {1,1,'direct',64,'','Direct control'}, {2,1,'object',64,'','Font object control'},
    {3,1,'family',64,'','Font family control'}, {4,1,'direct',64,'','New direct'},
    {5,1,'object',64,'','New font object'}, {6,1,'family',64,'','New font family'},
    {7,1,'direct',64,'','Empty placeholder'}, {8,1,'direct',64,'','Shared placeholder'},
    {9,1,'direct',64,'','Before same size'}, {10,1,'direct',64,'','Before new size'},
    {11,1,'direct',64,'','Before new object'}, {12,1,'direct',64,'','Before new family'},
    {13,1,'direct',64,'','Before new flags'},
    {9,2,'direct',64,'','Reuse same size'}, {10,2,'direct',128,'','Reuse new size'},
    {11,2,'object',64,'','Reuse new object'}, {12,2,'family',64,'','Reuse new family'},
    {13,2,'direct',64,'OUTLINE','Reuse new flags'},
    {4,2,'direct',64,'','New path later retry'}, {14,2,'direct',64,'','Second phase control'},
    {15,2,'direct',128,'','Fresh large-size control'}, {16,2,'direct',64,'OUTLINE','Fresh outline control'},
}
local function stop(message)
    if run then run.active=false end
    if message and readout then readout:SetText(message) end
end
local function metadata(path)
    local function get(name)
        local api=C_UIFileAsset and C_UIFileAsset[name]
        if not api then return 'NA' end
        local ok,value=pcall(api,path)
        if not ok then return 'ERR' end
        if type(value)=='boolean' then return value and '1' or '0' end
        return tostring(value)
    end
    return 'K'..get('IsKnownFile')..' L'..get('IsLooseFile')..' I'..get('GetFileID')
end
local function sample(index,now)
    local r=run.readers[index];local s=specs[index]
    local function finish(status,text)
        run.results[index]={status=status,text=text}
        run.recent[#run.recent+1]=s[6]..': '..(status==1 and text or ('FAIL '..text:gsub('[\r\n].*',''):sub(1,58)))
        -- Release this diagnostic FontString through a normal font assignment.
        if GameFontNormal then
            pcall(r.meter.SetFontObject,r.meter,GameFontNormal)
            pcall(r.meter.SetText,r.meter,'')
        end
    end
    if now-r.start>=20 then finish(2,r.reason or 'Font load timed out');return end
    if now<r.nextTry then return end
    r.nextTry=now+1
    local ok,why=pcall(function()
        if s[3]=='direct' then r.meter:SetFont(r.path,s[4],s[5])
        elseif s[3]=='object' then
            if type(CreateFont)~='function' then error('Font object API unavailable') end
            r.object=r.object or CreateFont('CodexMatrix'..run.token..'Case'..index)
            r.object:SetFont(r.path,s[4],s[5]);r.meter:SetFontObject(r.object)
        else
            if type(CreateFontFamily)~='function' then error('Font family API unavailable') end
            if not r.object then
                -- This client requires all five alphabet members, even when
                -- the test only measures ASCII glyphs through the roman face.
                local members={}
                for _,alphabet in ipairs({'roman','korean','simplifiedchinese','traditionalchinese','russian'}) do
                    members[#members+1]={alphabet=alphabet,file=r.path,height=s[4],flags=s[5]}
                end
                r.object=CreateFontFamily('CodexMatrix'..run.token..'Case'..index,members)
            end
            r.meter:SetFontObject(r.object)
        end
    end)
    local function width(char)
        r.meter:SetText(char..'~');return r.meter:GetUnboundedStringWidth()
    end
    pcall(width,'!') -- Trigger lazy layout even before the assignment resolves.
    if not run.metadata[s[1]] then run.metadata[s[1]]=metadata(r.path) end
    local current=r.meter:GetFont()
    local matches=type(current)=='string' and current:lower()==r.path:lower()
    local errorText=tostring(why):gsub('^.-:%d+: ','')
    if errorText:find('file not found',1,true) then errorText='Font file not found' end
    r.reason=not ok and ('API: '..errorText) or not matches and 'Font path unresolved' or 'Metrics pending'
    if not ok then r.detail=tostring(why);return end
    -- Inheritance/family getters are diagnostic, not proof of readable bytes.
    -- Always try checked decoding; only the observer's exact per-asset nonce
    -- can establish fresh delivery, so fallback or cached text cannot pass.
    local decoded,text,reason=pcall(NS.DecodeFontProbe,width)
    if decoded and text then finish(1,text);return end
    r.reason=not matches and 'Font path unresolved' or decoded and reason or 'Measurement API failed'
end
NS.ShowFontMatrixProbe=function()
    if used then if panel then panel:Show() end;return end
    if NS.IsVisualWatching and NS.IsVisualWatching() then NS.SetStatus('Finish or pause the reply before this test.');return end
    if previousControl and previousControl() then NS.SetStatus('Close the other diagnostic probe first.');return end
    local token=NS.FontMatrixToken
    if type(token)~='string' or #token~=8 or not token:match('^[0-9a-f]+$') then
        NS.SetStatus('Prepare a fresh font options test first.');return
    end
    used=true
    panel=CreateFrame('Frame',nil,UIParent,'BasicFrameTemplateWithInset')
    panel:SetSize(420,205);panel:SetPoint('TOPLEFT',UIParent,'TOPLEFT',12,-52)
    panel:SetMovable(true);panel:EnableMouse(true);panel:RegisterForDrag('LeftButton')
    panel:SetScript('OnDragStart',panel.StartMoving);panel:SetScript('OnDragStop',panel.StopMovingOrSizing)
    panel.TitleText:SetText('Codex font options probe 3')
    readout=panel:CreateFontString(nil,'OVERLAY','GameFontHighlightSmall')
    readout:SetPoint('TOPLEFT',12,-32);readout:SetWidth(396);readout:SetJustifyH('LEFT')
    run={token=token,start=GetTime(),active=true,elapsed=0,readers={},results={},metadata={},recent={},cursor=0}
    panel:SetScript('OnHide',function() stop('Test closed. Use fresh preparation before another run.') end)
    panel:SetScript('OnUpdate',function()
        if not run.active then return end
        if NS.IsVisualWatching and NS.IsVisualWatching() then stop('Test cancelled: chat reception started.');return end
        local now=GetTime();run.elapsed=math.floor(now-run.start)
        if run.elapsed>=165 then stop();return end
        for i,s in ipairs(specs) do
            if not run.readers[i] and run.elapsed>=(s[2]==1 and 30 or 105) then
                local meter=panel:CreateFontString(nil,'OVERLAY')
                -- Give the large-size calibration ample layout space and use
                -- the documented unbounded width getter above.
                meter:SetPoint('TOPLEFT',0,0);meter:SetWidth(2048);meter:SetAlpha(0);meter:SetWordWrap(false);meter:SetNonSpaceWrap(false)
                run.readers[i]={meter=meter,path='Interface\\AddOns\\CodexPixelBridge\\fontmatrix_'..token..'_'..string.format('%02d',s[1])..'.ttf',start=now,nextTry=0}
            end
        end
        -- One bounded 64-byte measurement per frame, with fair retries.
        for _=1,#specs do
            run.cursor=run.cursor%#specs+1
            local i=run.cursor;local r=run.readers[i]
            if r and not run.results[i] and now>=r.nextTry then sample(i,now);break end
        end
        local count=0;for _ in pairs(run.results) do count=count+1 end
        local lines={run.elapsed>=140 and ('Test complete: '..count..' / '..#specs..' results reported.') or ('Testing '..run.elapsed..' / 140 seconds. Results '..count..' / '..#specs..'.')}
        for i=math.max(1,#run.recent-6),#run.recent do lines[#lines+1]=run.recent[i]:gsub('|','||') end
        lines[#lines+1]='Keep the strip visible. This test sends no chat.'
        readout:SetText(table.concat(lines,'\n'))
    end)
    readout:SetText('Waiting for the desktop writer. Keep the top-left strip visible.')
    panel:Show()
end
NS.FontDiscoveryControl=function()
    if not run or not run.active then return previousControl and previousControl() end
    if NS.IsVisualWatching and NS.IsVisualWatching() then stop('Test cancelled: chat reception started.');return end
    local n=math.floor((GetTime()-run.start)*4)%39
    local case,status,payload=n,0,''
    if n>22 then case=n-22;status=3;payload=run.metadata[case] or ''
    elseif run.results[n] then status=run.results[n].status;payload=run.results[n].text end
    payload=payload:sub(1,40)
    local phase=run.elapsed>=140 and 3 or run.elapsed>=75 and 2 or 1
    local body='CPFM'..string.char(2,phase,case,status)..run.token..NS.U32(run.elapsed)
        ..payload..string.rep(string.char(0),40-#payload)
    return body..NS.Adler(body)
end
