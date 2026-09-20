from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest

from fontTools.ttLib import TTFont
from lupa.lua51 import LuaRuntime
from PIL import ImageFont

from companion.protocol import Assembler, decode_image, read_image_frame, render
from tools.compact_font_bank import prepare as prepare_compact
from tools.font_matrix import Matrix, SPECS, asset_path, font_content, parse_report, prepare

ROOT=Path(__file__).resolve().parents[1]


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.addon=self.root/'CodexPixelBridge';self.addon.mkdir()
        (self.addon/'CodexPixelBridge.toc').write_text('test')
        self.manifest=prepare(self.addon,self.root/'manifest.json')
        self.now=0;self.matrix=Matrix(self.manifest,self.root/'record.json',clock=lambda:self.now)

    def tearDown(self):self.temp.cleanup()

    def test_font_packet_survives_size_change_and_contains_no_programs(self):
        lua=LuaRuntime(encoding=None);ns=lua.table()
        for name in ('Protocol.lua','FontProbe.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CPB',ns)
        content=font_content('12345678',10,'B10 byte-perfect test')
        for size in (64,128):
            face=ImageFont.truetype(BytesIO(content),size)
            self.assertEqual(ns[b'DecodeFontProbe'](lambda c:face.getlength(c.decode()+'~')),b'B10 byte-perfect test')
        font=TTFont(BytesIO(content))
        self.assertNotIn('fpgm',font);self.assertNotIn('prep',font)
        self.assertTrue(all(not (hasattr(g,'program') and g.program.getBytecode()) for g in font['glyf'].glyphs.values()))

    def test_compact_bank_replacement_detaches_only_the_published_slot(self):
        directory=self.root/'compact'
        report=prepare_compact(directory,count=1030,group_size=512)
        self.assertEqual(report['seed_files'],3)
        self.assertEqual(report['maximum_observed_links'],513)
        first=directory/'reserve00000001.ttf';second=directory/'reserve00000002.ttf'
        self.assertTrue(os.path.samefile(first,second));baseline=second.read_bytes()
        replacement=directory/'first.next.ttf';replacement.write_bytes(font_content('12345678',1,'reply'))
        replacement.replace(first)
        self.assertFalse(os.path.samefile(first,second));self.assertEqual(second.read_bytes(),baseline)
        with self.assertRaises(ValueError):prepare_compact(directory,3)

    def test_preparation_excludes_late_fonts_and_preserves_seed_when_published(self):
        self.assertFalse(any(self.matrix.paths[i].exists() for i in (4,5,6)))
        self.assertEqual(self.matrix.paths[7].stat().st_size,0)
        self.assertTrue(os.path.samefile(self.matrix.paths[0],self.matrix.paths[8]))
        baseline=self.matrix.paths[0].read_bytes()
        self.matrix.write(8,1,0)
        self.assertFalse(os.path.samefile(self.matrix.paths[0],self.matrix.paths[8]))
        self.assertEqual(self.matrix.paths[0].read_bytes(),baseline)
        with self.assertRaises(ValueError):asset_path(self.addon,'../bad',1)
        with self.assertRaises(ValueError):Matrix(self.manifest,self.root/'record2.json')

    def run_probe(self,allow_new=False,size_reloads=False,fail_large_control=False):
        lua=LuaRuntime(encoding=None);ns=lua.table();faces={};requests=[]
        def key(path,height):return (path,height if size_reloads else 64)
        def load(path,height):
            if not path:return
            asset=int(path.decode().rsplit('_',1)[1][:2])
            if asset==15 and fail_large_control:return
            if asset in (4,5,6) and not allow_new:return
            k=key(path,height)
            if k not in faces:
                faces[k]=ImageFont.truetype(str(self.matrix.paths[asset]),height)
                requests.append((self.now,asset,height))
        def ready(path,height):return bool(path and key(path,height) in faces)
        def measure(path,height,text):return faces[key(path,height)].getlength(text.decode('ascii'))
        lua.globals()[b'loadface']=load;lua.globals()[b'ready']=ready;lua.globals()[b'measure']=measure
        lua.execute(b'''
        now=0;widgets={};watching=false;constructors={object=0,family=0}
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:SetFont(path,height,flags) self.path=path;self.height=height;self.owner=nil end
        function methods:SetFontObject(object) self.owner=object;self.path=nil;self.height=nil end
        function methods:GetFont()
            local owner=rawget(self,'owner') or self
            local path,height=rawget(owner,'path'),rawget(owner,'height')
            if path and ready(path,height) then return path,height end
        end
        function methods:SetText(text)
            self.text=text
            local owner=rawget(self,'owner') or self
            if rawget(owner,'path') then loadface(owner.path,owner.height) end
        end
        function methods:GetStringWidth()
            local owner=rawget(self,'owner') or self
            return measure(rawget(owner,'path'),rawget(owner,'height'),self.text)
        end
        methods.GetUnboundedStringWidth=methods.GetStringWidth
        function methods:Hide() if self.scripts.OnHide then self.scripts.OnHide() end end
        local function widget()
            local w={scripts={}};table.insert(widgets,w)
            return setmetatable(w,{__index=function(t,k) return methods[k] or function() end end})
        end
        function methods:CreateFontString() return widget() end
        function CreateFrame() local w=widget();w.TitleText=widget();return w end
        function CreateFont(name) constructors.object=constructors.object+1;return widget() end
        function CreateFontFamily(name,members)
            constructors.family=constructors.family+1
            assert(#members==5 and members[1].alphabet=='roman')
            local expected={'roman','korean','simplifiedchinese','traditionalchinese','russian'}
            for i,alphabet in ipairs(expected) do assert(members[i].alphabet==alphabet) end
            local f=widget();f:SetFont(members[1].file,members[1].height,members[1].flags);return f
        end
        UIParent=CreateFrame();GameFontNormal=widget()
        function GetTime() return now end
        C_UIFileAsset={IsKnownFile=function() return true end,IsLooseFile=function() return true end,GetFileID=function() return -42 end}
        ''')
        for name in ('Protocol.lua','FontProbe.lua','FontMatrixProbe.lua'):
            lua.execute((ROOT/'addon/CodexPixelBridge'/name).read_bytes(),b'CPB',ns)
        ns[b'FontMatrixToken']=self.manifest['token'].encode()
        ns[b'IsVisualWatching']=lambda:bool(lua.globals()[b'watching']);ns[b'SetStatus']=lambda _:None
        ns[b'ShowFontMatrixProbe']()
        first=None
        for index in range(1652):
            self.now=index/10;lua.globals()[b'now']=self.now
            lua.execute(b'for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate() end end')
            frame=ns[b'FontDiscoveryControl']()
            if frame:
                first=first or frame;self.matrix.accept(parse_report(frame))
        self.assertIsNone(ns[b'FontDiscoveryControl']())
        self.assertEqual(len(self.matrix.data['results']),22)
        self.assertTrue(self.matrix.done)
        for case,spec in enumerate(SPECS,1):
            result=self.matrix.data['results'][str(case)]
            self.assertEqual((result['asset'],result['phase'],result['method'],result['height'],result['flags']),spec)
        self.assertEqual(read_image_frame(render(first)),first)
        with self.assertRaises(ValueError):decode_image(render(first))
        with self.assertRaises(ValueError):Assembler().accept(first)
        damaged=bytearray(first);damaged[23]^=1
        with self.assertRaises(ValueError):parse_report(bytes(damaged))
        self.assertEqual(lua.globals()[b'constructors'][b'object'],3)
        self.assertEqual(lua.globals()[b'constructors'][b'family'],3)
        return self.matrix.data

    def test_complete_matrix_distinguishes_cached_bytes_from_new_replies(self):
        data=self.run_probe()
        summary=data['summary']
        self.assertTrue(summary['direct_control_passed'] and summary['object_control_passed'] and summary['family_control_passed'])
        self.assertTrue(summary['second_phase_control_passed'])
        self.assertTrue(summary['empty_placeholder_passed'] and summary['shared_placeholder_passed'])
        self.assertEqual(summary['new_path_candidates'],[]);self.assertEqual(summary['reuse_candidates'],[])
        self.assertTrue(all(data['results'][str(i)]['matches_old'] for i in range(14,19)))

    def test_matrix_finds_allowed_new_paths_and_isolates_size_reload_candidate(self):
        data=self.run_probe(allow_new=True,size_reloads=True)
        self.assertEqual(data['summary']['new_path_candidates'],['direct','object','family'])
        self.assertEqual([r['case'] for r in data['summary']['reuse_candidates']],[15])
        self.assertTrue(data['summary']['new_path_long_retry_passed'])

    def test_late_second_signal_and_frozen_clock_do_not_write_reuse_files(self):
        def report(elapsed):return dict(token=self.matrix.token,elapsed=elapsed,phase=2 if elapsed>=75 else 1,case=0,status=0,text='')
        self.matrix.accept(report(0));before=self.matrix.paths[9].read_bytes()
        self.now=100
        with self.assertRaises(ValueError):self.matrix.accept(report(75))
        self.assertEqual(self.matrix.paths[9].read_bytes(),before)

    def test_size_candidate_requires_its_fresh_matching_control(self):
        data=self.run_probe(size_reloads=True,fail_large_control=True)
        self.assertTrue(data['results']['15']['matches_expected'])
        self.assertFalse(data['summary']['large_size_control_passed'])
        self.assertEqual(data['summary']['reuse_candidates'],[])


if __name__=='__main__':unittest.main()
