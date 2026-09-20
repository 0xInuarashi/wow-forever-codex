from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from fontTools.ttLib import TTFont
from lupa.lua51 import LuaRuntime
from PIL import ImageFont

from companion.protocol import Assembler, decode_image, read_image_frame, render
from tools.font_discovery import Experiment, asset_path, font_content, parse_report, prepare

ROOT = Path(__file__).resolve().parents[1]


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addon = self.root/'CodexPixelBridge'; self.addon.mkdir()
        (self.addon/'CodexPixelBridge.toc').write_text('test')
        self.manifest = prepare(self.addon, self.root/'manifest.json')
        self.now = 0
        self.experiment = Experiment(self.manifest, self.root/'record.json', clock=lambda: self.now)

    def tearDown(self): self.temp.cleanup()

    def report(self, elapsed, **fields):
        return dict(token=self.manifest['token'], phase=3 if elapsed>=120 else 2 if elapsed>=70 else 1,
                    case=0, status=0, text='', elapsed=elapsed, **fields)

    def test_preparation_leaves_late_paths_absent_and_writer_is_exclusive(self):
        self.assertEqual(len(list(self.addon.glob('*.ttf'))), 1)
        self.experiment.accept(self.report(0))
        self.assertTrue(self.experiment.paths[1].exists())
        self.assertFalse(self.experiment.paths[2].exists())
        self.now=70; self.experiment.accept(self.report(70))
        self.assertTrue(self.experiment.paths[2].exists())
        with self.assertRaises(FileExistsError): self.experiment.write(3, 70)
        with self.assertRaises(ValueError): Experiment(self.manifest, self.root/'another.json')
        with self.assertRaises(ValueError): asset_path(self.addon, '../other', 1)
        with self.assertRaises(ValueError): asset_path(self.addon, self.manifest['token'], 4)
        for case in range(1,4):
            font=TTFont(BytesIO(self.experiment.paths[case-1].read_bytes()))
            self.assertNotIn('fpgm',font); self.assertNotIn('prep',font)
            for glyph in font['glyf'].glyphs.values():
                self.assertFalse(hasattr(glyph,'program') and glyph.program.getBytecode())

    def test_missed_windows_and_restarted_clock_fail_without_late_writes(self):
        with self.assertRaises(ValueError): self.experiment.accept(self.report(16))
        self.assertFalse(self.experiment.paths[1].exists())
        # A new observer is necessary after that aborted attempt.
        ex=Experiment(self.manifest,self.root/'fresh.json',clock=lambda:self.now)
        ex.accept(self.report(1))
        with self.assertRaises(ValueError): ex.accept(self.report(0))
        self.now=100
        with self.assertRaises(ValueError): ex.accept(self.report(70))
        self.assertFalse(ex.paths[2].exists())

    def run_lua(self, missing_new=False, bad_control=False):
        lua=LuaRuntime(encoding=None);ns=lua.table();faces={};tried=[]
        token=self.manifest['token']
        def assign(path,text):
            if not text: return False
            basename=path.decode().rsplit('\\',1)[-1]
            tried.append((self.now,basename))
            if missing_new and '_late' in basename: return False
            if path not in faces:
                content=(self.addon/basename).read_bytes()
                if bad_control and '_control.' in basename:
                    content=font_content(token,1,'PREPARED BASELINE')
                faces[path]=ImageFont.truetype(BytesIO(content),64)
                return False
            return True
        def measure(path,text): return faces[path].getlength(text.decode('utf-8'))
        lua.globals()[b'assign']=assign;lua.globals()[b'measure']=measure
        lua.execute(b'''
        now=0;widgets={};watching=false
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:SetText(v) self.text=v end
        function methods:SetFont(path)
            local ready=assign(path,rawget(self,'text'));if ready then self.font=path end;return ready
        end
        function methods:GetFont() return rawget(self,'font') end
        function methods:GetStringWidth() return measure(rawget(self,'font'),self.text) end
        function methods:Hide() if self.scripts.OnHide then self.scripts.OnHide() end end
        local function widget()
            local w={scripts={}};table.insert(widgets,w)
            return setmetatable(w,{__index=function(t,k) return methods[k] or function() end end})
        end
        function methods:CreateFontString() return widget() end
        function CreateFrame() local w=widget();w.TitleText=widget();return w end
        UIParent=CreateFrame()
        function GetTime() return now end
        ''')
        for name in ('Protocol.lua','NativeProtocol.lua','LateFontProbe.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CPB',ns)
        ns[b'FontDiscoveryToken']=token.encode()
        ns[b'IsVisualWatching']=lambda:bool(lua.globals()[b'watching'])
        ns[b'SetStatus']=lambda _:None
        ns[b'ShowLateFontProbe']()
        original_frame=None
        for index in range(1402):
            self.now=index/10
            lua.globals()[b'now']=self.now
            lua.execute(b'for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate() end end')
            frame=ns[b'FontDiscoveryControl']()
            if frame:
                original_frame=original_frame or frame
                self.experiment.accept(parse_report(frame))
        self.assertIsNone(ns[b'FontDiscoveryControl']())
        self.assertTrue(self.experiment.done)
        self.assertGreaterEqual(min(t for t,n in tried if '_control.' in n),30)
        self.assertGreaterEqual(min(t for t,n in tried if '_late1.' in n),50)
        self.assertGreaterEqual(min(t for t,n in tried if '_late2.' in n),100)
        self.assertEqual(read_image_frame(render(original_frame)),original_frame)
        with self.assertRaises(ValueError): decode_image(render(original_frame))
        with self.assertRaises(ValueError): Assembler().accept(original_frame)
        corrupted=bytearray(original_frame);corrupted[22]^=1
        with self.assertRaises(ValueError):parse_report(bytes(corrupted))
        # Starting the same probe again in this UI session cannot reuse its paths.
        ns[b'ShowLateFontProbe']()
        self.assertIsNone(ns[b'FontDiscoveryControl']())
        return self.experiment.data

    def test_actual_fonts_lua_measurements_and_optical_report_roundtrip(self):
        data=self.run_lua()
        self.assertIn('supported in this run',data['verdict'])
        self.assertTrue(all(r['matches_nonce'] for r in data['results'].values()))

    def test_unavailable_late_fonts_report_bounded_negative_with_positive_control(self):
        data=self.run_lua(missing_new=True)
        self.assertIn('both new font paths failed',data['verdict'])
        self.assertTrue(data['results']['1']['matches_nonce'])

    def test_failed_control_is_inconclusive_even_if_new_fonts_pass(self):
        data=self.run_lua(bad_control=True)
        self.assertIn('inconclusive',data['verdict'])

    def test_active_chat_prevents_probe_from_overriding_optical_strip(self):
        lua=LuaRuntime(encoding=None);ns=lua.table();messages=[]
        ns[b'SetStatus']=messages.append
        ns[b'IsVisualWatching']=lambda:True
        lua.execute((ROOT/'addon/CodexPixelBridge/LateFontProbe.lua').read_bytes(),b'CPB',ns)
        ns[b'ShowLateFontProbe']()
        self.assertIn(b'Finish or pause',messages[0])
        self.assertIsNone(ns[b'FontDiscoveryControl']())


if __name__=='__main__': unittest.main()
