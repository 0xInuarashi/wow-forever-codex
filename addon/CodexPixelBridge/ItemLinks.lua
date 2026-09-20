-- Observe normal user-driven chat-link insertion. Never replace Blizzard functions.
local _,NS=...
local edit,panel=NS.PromptEditBox,NS.Panel
local function itemData(link)
    if type(link)~='string' then return end
    local data,label=link:match('|H(item:[^|]+)|h(.-)|h')
    if data and data:match('^item:%d+[:%d%-]*$') then return data,label end
end
local function itemInfo(data)
    local getter=C_Item and C_Item.GetItemInfo or GetItemInfo
    if type(getter)~='function' then return end
    local ok,name,link,quality,level,minimum,kind,subkind=pcall(getter,data)
    if ok then return name,level,minimum,kind,subkind end
end
NS.MakePromptText=function(raw)
    -- Transport readable item identity, exact variant fields and cached basics.
    -- A missing cache entry still sends the linked name and ID without blocking.
    local plain=raw:gsub('|cn[%w_]+:',''):gsub('|c%x%x%x%x%x%x%x%x',''):gsub('|r','')
    return (plain:gsub('|H([^|]+)|h(.-)|h',function(data,label)
        if not data:match('^item:%d+[:%d%-]*$') then return label end
        local id=data:match('^item:(%d+)')
        local name,level,minimum,kind,subkind=itemInfo(data)
        local details={'WoW Forever item ID '..id,'link='..data}
        if kind and kind~='' then details[#details+1]=kind..(subkind and subkind~='' and (' / '..subkind) or '') end
        if level and level>0 then details[#details+1]='item level '..level end
        if minimum and minimum>0 then details[#details+1]='requires level '..minimum end
        return (name and ('['..name..']') or label)..' ('..table.concat(details,'; ')..')'
    end))
end
NS.InsertItemLink=function(link)
    if not panel:IsShown() or not edit:HasFocus() or not itemData(link) then return false end
    if #edit:GetText()+#link+1>1280 then
        NS.SetStatus('Not enough room for this item link. Shorten the message first.');return false
    end
    edit:Insert(link..' ')
    return true
end
-- A secure post-hook cannot return "handled" to the bag click. Cancel only
-- the redundant dialog opened synchronously for the item we just inserted.
-- Hide invokes Blizzard's own OnHide cleanup; no stack action is performed.
local pendingLink
local function observeLink(link)
    pendingLink=nil
    if NS.InsertItemLink(link) and IsModifiedClick('CHATLINK') then pendingLink=itemData(link) end
end
local function dismissLinkedSplit(self,_,owner)
    local inserted=pendingLink;pendingLink=nil
    if not inserted or not panel:IsShown() or not edit:HasFocus() or not IsModifiedClick('SPLITSTACK') then return end
    if self:IsProtected() or not owner or type(owner.GetBagID)~='function' or type(owner.GetID)~='function' then return end
    local getter=C_Container and C_Container.GetContainerItemLink or GetContainerItemLink
    if type(getter)=='function' and itemData(getter(owner:GetBagID(),owner:GetID()))==inserted then self:Hide() end
end
local hooked,splitHooked=false,false
local function installHook()
    if type(hooksecurefunc)~='function' then return end
    if not hooked then
        if ChatFrameUtil and type(ChatFrameUtil.InsertLink)=='function' then
            hooksecurefunc(ChatFrameUtil,'InsertLink',observeLink);hooked=true
        elseif type(ChatEdit_InsertLink)=='function' then
            hooksecurefunc('ChatEdit_InsertLink',observeLink);hooked=true
        end
    end
    if not splitHooked and StackSplitFrame and type(StackSplitFrame.OpenStackSplitFrame)=='function' then
        hooksecurefunc(StackSplitFrame,'OpenStackSplitFrame',dismissLinkedSplit);splitHooked=true
    end
end
installHook()
local loader=CreateFrame('Frame')
loader:RegisterEvent('ADDON_LOADED')
loader:SetScript('OnEvent',function(self)
    installHook()
    if hooked and splitHooked then self:UnregisterEvent('ADDON_LOADED') end
end)
loader:SetScript('OnUpdate',function() pendingLink=nil end)
edit:SetScript('OnReceiveDrag',function()
    if not panel:IsShown() then return end
    local kind,id,link=GetCursorInfo()
    if kind~='item' then return end
    if not itemData(link) then
        local getter=C_Item and C_Item.GetItemInfo or GetItemInfo
        if type(getter)=='function' then
            local ok,_,cached=pcall(getter,id)
            if ok then link=cached end
        end
    end
    edit:SetFocus()
    if NS.InsertItemLink(link) then ClearCursor() end
end)
