-- Opt-in probe: documented font assignment and width measurements only.
-- Decoded data is plain text, never executable Lua or a game command.
local _,NS=...
local panel,meter,readout,timer
local function decode(width)
    local low,high=width('!'),width('"')
    if not low or not high or high-low<100 then return nil,'Invalid calibration' end
    local bytes={}
    for i=0,63 do
        local value=(width(string.char(35+i))-low)*255/(high-low)
        local rounded=math.floor(value+0.5)
        if rounded<0 or rounded>255 or math.abs(value-rounded)>0.20 then return nil,'Width did not resolve to a byte' end
        bytes[#bytes+1]=string.char(rounded)
    end
    local data=table.concat(bytes)
    if data:sub(1,4)~='CFP1' then return nil,'Header mismatch' end
    if NS.Adler(data:sub(1,60))~=data:sub(61,64) then return nil,'Checksum mismatch' end
    local length=data:byte(9)
    if length>51 then return nil,'Invalid payload length' end
    for i=10+length,60 do if data:byte(i)~=0 then return nil,'Invalid padding' end end
    return data:sub(10,9+length)
end
NS.DecodeFontProbe=decode
NS.ShowFontProbe=function()
    if not panel then
        panel=CreateFrame('Frame',nil,UIParent,'BasicFrameTemplateWithInset')
        panel:SetSize(380,205); panel:SetPoint('TOPLEFT',UIParent,'TOPLEFT',12,-52)
        panel:SetMovable(true); panel:EnableMouse(true); panel:RegisterForDrag('LeftButton')
        panel:SetScript('OnDragStart',panel.StartMoving); panel:SetScript('OnDragStop',panel.StopMovingOrSizing)
        panel.TitleText:SetText('Codex font byte probe 2')
        readout=panel:CreateFontString(nil,'OVERLAY','GameFontHighlightSmall')
        readout:SetPoint('TOPLEFT',12,-32); readout:SetWidth(356); readout:SetJustifyH('LEFT')
        meter=panel:CreateFontString(nil,'OVERLAY')
        meter:SetPoint('TOPLEFT',12,-180); meter:SetAlpha(0)
        meter:SetWordWrap(false); meter:SetNonSpaceWrap(false)
        panel:SetScript('OnHide',function() if timer then timer:Cancel(); timer=nil end end)
    end
    if timer then timer:Cancel() end
    panel:Show()
    local tick,results,pending=0,{},nil
    local function sample(slot,label,attempt)
        local assigned,success=pcall(meter.SetFont,meter,'Interface\\AddOns\\CodexPixelBridge\\'..string.format('fontprobe%02d.ttf',slot),64,'')
        local function width(char)
            -- A constant final glyph keeps trailing outline/bearing effects equal.
            meter:SetText(char..'~')
            return meter:GetStringWidth()
        end
        local ok,text,reason=pcall(decode,width)
        if not ok then text=nil; reason='Measurement API failed' end
        if not assigned or not success then text=nil; reason='Font not ready' end
        if not text and attempt<8 then
            pending={slot,label,attempt+1}
            return
        end
        pending=nil
        results[#results+1]=label..': '..(text and ('VALID '..text:gsub('|','||')) or ('FAIL '..tostring(reason)))
    end
    local function update()
        tick=tick+1
        if pending then sample(unpack(pending)) end
        if tick==1 then sample(5,'Baseline 5',1) end
        if tick==40 then sample(6,'Fresh slot 6',1) end
        if tick==80 then sample(7,'Fresh slot 7',1) end
        if tick==120 then sample(8,'Fresh slot 8',1) end
        if tick==140 then sample(6,'Revisit slot 6',1) end
        readout:SetText('Tick '..tick..' / 145. First-use checks at 40, 80, 120.\n'..table.concat(results,'\n')..'\nThis is a test, not the active reply channel.')
        if tick>=145 then timer:Cancel(); timer=nil end
    end
    readout:SetText('Starting font width test. No game input or network request.')
    timer=C_Timer.NewTicker(1,update)
end
