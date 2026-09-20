from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from PIL import ImageFont
from lupa.lua51 import LuaRuntime
from companion.native import BANK_SIZE, CHUNK, NativeBridge, font_path, make_font, make_packet
from companion.visual import encode_control, parse_control
from companion.protocol import Assembler, decode_image, render
from companion.app import App

ROOT=Path(__file__).resolve().parents[1]


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addon=Path(self.temp.name)/'CodexPixelBridge';self.addon.mkdir()
        (self.addon/'CodexPixelBridge.toc').write_text('test')
        for i in [*range(1,20),BANK_SIZE]: font_path(self.addon,i).write_bytes(make_font(bytes(512),i))
        self.now=100.;self.bridge=NativeBridge(self.addon,clock=lambda:self.now)

    def tearDown(self): self.temp.cleanup()

    def control(self,**kwargs): return parse_control(encode_control(kind='font',**kwargs))

    def test_font_packet_uses_all_byte_values_and_control_cannot_submit(self):
        data=bytes(range(256))*2
        face=ImageFont.truetype(BytesIO(make_font(data,1)),64)
        self.assertGreater(face.getlength('AMaz'),0)
        low,high=face.getlength('!~'),face.getlength('"~')
        decoded=bytes(round((face.getlength(chr(0xE000+i)+'~')-low)*255/(high-low)) for i in range(512))
        self.assertEqual(decoded,data)
        control=encode_control(kind='font')
        self.assertEqual(decode_image(render(control)),control)
        with self.assertRaises(ValueError): Assembler().accept(control)
        with self.assertRaises(ValueError): self.control(slot=BANK_SIZE+1)

    def test_font_capacity_and_inactive_exhaustion_do_not_expand_image_bank(self):
        for slot in (1025,4097,9999,10000,BANK_SIZE):
            self.assertEqual(self.control(slot=slot).slot,slot)
        exhausted=self.control(slot=BANK_SIZE+1,active=False)
        self.assertEqual(exhausted.loaded,BANK_SIZE)
        self.assertFalse(self.bridge.accept(exhausted,{}))
        for slot in (BANK_SIZE+1,BANK_SIZE+2):
            with self.assertRaises(ValueError): self.control(slot=slot)
            with self.assertRaises(ValueError): font_path(self.addon,slot)
            with self.assertRaises(ValueError): make_font(bytes(512),slot)
        with self.assertRaises(ValueError): self.control(slot=BANK_SIZE+2,active=False)
        self.assertEqual(parse_control(encode_control(slot=4096)).slot,4096)
        self.assertFalse(parse_control(encode_control(slot=4097,active=False)).active)
        with self.assertRaises(ValueError): encode_control(slot=4097)
        with self.assertRaises(ValueError): encode_control(slot=4098,active=False)

    def test_writer_freezes_slot_and_rejects_late_missing_or_wrong_channel(self):
        snapshot={'id':'3132333435363738:1','state':'done','reply':'first'}
        self.assertTrue(self.bridge.accept(self.control(),snapshot))
        before=font_path(self.addon,1).read_bytes()
        self.assertFalse(self.bridge.accept(self.control(),dict(snapshot,reply='later')))
        self.assertEqual(before,font_path(self.addon,1).read_bytes())
        self.now+=6
        self.assertFalse(self.bridge.accept(self.control(),snapshot))
        self.assertTrue(self.bridge.accept(self.control(slot=2),snapshot))
        with self.assertRaises(ValueError): self.bridge.accept(self.control(slot=20),snapshot)
        with self.assertRaises(ValueError): self.bridge.accept(parse_control(encode_control()),snapshot)

    def test_native_parser_rejects_other_request_session_slot_and_corruption(self):
        lua=LuaRuntime(encoding=None);ns=lua.table()
        for name in ('Protocol.lua','NativeProtocol.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CPB',ns)
        frame=make_packet(self.control(),{'id':'3132333435363738:1','state':'done','reply':'café'})
        parse=ns[b'ParseNativePacket']
        self.assertEqual(parse(bytes(512),b'12345678',1,1),(None,b'Empty reply slot'))
        self.assertEqual(parse(frame,b'12345678',1,1)[b'text'],'café'.encode())
        for session,request,slot in [(b'87654321',1,1),(b'12345678',2,1),(b'12345678',1,2)]:
            self.assertIsNone(parse(frame,session,request,slot)[0])
        broken=bytearray(frame);broken[35]^=1
        self.assertIsNone(parse(bytes(broken),b'12345678',1,1)[0])

    def test_two_actual_font_replies_render_native_text_then_stop_strip(self, _cached_prefix=0, _miss_slots=(), _item_links=False, _start_slot=4):
        lua=LuaRuntime(encoding=None);ns=lua.table();faces={};calls={}
        if _start_slot!=4:
            for i in range(_start_slot,min(BANK_SIZE+1,_start_slot+20)):
                font_path(self.addon,i).write_bytes(make_font(bytes(512),i))
        for old_slot in range(1,_cached_prefix+1):
            old_control=self.control(session=b'oldcache',slot=old_slot)
            old_packet=make_packet(old_control,{'id':old_control.session+':1','state':'done','reply':'old reply'})
            old_path=('Interface\\AddOns\\CodexPixelBridge\\fontreply%04d.ttf'%old_slot).encode()
            faces[old_path]=ImageFont.truetype(BytesIO(make_font(old_packet,old_slot)),64)
        def assign(path,text):
            calls[path]=calls.get(path,0)+1
            # The working live probe sets/measures text even during assignment.
            # Model a lazy loader that cannot resolve an empty FontString yet.
            if not text: return False
            if path not in faces:
                slot=int(path.decode().rsplit('fontreply',1)[1].removesuffix('.ttf'))
                faces[path]=ImageFont.truetype(str(font_path(self.addon,slot)),64)
                return False  # Actual client required a retry on first assignment.
            return True
        def measure(path,text): return faces[path].getlength(text.decode('utf-8'))
        lua.globals()[b'assign']=assign;lua.globals()[b'measure']=measure
        lua.execute(b'''
        now=100; widgets={};SlashCmdList={}
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:HookScript(k,v) self.scripts[k]=v end
        function methods:SetText(v) self.text=v end
        function methods:GetText() return self.text or '' end
        function methods:SetFont(path) local ready=assign(path,rawget(self,'text'));if ready then self.font=path end;return ready end
        function methods:GetFont() return rawget(self,'font'),64 end
        function methods:GetStringWidth() return measure(self.font,self.text) end
        function methods:GetEffectiveScale() return 1 end
        function methods:SetColorTexture(r) self.r=r end
        function methods:IsShown() return self.shown~=false end
        function methods:SetShown(v) self.shown=v end
        function methods:Hide() self.shown=false end
        function methods:Show() self.shown=true end
        function methods:Clear() self.messages={} end
        function methods:AddMessage(v) table.insert(self.messages,v) end
        local function widget(kind)
            local w={kind=kind,scripts={},messages={}}
            setmetatable(w,{__index=function(t,k) return methods[k] or function() end end})
            table.insert(widgets,w);return w
        end
        function methods:CreateTexture() return widget('texture') end
        function methods:CreateFontString() return widget('font') end
        function CreateFrame(kind,name) local w=widget(kind);w.TitleText=widget('font');if name then _G[name]=w end;return w end
        UIParent=CreateFrame('Frame')
        function GetTime() return now end
        function GetServerTime() return 123456789 end
        ''')
        for name in ('Protocol.lua','NativeProtocol.lua','Main.lua','Native.lua','ReplyLinks.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CPB',ns)
        # Match WoW: restored SavedVariables become available after file execution.
        lua.globals()[b'savedSlot']=1 if _cached_prefix else 3
        lua.execute(b"CodexPixelBridgeState={nextFontSlotV2=savedSlot};for _,w in ipairs(widgets) do if w.scripts.OnEvent then w.scripts.OnEvent(w,'ADDON_LOADED','CPB') end end")
        def submit(text):
            lua.globals()[b'prompt']=text.encode()
            lua.execute(b"for _,w in ipairs(widgets) do if w.kind=='EditBox' then w:SetText(prompt);w.scripts.OnEnterPressed() end end")
        def run_reply(sequence,text):
            for _ in range(2000):
                # Main owns the real random-session bytes; read the emitted control.
                lua.execute(b"now=now+0.1;for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0.1) end end")
                self.now=lua.globals()[b'now']
                # Reuse the exact session created by Main (seconds + uptime ms).
                frame=ns[b'VisualControl'](bytes.fromhex('075bcd15000186a0'))
                c=parse_control(frame)
                if c.slot not in _miss_slots:
                    self.bridge.accept(c,{'id':c.session+':'+str(sequence),'state':'done','reply':text})
                if not c.active: break
            self.assertFalse(c.active)
            self.assertEqual(ns[b'LastNativeReply'],text.encode())
            return c
        # Reconcile a later beta settings restore at first user submission.
        if not _cached_prefix:
            lua.globals()[b'newStartSlot']=_start_slot
            lua.execute(b'CodexPixelBridgeState.nextFontSlotV2=newStartSlot')
        submit('first')
        first=run_reply(1,'First reply as normal text.')
        self.assertEqual(first.loaded,_cached_prefix+2 if _cached_prefix else _start_slot)
        if _start_slot==BANK_SIZE:
            self.assertEqual(first.slot,BANK_SIZE+1)
            self.assertEqual(lua.globals()[b'CodexPixelBridgeState'][b'nextFontSlotV2'],BANK_SIZE+1)
            loaded_paths=set(calls)
            submit('bank exhausted')
            for _ in range(100):
                lua.execute(b"now=now+0.1;for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0.1) end end")
            exhausted=parse_control(ns[b'VisualControl'](bytes.fromhex('075bcd15000186a0')))
            self.assertFalse(exhausted.active)
            self.assertEqual(exhausted.slot,BANK_SIZE+1)
            self.assertEqual(set(calls),loaded_paths)
            return
        submit('second')
        second_text='Second café 🌏 reply with | markup. '*40
        if _item_links:
            lua.execute(b"C_Item={GetItemInfo=function(data) return 'Empty Vial','|H'..data..'|h[Empty Vial]|h',1 end}")
            # The item reference deliberately straddles a 476-byte boundary.
            second_text='x'*470+'[Vial](item:3371)\n'+second_text
        second=run_reply(2,second_text)
        self.assertGreater(second.loaded,first.loaded)
        body=ns[b'NativeBody'][b'messages']
        self.assertIn(b'|| markup',body[1])
        if _item_links: self.assertIn(b'|Hitem:3371|h[Empty Vial]|h',body[1])
        self.assertEqual(lua.globals()[b'CodexPixelBridgeState'][b'nextFontSlotV2'],second.slot)
        self.assertTrue(any(n>=2 for n in calls.values()))
        lua.globals()[b'NS']=ns
        lua.execute(b"NS.ParseNativePacket=function() return nil,'Test checksum error' end")
        submit('third')
        for _ in range(800):
            lua.execute(b"now=now+0.1;for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0.1) end end")
            self.now=lua.globals()[b'now']
            c=parse_control(ns[b'VisualControl'](bytes.fromhex('075bcd15000186a0')))
            self.bridge.accept(c,{'id':c.session+':3','state':'done','reply':'third reply'})
            if not c.active: break
        self.assertFalse(c.active)
        self.assertEqual(c.loaded-second.loaded,3)
        messages=ns[b'NativeBody'][b'messages']
        self.assertIn(b'companion',messages[len(messages)])

    def test_cached_pre_reload_slots_recover_before_two_new_replies(self):
        self.test_two_actual_font_replies_render_native_text_then_stop_strip(_cached_prefix=3)

    def test_actual_fonts_cross_from_four_to_five_digit_paths(self):
        self.test_two_actual_font_replies_render_native_text_then_stop_strip(_start_slot=9999)

    def test_actual_last_font_delivers_reply_and_stops_at_exhaustion(self):
        self.test_two_actual_font_replies_render_native_text_then_stop_strip(_start_slot=BANK_SIZE)

    def test_three_missed_writes_keep_first_fragment_then_finish_without_manual_resume(self):
        self.test_two_actual_font_replies_render_native_text_then_stop_strip(_miss_slots=(6,7,8))

    def test_returned_item_link_crosses_font_packets_then_renders_as_a_native_link(self):
        self.test_two_actual_font_replies_render_native_text_then_stop_strip(_item_links=True)

    def test_transient_file_error_retries_same_packet_without_disabling_return(self):
        app=App.__new__(App);app.native=self.bridge;app.visual=None;app.return_retry_at=0
        app.record_transport=Mock();app.write=Mock()
        control=self.control();snapshot={'id':control.session+':1','state':'done','reply':'hello'}
        with patch('companion.app.time.monotonic',side_effect=lambda:self.now):
            with patch.object(Path,'replace',side_effect=PermissionError('temporarily busy')):
                app.publish_reply(control,snapshot)
            self.assertIs(app.native,self.bridge)
            self.assertEqual(app.record_transport.call_args.args[0],'write_retry')
            self.now+=1.1
            app.publish_reply(control,dict(snapshot,reply='changed'))
        self.assertEqual(app.record_transport.call_args.args[0],'written')
        face=ImageFont.truetype(str(font_path(self.addon,1)),64)
        low,high=face.getlength('!~'),face.getlength('"~')
        packet=bytes(round((face.getlength(chr(0xE000+i)+'~')-low)*255/(high-low)) for i in range(512))
        self.assertEqual(packet,make_packet(control,snapshot))
        self.assertFalse(app.write.called)


if __name__=='__main__': unittest.main()
