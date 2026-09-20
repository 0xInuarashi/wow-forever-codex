from pathlib import Path
import unittest
from tests import test_bridge
from companion.protocol import Assembler

ROOT=Path(__file__).resolve().parents[1]
LINK='|cff1eff00|Hitem:12345:17:0:0:0:0:-6:42:7:0|h[Café Blade]|h|r'


class ItemLinkTests(unittest.TestCase):
    def setUp(self):
        fixture=test_bridge.LuaTests();fixture.setUp();fixture.test_addon_load_and_submit_with_ui_stubs()
        self.lua,self.ns=fixture.lua,fixture.ns
        self.lua.globals()[b'NS']=self.ns
        self.lua.execute(br'''
        edit=NS.PromptEditBox;edit.focused=true;edit.cursor=0
        function edit:HasFocus() return self.focused end
        function edit:SetFocus() self.focused=true end
        function edit:Insert(text)
            local old=self:GetText();local cursor=self.cursor or #old
            self:SetText(old:sub(1,cursor)..text..old:sub(cursor+1))
            self.cursor=cursor+#text
        end
        originalCalls=0;hookCount=0
        ChatFrameUtil={InsertLink=function() originalCalls=originalCalls+1;return false end}
        function hooksecurefunc(target,key,callback)
            if type(target)=='string' then callback=key;key=target;target=_G end
            local original=target[key];hookCount=hookCount+1
            target[key]=function(...) local result=original(...);callback(...);return result end
        end
        C_Item={GetItemInfo=function() return 'Caf\195\169 Blade',nil,2,12,7,'Weapon','Sword' end}
        function GetCursorInfo() return cursorKind,cursorID,cursorLink end
        function ClearCursor() cleared=true end
        function IsModifiedClick() return true end
        ''')
        self.lua.globals()[b'link']=LINK.encode()

    def load(self):
        self.lua.execute((ROOT/'addon/CodexPixelBridge/ItemLinks.lua').read_bytes(),b'CodexPixelBridge',self.ns)

    def test_secure_posthook_preserves_original_return_and_inserts_at_cursor_only_when_focused(self):
        self.load()
        self.lua.execute(b'''
        edit:SetText('Is  useful?');edit.cursor=3
        assert(ChatFrameUtil.InsertLink(link)==false)
        assert(originalCalls==1 and hookCount==1)
        assert(edit:GetText()=='Is '..link..'  useful?')
        local before=edit:GetText()
        edit.focused=false;ChatFrameUtil.InsertLink(link);assert(edit:GetText()==before)
        edit.focused=true;NS.Panel:Hide();ChatFrameUtil.InsertLink(link);assert(edit:GetText()==before)
        NS.Panel:Show();ChatFrameUtil.InsertLink('|Hspell:123|h[Spell]|h');assert(edit:GetText()==before)
        ChatFrameUtil.InsertLink(nil);assert(edit:GetText()==before)
        edit:SetText(string.rep('x',1275));ChatFrameUtil.InsertLink(link);assert(#edit:GetText()==1275)
        ''')

    def test_legacy_hook_and_user_drag_use_same_bounded_insertion(self):
        self.lua.execute(b'ChatEdit_InsertLink=ChatFrameUtil.InsertLink;ChatFrameUtil=nil')
        self.load()
        self.lua.execute(b'''
        edit:SetText('');edit.cursor=0;ChatEdit_InsertLink(link)
        assert(edit:GetText()==link..' ' and hookCount==1)
        edit:SetText('');edit.cursor=0;edit.focused=false
        cursorKind='item';cursorID=12345;cursorLink=link
        edit.scripts.OnReceiveDrag();assert(cleared and edit:GetText()==link..' ')
        cleared=false;cursorKind='spell';edit.scripts.OnReceiveDrag();assert(not cleared)
        cursorKind='item';edit:SetText(string.rep('x',1275));edit.scripts.OnReceiveDrag();assert(not cleared)
        ''')

    def test_linked_bag_stack_is_dismissed_but_normal_splits_and_chat_still_work(self):
        self.lua.execute(b'''
        bagLink=link;modified=true;normalChat=false
        ChatFrameUtil.InsertLink=function(text)
            originalCalls=originalCalls+1
            if normalChat then normalText=text;return true end
            return false
        end
        function IsModifiedClick() return modified end
        C_Container={GetContainerItemLink=function() return bagLink end}
        bag={GetBagID=function() return 0 end,GetID=function() return 1 end}
        StackSplitFrame={}
        function StackSplitFrame:IsProtected() return self.protected end
        function StackSplitFrame:Hide() self.shown=false;self.owner.hasStackSplit=0 end
        function StackSplitFrame:OpenStackSplitFrame(count,parent)
            self.owner=parent;parent.hasStackSplit=1;self.shown=true
        end
        -- Blizzard's bag route: try chat insertion, then open the split dialog
        -- when the original insertion function returns false for a stacked item.
        function bagClick()
            if ChatFrameUtil.InsertLink(bagLink) then return end
            StackSplitFrame:OpenStackSplitFrame(20,bag)
        end
        function nextFrame()
            for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0) end end
        end
        ''')
        self.load()
        self.lua.execute(b'''
        edit:SetText('');edit.cursor=0;bagClick()
        assert(edit:GetText()==link..' ' and not StackSplitFrame.shown and bag.hasStackSplit==0)
        -- The marker is consumed, so another split is not suppressed.
        StackSplitFrame:OpenStackSplitFrame(20,bag);assert(StackSplitFrame.shown)
        nextFrame();edit.focused=false;bagClick();assert(StackSplitFrame.shown)
        edit.focused=true;NS.Panel:Hide();bagClick();assert(StackSplitFrame.shown)
        NS.Panel:Show();edit:SetText(string.rep('x',1275));bagClick();assert(StackSplitFrame.shown)
        edit:SetText('');edit.cursor=0;ChatFrameUtil.InsertLink(link)
        nextFrame();StackSplitFrame:OpenStackSplitFrame(20,bag);assert(StackSplitFrame.shown)
        ChatFrameUtil.InsertLink(link);bagLink='|Hitem:99|h[Other item]|h'
        StackSplitFrame:OpenStackSplitFrame(20,bag);assert(StackSplitFrame.shown)
        bagLink=link;StackSplitFrame.protected=true;bagClick();assert(StackSplitFrame.shown)
        StackSplitFrame.protected=false;StackSplitFrame:Hide()
        edit.focused=false;normalChat=true;bagClick()
        assert(normalText==link and not StackSplitFrame.shown)
        ''')

    def test_link_identity_and_cached_details_survive_actual_lua_optical_submission(self):
        self.load()
        raw='Is '+LINK+' useful?'
        expected=self.ns[b'MakePromptText'](raw.encode())
        self.assertIn('[Café Blade]'.encode(),expected)
        self.assertIn(b'WoW Forever item ID 12345',expected)
        self.assertIn(b'link=item:12345:17:0:0:0:0:-6:42:7:0',expected)
        self.assertIn(b'Weapon / Sword; item level 12; requires level 7',expected)
        self.assertNotIn(b'|H',expected)
        self.lua.globals()[b'raw']=raw.encode()
        self.lua.execute(b'edit:SetText(raw);edit.scripts.OnEnterPressed()')
        assembler=Assembler();received=[]
        for _ in range(36):
            self.lua.execute(b'''
            for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0.3) end end
            bits={};for _,w in ipairs(widgets) do if w.kind=='Texture' then table.insert(bits,w.r) end end
            ''')
            bits=self.lua.globals()[b'bits']
            frame=bytes(sum(int(bits[i+j+1])<<(7-j) for j in range(8)) for i in range(0,512,8))
            result=assembler.accept(frame)
            if result:received.append(result[1])
        self.assertIn(expected.decode(),received)
        self.lua.execute(b'C_Item.GetItemInfo=function() return nil end')
        fallback=self.ns[b'MakePromptText'](raw.encode())
        self.assertIn('[Café Blade]'.encode(),fallback)
        self.assertIn(b'item ID 12345',fallback)
        self.assertNotIn(b'item level',fallback)
        named_color=b'|cnIQ1:'+LINK.encode().split(b'|H',1)[1]
        named_color=named_color.replace(b'|cnIQ1:',b'|cnIQ1:|H',1)
        named=self.ns[b'MakePromptText'](named_color)
        self.assertNotIn(b'|cn',named)
        self.assertIn(b'item ID 12345',named)

    def test_expanded_details_over_limit_keep_draft_instead_of_sending_truncated_prompt(self):
        self.load()
        self.lua.execute(b'''
        C_Item.GetItemInfo=function() return string.rep('n',250),nil,2,12,7,'Weapon','Sword' end
        local raw=string.rep('q',1000)..link
        assert(#raw<1280 and #NS.MakePromptText(raw)>1280)
        edit:SetText(raw);edit.scripts.OnEnterPressed();assert(edit:GetText()==raw)
        ''')
