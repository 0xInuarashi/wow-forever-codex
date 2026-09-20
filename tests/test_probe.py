from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from PIL import Image
from tools.probe_session import ASSETS, asset_image, main, make_server, validate_target, write_assets

ROOT = Path(__file__).resolve().parents[1]


class ResourceProbeTests(unittest.TestCase):
    def test_session_restores_assets_without_starting_server(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'CodexPixelBridge'
            target.mkdir()
            (target / 'CodexPixelBridge.toc').write_text('test')
            write_assets(target, asset_image(0))
            original = {p.name: p.read_bytes() for p in target.glob('*.tga')}
            with patch('sys.argv', ['probe_session', str(target), '--duration', '1']), patch('tools.probe_session.make_server') as server, patch('builtins.print'):
                main()
            server.assert_not_called()
            self.assertEqual({p.name: p.read_bytes() for p in target.glob('*.tga')}, original)

    def test_bounded_assets_and_loopback_image_only(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                validate_target(directory)
            target = Path(directory) / 'CodexPixelBridge'
            target.mkdir()
            (target / 'CodexPixelBridge.toc').write_text('test')
            write_assets(target, asset_image(42))
            self.assertEqual(sorted(p.name for p in target.glob('*.tga')), sorted(ASSETS))
            with Image.open(target / ASSETS[0]) as image:
                self.assertEqual(image.size, (64, 64))
            self.assertEqual((target / 'CodexPixelBridge.toc').read_text(), 'test')
        events = []
        server = make_server(lambda: asset_image(42), events.append, port=0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
        thread.start()
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
            base = f'http://127.0.0.1:{server.server_address[1]}'
            with urlopen(base + '/probe.png', timeout=2) as response:
                self.assertEqual(Image.open(BytesIO(response.read())).size, (64, 64))
            with self.assertRaises(HTTPError) as error:
                urlopen(base + '/anything-else', timeout=2)
            self.assertEqual(error.exception.code, 404)
            self.assertEqual(events, [{'event': 'http_request', 'path': '/probe.png'}])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_lua_probe_release_revisit_late_asset_and_stop(self):
        try:
            from lupa.lua51 import LuaRuntime
        except ImportError:
            self.skipTest('Install Lupa for Lua 5.1 checks')
        lua = LuaRuntime(encoding=None)
        lua.execute(b'''
        UIParent={}; textures={}; urlCalls=0
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:SetTexture(v) self.texture=v end
        function methods:GetTexture() return rawget(self,'texture') end
        function methods:IsObjectLoaded() return rawget(self,'texture')~=nil end
        function methods:IsShown() return self.shown end
        function methods:Hide() self.shown=false; if self.scripts.OnHide then self.scripts.OnHide() end end
        function methods:Show()
            if self.shown then return end
            self.shown=true; if self.scripts.OnShow then self.scripts.OnShow() end
        end
        function methods:SetText(v) self.text=v end
        function methods:SetPoint(...) self.point={...} end
        local function widget()
            return setmetatable({shown=true,scripts={}}, {__index=function(t,k) return methods[k] or function() end end})
        end
        function methods:CreateFontString() return widget() end
        function methods:CreateTexture() local t=widget(); table.insert(textures,t); return t end
        function CreateFrame(_,name) local f=widget(); f.TitleText=widget(); _G[name]=f; return f end
        function GetBuildInfo() return '1.60.1','69913','',16001 end
        C_Timer={NewTicker=function(_,fn)
            ticker={callback=fn,Cancel=function(self) self.cancelled=true end}; return ticker
        end}
        C_Texture={SetURLTexture=function() urlCalls=urlCalls+1; error('restricted') end}
        ''')
        ns = lua.table()
        lua.execute((ROOT / 'addon/CodexPixelBridge/Probe.lua').read_bytes(), b'CodexPixelBridge', ns)
        ns[b'ShowProbe']()
        lua.execute(b'''
        assert(CodexPixelBridgeProbe.point[1]=='TOPLEFT')
        assert(type(CodexPixelBridgeProbe.scripts.OnDragStart)=='function')
        assert(textures[2].texture:find('probe_release.tga',1,true))
        ticker.callback(); ticker.callback()
        assert(textures[2]:GetTexture()==nil)
        for i=4,12 do ticker.callback(); assert(textures[2]:GetTexture()==nil) end
        ticker.callback(); assert(textures[2].texture:find('probe_release.tga',1,true))
        ticker.callback(); ticker.callback()
        assert(textures[3].texture:find('probe_slot01.tga',1,true))
        for i=16,89 do ticker.callback() end
        assert(textures[4]:GetTexture()==nil)
        ticker.callback()
        assert(textures[4].texture:find('probe_late_v3.tga',1,true))
        for i=91,120 do ticker.callback() end
        assert(textures[3].texture:find('probe_slot08.tga',1,true))
        for i=121,135 do ticker.callback() end
        assert(textures[3].texture:find('probe_slot01.tga',1,true))
        for i=136,150 do ticker.callback() end
        assert(ticker.cancelled and urlCalls==0)
        CodexPixelBridgeProbe:Hide()
        for _,t in ipairs(textures) do assert(t:GetTexture()==nil) end
        C_Texture.SetURLTexture=function() error('restricted') end
        CodexPixelBridgeProbe:Show()
        assert(not ticker.cancelled)
        CodexPixelBridgeProbe:Hide()
        assert(ticker.cancelled)
        ''')


if __name__ == '__main__':
    unittest.main()
