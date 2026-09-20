import argparse
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from companion.protocol import encode, parse, render, decode_image, Assembler
from companion.app import Inbox, run_agent

ROOT=Path(__file__).resolve().parents[1]

class ProtocolTests(unittest.TestCase):
    def test_mock_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            inbox=Inbox(Path(d)/'jobs.db'); assembler=Assembler(); accepted=0
            for frame in encode('Review my work repository')*3:
                result=assembler.accept(decode_image(render(frame)))
                if result and inbox.add(*result):
                    key,prompt=result; accepted+=1
                    state,reply=run_agent(argparse.Namespace(backend='mock'),prompt)
                    inbox.update(key,state,reply)
            self.assertEqual(accepted,1)
            self.assertEqual(inbox.db.execute('SELECT state FROM jobs').fetchone()[0],'done')
            inbox.db.close()

    def test_unicode_out_of_order_and_duplicate_fragments(self):
        text='Hello สวัสดี 🌏 '*35
        frames=encode(text)
        random.Random(4).shuffle(frames)
        a=Assembler(); result=None
        for frame in [frames[0]]+frames:
            result=a.accept(decode_image(render(frame,3))) or result
        self.assertEqual(result[1],text)

    def test_corrupt_and_obscured(self):
        frame=bytearray(encode('hello')[0]); frame[25]^=1
        with self.assertRaises(ValueError): parse(frame)
        im=render(encode('hello')[0]); im.paste((128,128,128),(0,0,4,4))
        with self.assertRaises(ValueError): decode_image(im)

    def test_boundaries(self):
        for text in ['', 'x'*1281]:
            with self.assertRaises(ValueError): encode(text)
        frames=encode('x'*1280)
        self.assertEqual(len(frames),32)
        a=Assembler()
        for frame in frames: result=a.accept(frame)
        self.assertEqual(result[1],'x'*1280)

    def test_conflicting_fragment(self):
        a=Assembler(); a.accept(encode('a'*80)[0])
        with self.assertRaises(ValueError): a.accept(encode('b'*80)[0])

    def test_persistent_dedup_and_no_crash_replay(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'inbox.db'; inbox=Inbox(p)
            self.assertTrue(inbox.add('abc:1','hi'))
            self.assertFalse(inbox.add('abc:1','hi'))
            inbox.db.close(); inbox=Inbox(p)
            self.assertFalse(inbox.add('abc:1','hi'))
            self.assertEqual(inbox.db.execute('SELECT state FROM jobs').fetchone()[0],'interrupted')
            inbox.db.close()

    def test_codex_adapter_stdin_and_json(self):
        args=argparse.Namespace(backend='codex',codex='codex',sandbox='read-only',project=ROOT,timeout=10)
        output='{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}\n{"type":"turn.completed"}\n'
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')) as call:
            self.assertEqual(run_agent(args,'$(do not run); --flag'),('done','hello'))
            self.assertFalse(call.call_args.kwargs['shell'])
            self.assertEqual(call.call_args.kwargs['input'],'$(do not run); --flag')
            self.assertNotIn('$(do not run); --flag',call.call_args.args[0])
        with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('codex',10)):
            self.assertEqual(run_agent(args,'hi')[0],'failed')
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'{"type":"error","message":"blocked"}','')):
            self.assertEqual(run_agent(args,'hi'),('failed','blocked'))

    def test_actual_local_process_adapter(self):
        import sys
        args=argparse.Namespace(backend='codex',codex=sys.executable,sandbox='read-only',project=ROOT,timeout=10)
        real_run=subprocess.run
        script="import sys,json; sys.stdin.reconfigure(encoding='utf-8'); p=sys.stdin.read(); print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':p}})); print(json.dumps({'type':'turn.completed'}))"
        def fixture(command,**kwargs): return real_run([sys.executable,'-c',script],**kwargs)
        with patch('subprocess.run',side_effect=fixture):
            self.assertEqual(run_agent(args,'test café'),('done','test café'))

class LuaTests(unittest.TestCase):
    def setUp(self):
        try:
            from lupa.lua51 import LuaRuntime
        except ImportError:
            self.skipTest('Install requirements-dev.txt for Lua 5.1 checks')
        self.lua=LuaRuntime(encoding=None)
        self.ns=self.lua.table()
        self.lua.execute((ROOT/'addon/CodexPixelBridge/Protocol.lua').read_bytes(),b'CodexPixelBridge',self.ns)

    def test_lua_python_wire_compatibility(self):
        for text in ['hello','สวัสดี 🌏'*40,'x'*1280]:
            frames=self.ns[b'Encode'](text.encode(),b'12345678',37)
            self.assertEqual([frames[i] for i in range(1,len(frames)+1)],encode(text,message=37))

    def test_addon_load_and_submit_with_ui_stubs(self):
        self.lua.execute(b'''
        widgets={}; SlashCmdList={}; UIParent={GetEffectiveScale=function() return 1 end}
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:SetText(v) self.text=v end
        function methods:GetText() return self.text or '' end
        function methods:SetColorTexture(r,g,b,a) self.r=r end
        function methods:GetEffectiveScale() return 1 end
        function methods:IsShown() return self.shown~=false end
        function methods:SetShown(v) self.shown=v end
        function methods:Hide() self.shown=false end
        function methods:Show() self.shown=true end
        local function widget(kind)
          local w={kind=kind,scripts={}}
          setmetatable(w,{__index=function(t,k) return methods[k] or function() end end})
          table.insert(widgets,w); return w
        end
        function methods:CreateTexture() return widget('Texture') end
        function methods:CreateFontString() return widget('FontString') end
        function CreateFrame(kind,name) local w=widget(kind); w.TitleText=widget('FontString'); if name then _G[name]=w end; return w end
        function GetServerTime() return 123456789 end
        function GetTime() return 123.5 end
        C_Timer={NewTicker=function() return {} end}
        ''')
        for name in ['Main.lua','Probe.lua']:
            self.lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CodexPixelBridge',self.ns)
        self.lua.execute(b'''
        for _,w in ipairs(widgets) do if w.kind=='EditBox' then w:SetText('hello from Lua'); w.scripts.OnEnterPressed() end end
        for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0.3) end end
        bits={}; for _,w in ipairs(widgets) do if w.kind=='Texture' then table.insert(bits,w.r) end end
        ''')
        bits=self.lua.globals()[b'bits']
        frame=bytes(sum(int(bits[i+j+1]) << (7-j) for j in range(8)) for i in range(0,512,8))
        self.assertEqual(Assembler().accept(frame)[1],'hello from Lua')
        self.lua.execute(b'''
        SlashCmdList.CODEXPIXELBRIDGE('hide')
        assert(not CodexPixelBridgePanel:IsShown())
        CodexPixelBridgeToggle()
        assert(CodexPixelBridgePanel:IsShown())
        CodexPixelBridgeMinimapButton.scripts.OnClick()
        assert(not CodexPixelBridgePanel:IsShown())
        SlashCmdList.CODEXPIXELBRIDGE('show')
        assert(CodexPixelBridgePanel:IsShown())
        assert(SLASH_CODEXPIXELBRIDGE2=='/codex')
        ''')

    def test_pause_timeout_and_send_control_actual_optical_strip(self):
        from companion.visual import parse_control
        self.test_addon_load_and_submit_with_ui_stubs()
        self.lua.execute(b'now=200; function GetTime() return now end')
        self.lua.execute((ROOT/'addon/CodexPixelBridge/Visual.lua').read_bytes(), b'CodexPixelBridge', self.ns)
        self.ns[b'OnPromptSubmitted'](1)
        def pulse():
            self.lua.execute(b'''
            now=now+0.3
            for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate(w,0.3) end end
            bits={}; for _,w in ipairs(widgets) do if w.kind=='Texture' and #bits<512 then table.insert(bits,w.r) end end
            ''')
            bits = self.lua.globals()[b'bits']
            return bytes(sum(int(bits[i+j+1]) << (7-j) for j in range(8)) for i in range(0,512,8))
        self.assertEqual({pulse()[:4], pulse()[:4]}, {b'CPBC', b'CPB1'})
        self.lua.execute(b"SlashCmdList.CODEXPIXELBRIDGE('pause')")
        paused = pulse()
        self.assertFalse(parse_control(paused).active)
        self.lua.execute(b'now=now+60')
        self.assertEqual(paused, pulse())
        self.lua.execute(b"SlashCmdList.CODEXPIXELBRIDGE('resume')")
        resumed = [pulse(), pulse()]
        self.assertTrue(parse_control(next(f for f in resumed if f[:4]==b'CPBC')).active)
        self.lua.execute(b'now=now+631')
        pulse()  # The watch timer transitions to idle.
        idle = pulse()
        self.assertFalse(parse_control(idle).active)
        self.assertEqual(idle, pulse())
        self.lua.execute(b'''
        for _,w in ipairs(widgets) do if w.kind=='EditBox' then w:SetText('second prompt'); w.scripts.OnEnterPressed() end end
        ''')
        frames = [pulse() for _ in range(8)]
        control = parse_control(next(f for f in frames if f[:4]==b'CPBC'))
        self.assertTrue(control.active)
        self.assertEqual(control.request, 2)
        assembler = Assembler()
        prompts = [assembler.accept(f) for f in frames if f[:4]==b'CPB1']
        self.assertIn('second prompt', [p[1] for p in prompts if p])
        self.lua.execute(b"SlashCmdList.CODEXPIXELBRIDGE('clear')")
        cleared = pulse()
        self.assertFalse(parse_control(cleared).active)
        self.assertEqual(cleared, pulse())

if __name__=='__main__': unittest.main()
