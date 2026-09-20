from pathlib import Path
import unittest
from tests import test_item_links

ROOT=Path(__file__).resolve().parents[1]


class ReplyLinkTests(unittest.TestCase):
    def setUp(self):
        fixture=test_item_links.ItemLinkTests();fixture.setUp();fixture.load()
        self.lua,self.ns=fixture.lua,fixture.ns
        self.lua.execute(br'''
        body=CreateFrame('ScrollingMessageFrame');NS.NativeBody=body
        function body:Clear() self.messages={} end
        function body:AddMessage(text,r,g,b) self.messages={text};self.color={r,g,b} end
        function body:GetScrollOffset() return self.offset or 0 end
        function body:SetScrollOffset(offset) self.offset=offset end
        function body:ScrollToTop() self.offset=100 end
        function body:SetHyperlinksEnabled(enabled) self.hyperlinks=enabled end
        function NS.Panel:HookScript(key,fn)
            local previous=self.scripts[key]
            self.scripts[key]=function(...) if previous then previous(...) end;fn(...) end
        end
        local oldCreateFrame=CreateFrame
        function CreateFrame(kind,name,...)
            local frame=oldCreateFrame(kind,name,...)
            if name then _G[name]=frame end
            if kind=='GameTooltip' then
                function frame:SetOwner(owner) self.owner=owner end
                function frame:SetHyperlink(data) tooltipCalls=tooltipCalls+1;self.data=data end
            end
            return frame
        end
        cache={[118]='Minor Healing Potion',[3371]='Empty Vial',[12345]='Caf\195\169 Blade'}
        loadedRequests={};infoCalls=0;tooltipCalls=0;clickCalls=0
        C_Item={
            GetItemInfo=function(data)
                infoCalls=infoCalls+1
                local id=tonumber(data:match('^item:(%d+)'))
                if cache[id] then return cache[id],'|H'..data..'|h['..cache[id]..']|h',2 end
            end,
            GetItemQualityColor=function() return 0.1,1,0,'ff1eff00' end,
            RequestLoadItemDataByID=function(id) loadedRequests[#loadedRequests+1]=id end,
        }
        function SetItemRef(data,text,button) clickCalls=clickCalls+1;clickedData=data;clickedText=text end
        modified=false
        function IsModifiedClick(kind) return modified and kind=='CHATLINK' end
        function ChatFrameUtil.GetActiveWindow() return activeChat end
        function loadEvent(id,success)
            for _,w in ipairs(widgets) do
                if w.scripts.OnEvent then w.scripts.OnEvent(w,'ITEM_DATA_LOAD_RESULT',id,success) end
            end
        end
        function update()
            for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0) end end
        end
        ''')
        self.lua.execute((ROOT/'addon/CodexPixelBridge/ReplyLinks.lua').read_bytes(),b'CPB',self.ns)

    def display(self,text):
        self.ns[b'DisplayNativeReply'](text.encode())
        return self.ns[b'NativeBody'][b'messages'][1].decode()

    def test_game_name_color_variant_and_utf8_replace_only_explicit_item_references(self):
        result=self.display('Use [wrong name](item:12345:17:0:0:0:0:-6:42:7:0), plus [Potion](item:118). café 🌏')
        self.assertIn('|cff1eff00|Hitem:12345:17:0:0:0:0:-6:42:7:0|h[Café Blade]|h|r',result)
        self.assertIn('|Hitem:118|h[Minor Healing Potion]',result)
        self.assertNotIn('wrong name',result)
        self.assertIn('café 🌏',result)
        self.lua.execute(b'assert(body.hyperlinks and #loadedRequests==0);assert(body.color[1]==1 and body.color[2]==1 and body.color[3]==1)')

    def test_uncached_load_completes_asynchronously_without_resetting_scroll_or_repeating_requests(self):
        first=self.display('Try [Unknown](item:999).')
        self.assertEqual(first,'Try Unknown (item #999).')
        self.lua.execute(b'''
        assert(#loadedRequests==1 and loadedRequests[1]==999)
        NS.DisplayNativeReply('Try [Unknown](item:999).');assert(#loadedRequests==1)
        body.offset=17;cache[999]='Game name';loadEvent(999,true)
        assert(not body.messages[1]:find('|H',1,true));update()
        assert(body.messages[1]:find('|Hitem:999|h[Game name]',1,true));assert(body.offset==17)
        assert(#loadedRequests==1)
        ''')

    def test_failed_missing_and_synchronous_item_loads_leave_readable_text(self):
        self.display('Try [Unavailable](item:999).')
        self.lua.execute(b'''
        loadEvent(999,false);update();assert(body.messages[1]=='Try Unavailable (item #999).')
        update();assert(#loadedRequests==1)
        NS.ClearReplyLinks()
        C_Item.RequestLoadItemDataByID=function(id) cache[id]='Loaded now';loadEvent(id,true) end
        NS.DisplayNativeReply('[Soon](item:777)');update()
        assert(body.messages[1]:find('|Hitem:777|h[Loaded now]',1,true))
        NS.ClearReplyLinks();C_Item.RequestLoadItemDataByID=nil
        NS.DisplayNativeReply('[Unavailable](item:555)');assert(body.messages[1]=='Unavailable (item #555)')
        ''')

    def test_only_current_validated_item_links_can_open_tooltips_or_click_actions(self):
        self.display('[Potion](item:118)')
        self.lua.execute(b'''
        body.scripts.OnHyperlinkEnter(body,'item:118')
        assert(tooltipCalls==1 and CodexPixelBridgeReplyTooltip:IsShown())
        body.scripts.OnHyperlinkLeave();assert(not CodexPixelBridgeReplyTooltip:IsShown())
        body.scripts.OnHyperlinkClick(body,'item:118','untrusted label','LeftButton')
        assert(clickCalls==1 and clickedData=='item:118' and clickedText:find('[Minor Healing Potion]',1,true))
        body.scripts.OnHyperlinkClick(body,'item:118','','RightButton');assert(clickCalls==1)
        for _,bad in ipairs({'item:3371','spell:118','url:https://example.com','addon:run','item:118|Hspell:1'}) do
            body.scripts.OnHyperlinkClick(body,bad,'','LeftButton');body.scripts.OnHyperlinkEnter(body,bad)
        end
        assert(clickCalls==1 and tooltipCalls==1)
        NS.Panel:Hide();body.scripts.OnHyperlinkClick(body,'item:118','','LeftButton');assert(clickCalls==1)
        NS.Panel:Show();NS.DisplayNativeReply('New response')
        body.scripts.OnHyperlinkClick(body,'item:118','','LeftButton');assert(clickCalls==1)
        ''')

    def test_shift_click_inserts_into_codex_or_focused_normal_chat_without_sending(self):
        self.display('[Vial](item:3371)')
        self.lua.execute(b'''
        modified=true;edit:SetText('Tell me more about ');edit.cursor=#edit:GetText();edit.focused=false
        body.scripts.OnHyperlinkClick(body,'item:3371','','LeftButton')
        assert(edit:HasFocus() and edit:GetText():find('|Hitem:3371|h[Empty Vial]',1,true))
        assert(clickCalls==0)
        edit.focused=false;activeChat={HasFocus=function() return true end}
        ChatFrameUtil.InsertLink=function(text) normalDraft=text end
        local before=edit:GetText();body.scripts.OnHyperlinkClick(body,'item:3371','','LeftButton')
        assert(normalDraft:find('|Hitem:3371|h[Empty Vial]',1,true) and edit:GetText()==before)
        activeChat=nil;edit:SetText(string.rep('x',1275));edit.cursor=1275
        body.scripts.OnHyperlinkClick(body,'item:3371','','LeftButton');assert(#edit:GetText()==1275)
        ''')

    def test_raw_markup_invalid_fields_and_ordinary_urls_remain_literal(self):
        raw='|Hitem:118|h[Raw]|h |Ttexture:99|t [site](https://example.com) [x](item:0) [x](item:1--2) [x](item:1:2-3) [x](item:2147483648) [x](item:118|hBAD)'
        self.assertEqual(self.display(raw),raw.replace('|','||'))
        self.lua.execute(b'assert(infoCalls==0 and #loadedRequests==0 and tooltipCalls==0 and clickCalls==0)')

    def test_mismatched_game_data_is_not_linked_and_lookups_are_bounded(self):
        self.lua.execute(b"C_Item.GetItemInfo=function() return 'Other','|Hitem:999|h[Other]|h',1 end")
        self.assertEqual(self.display('[Potion](item:118)'),'Potion (item #118)')
        self.lua.execute(b'NS.ClearReplyLinks();C_Item.GetItemInfo=function() return nil end;loadedRequests={}')
        self.display(' '.join(f'[Item {i}](item:{i})' for i in range(1,201)))
        self.assertEqual(len(self.lua.globals()[b'loadedRequests']),32)
        self.lua.execute(b'update();update();assert(#loadedRequests==32)')


if __name__=='__main__':unittest.main()
