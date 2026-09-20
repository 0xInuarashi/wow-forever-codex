from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from fontTools.ttLib import TTFont
from PIL import ImageFont
from tools.font_probe import font_bytes, packet, write_font

ROOT = Path(__file__).resolve().parents[1]


class FontProbeTests(unittest.TestCase):
    def test_all_byte_values_survive_real_freetype_metrics(self):
        for start in range(0, 256, 64):
            expected = bytes(range(start, start + 64))
            content = font_bytes(expected, 1)
            font = ImageFont.truetype(BytesIO(content), size=64)
            low, high = font.getlength('!~'), font.getlength('"~')
            actual = bytes(round((font.getlength(chr(35+i)+'~')-low)*255/(high-low)) for i in range(64))
            self.assertEqual(actual, expected)
            tables = TTFont(BytesIO(content))
            self.assertNotIn('fpgm', tables)
            self.assertNotIn('prep', tables)
            for glyph in tables['glyf'].glyphs.values():
                self.assertFalse(hasattr(glyph, 'program') and glyph.program.getBytecode())

    def test_lua_decodes_unicode_bytes_and_rejects_corruption(self):
        from lupa.lua51 import LuaRuntime
        lua = LuaRuntime(encoding=None)
        ns = lua.table()
        for name in ('Protocol.lua', 'FontProbe.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(), b'CodexPixelBridge', ns)
        text = 'Native text café สวัสดี 🌏'
        content = packet(text, 1234)
        def widths(data):
            font = ImageFont.truetype(BytesIO(font_bytes(data, 1)), size=64)
            return lambda c: font.getlength(c.decode('ascii')+'~')
        self.assertEqual(ns[b'DecodeFontProbe'](widths(content)), text.encode())
        broken = bytearray(content); broken[15] ^= 1
        self.assertEqual(ns[b'DecodeFontProbe'](widths(broken)), (None, b'Checksum mismatch'))
        self.assertEqual(ns[b'DecodeFontProbe'](lambda _: 1), (None, b'Invalid calibration'))

    def test_font_writes_are_bounded_and_preparation_preserves_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            addon = Path(directory)/'CodexPixelBridge'; addon.mkdir()
            (addon/'CodexPixelBridge.toc').write_text('probe')
            with self.assertRaises(ValueError): write_font(addon, 2, packet('test'))
            write_font(addon, 2, packet('baseline'), prepare=True)
            path = addon/'fontprobe02.ttf'
            baseline = path.read_bytes()
            write_font(addon, 2, packet('replacement'), prepare=True)
            self.assertEqual(path.read_bytes(), baseline)
            write_font(addon, 2, packet('live', 1))
            self.assertNotEqual(path.read_bytes(), baseline)
            with self.assertRaises(ValueError): write_font(addon, 9, packet('test'), prepare=True)
            self.assertEqual(sorted(p.name for p in addon.iterdir()), ['CodexPixelBridge.toc', 'fontprobe02.ttf'])

    def test_probe_waits_for_font_assignment_and_stops_timer(self):
        from lupa.lua51 import LuaRuntime
        lua = LuaRuntime(encoding=None)
        ns = lua.table()
        lua.execute(b'''
        UIParent={}; widgets={}; attempts={}
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:SetText(v) self.text=v end
        function methods:SetFont(path)
            attempts[path]=(attempts[path] or 0)+1
            if attempts[path]==1 then return false end
            self.font=path; return true
        end
        function methods:GetStringWidth() return measure(self.font,self.text) end
        local function widget()
            local w={scripts={}}; table.insert(widgets,w)
            return setmetatable(w,{__index=function(t,k) return methods[k] or function() end end})
        end
        function methods:CreateFontString() return widget() end
        function CreateFrame() local w=widget(); w.TitleText=widget(); return w end
        C_Timer={NewTicker=function(interval,callback)
            ticker={callback=callback,Cancel=function(self) self.cancelled=true end};return ticker
        end}
        ''')
        fonts = {slot: ImageFont.truetype(BytesIO(font_bytes(packet(f'slot {slot}'),slot)),64) for slot in range(5,9)}
        def measure(path, text):
            if not path: return 0
            slot = int(path.decode().split('fontprobe')[1][:2])
            return fonts[slot].getlength(text.decode())
        lua.globals()[b'measure'] = measure
        for name in ('Protocol.lua', 'FontProbe.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CodexPixelBridge',ns)
        ns[b'ShowFontProbe']()
        for _ in range(145): lua.execute(b'ticker.callback()')
        widgets = lua.globals()[b'widgets']
        texts = [widgets[i][b'text'] for i in range(1,len(widgets)+1)]
        text = next(value for value in texts if isinstance(value,bytes) and value.startswith(b'Tick'))
        for slot in range(5,9): self.assertIn(f'VALID slot {slot}'.encode(),text)
        self.assertNotIn(b'FAIL',text)
        self.assertTrue(lua.globals()[b'ticker'][b'cancelled'])
        ns[b'ShowFontProbe']()
        lua.execute(b"for _,w in ipairs(widgets) do if w.scripts.OnHide then w.scripts.OnHide() end end")
        self.assertTrue(lua.globals()[b'ticker'][b'cancelled'])


if __name__ == '__main__':
    unittest.main()
