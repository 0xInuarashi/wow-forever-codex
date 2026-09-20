-- Bounded visual diagnostics using ordinary documented texture APIs only.
local _, NS = ...
local panel, timer
local base='Interface\\AddOns\\CodexPixelBridge\\'

function NS.ShowProbe()
    if panel then panel:Show(); return end
    panel=CreateFrame('Frame','CodexPixelBridgeProbe',UIParent,'BasicFrameTemplateWithInset')
    panel:SetSize(460,255)
    panel:SetPoint('TOPLEFT',UIParent,'TOPLEFT',24,-60)
    panel:SetFrameStrata('HIGH')
    panel:SetMovable(true); panel:EnableMouse(true); panel:RegisterForDrag('LeftButton')
    panel:SetClampedToScreen(true)
    panel:SetScript('OnDragStart',panel.StartMoving)
    panel:SetScript('OnDragStop',panel.StopMovingOrSizing)
    panel.TitleText:SetText('Codex resource probe 3 - drag to move')
    local textures={}
    local labels={'Same path','Released 10s','Unused slots','Created later'}
    for i=1,4 do
        local label=panel:CreateFontString(nil,'OVERLAY','GameFontNormalSmall')
        label:SetPoint('TOPLEFT',16+(i-1)*110,-35); label:SetText(labels[i])
        local texture=panel:CreateTexture(nil,'ARTWORK')
        texture:SetPoint('TOPLEFT',16+(i-1)*110,-52); texture:SetSize(64,64)
        textures[i]=texture
    end
    local info=panel:CreateFontString(nil,'OVERLAY','GameFontHighlightSmall')
    info:SetPoint('TOPLEFT',16,-124); info:SetWidth(428); info:SetJustifyH('LEFT')
    local ticks,slot=0,0
    local function safeState(texture)
        return tostring(texture:GetTexture())..' / '..tostring(texture:IsObjectLoaded())
    end
    local function display()
        local version,build,_,toc=GetBuildInfo()
        info:SetText('Build '..tostring(version)..' / '..tostring(build)..' TOC '..tostring(toc)
            ..' | tick '..ticks..'/150'
            ..'\nSame: '..safeState(textures[1])..' | Released: '..safeState(textures[2])
            ..'\nSlot '..slot..': '..safeState(textures[3])..' | Later: '..safeState(textures[4])
            ..'\nEach image contains the external writer counter. Compare with its log.'
            ..'\nLater file first loads at 90s. Slot 1 is revisited at 135s.'
            ..'\nClose to stop. This is a test, not a connected chat channel.')
    end
    local function sample()
        if not panel:IsShown() then return end
        ticks=ticks+1
        textures[1]:SetTexture(nil)
        textures[1]:SetTexture(base..'probe.tga')
        -- Retain no assigned resource for ten complete timer intervals.
        if ticks%12==1 then textures[2]:SetTexture(base..'probe_release.tga') end
        if ticks%12==3 then textures[2]:SetTexture(nil) end
        if ticks%15==0 then
            slot=math.floor(ticks/15)
            if slot>8 then slot=1 end
            textures[3]:SetTexture(nil)
            textures[3]:SetTexture(base..string.format('probe_slot%02d.tga',slot))
        end
        if ticks==90 then
            textures[4]:SetTexture(base..'probe_late_v3.tga')
        end
        display()
        if ticks>=150 and timer then timer:Cancel(); timer=nil end
    end
    local function start()
        ticks=0; slot=0
        for _,texture in ipairs(textures) do texture:SetTexture(nil) end
        sample(); timer=C_Timer.NewTicker(1,sample)
    end
    panel:SetScript('OnHide',function()
        if timer then timer:Cancel(); timer=nil end
        for _,texture in ipairs(textures) do texture:SetTexture(nil) end
    end)
    panel:SetScript('OnShow',start)
    start()
end
