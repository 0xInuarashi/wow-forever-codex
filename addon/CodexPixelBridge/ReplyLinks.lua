-- Only explicit [label](item:ID[:variant fields]) references become links.
-- All other response bytes stay literal. WoW supplies the name and quality.
local _,NS=...
local body,panel=NS.NativeBody,NS.Panel
local MAX_ITEMS,MAX_LINKS=32,128
local current,allowed,requested,itemCount=nil,{},{},0
local dirty=false
local hover=CreateFrame('GameTooltip','CodexPixelBridgeReplyTooltip',UIParent,'GameTooltipTemplate')
local function escape(text) return (text:gsub('|','||')) end
local function itemID(data)
    if type(data)~='string' or #data>320 or not data:match('^item:%d+[:%d%-]*$') then return end
    local id,tail=data:match('^item:(%d+)(.*)$')
    if #id>10 or tonumber(id)<1 or tonumber(id)>2147483647 then return end
    local fields=0
    for field in tail:gmatch(':([^:]*)') do
        fields=fields+1
        if fields>64 or #field>11 or (field~='' and (not field:match('^%-?%d+$') or math.abs(tonumber(field))>2147483647)) then return end
    end
    -- Disallow a stray minus immediately following the item ID.
    if tail~='' and tail:sub(1,1)~=':' then return end
    return tonumber(id)
end
local function itemLink(data,id)
    local getter=C_Item and C_Item.GetItemInfo or GetItemInfo
    if type(getter)~='function' then return end
    local ok,name,canonical,quality=pcall(getter,data)
    if not ok or type(name)~='string' or name=='' or type(canonical)~='string' then return end
    if itemID(canonical:match('|H(item:[^|]+)|h'))~=id then return end
    local color='ffffffff'
    local colorGetter=C_Item and C_Item.GetItemQualityColor or GetItemQualityColor
    if type(colorGetter)=='function' and type(quality)=='number' then
        local good,_,_,_,hex=pcall(colorGetter,quality)
        if good and type(hex)=='string' and hex:match('^%x%x%x%x%x%x%x%x$') then color=hex end
    end
    name=name:gsub('[%c%[%]]','')
    return '|c'..color..'|H'..data..'|h['..escape(name)..']|h|r'
end
local function render(preserveScroll)
    if not current then return end
    local offset=preserveScroll and body:GetScrollOffset()
    local chunks,loads={},{}
    local cursor,count=1,0
    allowed={}
    while count<MAX_LINKS do
        local first,last,label,data=current:find('%[([^%[%]\r\n]+)%]%((item:[^%s%(%)]+)%)',cursor)
        if not first then break end
        chunks[#chunks+1]=escape(current:sub(cursor,first-1))
        local id=itemID(data)
        if id and not requested[id] and itemCount<MAX_ITEMS then
            itemCount=itemCount+1;requested[id]=true;loads[#loads+1]=id
        end
        local link=id and requested[id] and itemLink(data,id)
        if link then
            allowed[data]=link;chunks[#chunks+1]=link
        elseif id then
            chunks[#chunks+1]=escape(label)..' (item #'..id..')'
        else
            chunks[#chunks+1]=escape(current:sub(first,last))
        end
        cursor=last+1;count=count+1
    end
    chunks[#chunks+1]=escape(current:sub(cursor))
    hover:Hide()
    body:Clear();body:AddMessage(table.concat(chunks),1,1,1)
    if offset then body:SetScrollOffset(offset) else body:ScrollToTop() end
    -- Request only referenced uncached items, once each per prompt. Register
    -- before calling: ITEM_DATA_LOAD_RESULT can be delivered synchronously.
    for _,id in ipairs(loads) do
        if not itemLink('item:'..id,id) and C_Item and type(C_Item.RequestLoadItemDataByID)=='function' then
            pcall(C_Item.RequestLoadItemDataByID,id)
        end
    end
end
NS.ClearReplyLinks=function()
    current=nil;allowed={};requested={};itemCount=0;dirty=false;hover:Hide()
end
NS.DisplayNativeReply=function(text)
    current=text;render(false)
end
body:SetHyperlinksEnabled(true)
body:SetScript('OnHyperlinkEnter',function(self,data)
    if not allowed[data] or not panel:IsShown() then return end
    hover:SetOwner(self,'ANCHOR_CURSOR_RIGHT')
    local ok=pcall(hover.SetHyperlink,hover,data)
    if ok then hover:Show() else hover:Hide() end
end)
body:SetScript('OnHyperlinkLeave',function() hover:Hide() end)
body:SetScript('OnHyperlinkClick',function(self,data,_,button)
    local link=allowed[data]
    if not link or not panel:IsShown() or button~='LeftButton' then return end
    if IsModifiedClick('CHATLINK') then
        -- A real Shift-click inserts into a focused normal chat draft, or the
        -- Codex draft. Neither path sends a message or performs an item action.
        local active=ChatFrameUtil and ChatFrameUtil.GetActiveWindow and ChatFrameUtil.GetActiveWindow()
        if active and active:HasFocus() and ChatFrameUtil.InsertLink then
            ChatFrameUtil.InsertLink(link)
        else
            NS.PromptEditBox:SetFocus();NS.InsertItemLink(link)
        end
    elseif type(SetItemRef)=='function' then
        SetItemRef(data,link,button,self)
    end
end)
panel:HookScript('OnHide',function() hover:Hide() end)
local events=CreateFrame('Frame')
events:RegisterEvent('ITEM_DATA_LOAD_RESULT')
events:SetScript('OnEvent',function(_,_,id)
    if requested[id] then dirty=true end
end)
events:SetScript('OnUpdate',function()
    if dirty then dirty=false;render(true) end
end)
