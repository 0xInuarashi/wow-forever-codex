import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.native import BANK_SIZE, NativeBridge, font_path, prepare_bank
from companion.visual import encode_control, parse_control


class FontBankTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addon=Path(self.temp.name)/'CodexPixelBridge';self.addon.mkdir()
        (self.addon/'CodexPixelBridge.toc').write_text('test')

    def tearDown(self): self.temp.cleanup()

    def test_compact_bank_preserves_slots_and_publication_detaches_only_one(self):
        font_path(self.addon,1).write_bytes(b'preserve existing response')
        result=prepare_bank(self.addon,count=1025)
        self.assertEqual((result['created'],result['preserved'],result['shared_groups_created']),(1024,1,2))
        self.assertEqual(font_path(self.addon,1).read_bytes(),b'preserve existing response')
        a,b,c=(font_path(self.addon,i) for i in (2,513,514))
        self.assertEqual(a.stat().st_ino,b.stat().st_ino)
        self.assertNotEqual(a.stat().st_ino,c.stat().st_ino)
        self.assertEqual(a.stat().st_nlink,512)
        baseline=b.read_bytes();font_path(self.addon,BANK_SIZE).write_bytes(baseline)
        bridge=NativeBridge(self.addon,clock=lambda:100.)
        control=parse_control(encode_control(kind='font',slot=2))
        self.assertTrue(bridge.accept(control,{'id':control.session+':1','state':'done','reply':'isolated reply'}))
        self.assertNotEqual(a.stat().st_ino,b.stat().st_ino)
        self.assertEqual(b.read_bytes(),baseline)
        published=a.read_bytes()
        rerun=prepare_bank(self.addon,count=1025)
        self.assertEqual(rerun['created'],0)
        self.assertEqual(a.read_bytes(),published)
        self.assertEqual(font_path(self.addon,1).read_bytes(),b'preserve existing response')
        self.assertFalse(list(self.addon.glob('.fontseed-*')))

    def test_interrupted_preparation_resumes_without_overwriting_or_link_leaks(self):
        original_link=os.link;calls=0
        def fail(source,target):
            nonlocal calls
            calls+=1
            if calls==4: raise OSError('test interruption')
            original_link(source,target)
        with patch('companion.native.os.link',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'rerun to resume'): prepare_bank(self.addon,count=10)
        original=font_path(self.addon,1).read_bytes()
        self.assertEqual(len(list(self.addon.glob('fontreply*.ttf'))),3)
        self.assertFalse(list(self.addon.glob('.fontseed-*')))
        report=prepare_bank(self.addon,count=10)
        self.assertEqual((report['created'],report['preserved']),(7,3))
        self.assertEqual(font_path(self.addon,1).read_bytes(),original)

    def test_invalid_count_and_reserved_directory_are_rejected(self):
        for count in (0,-1,BANK_SIZE+1,True,2.5):
            with self.assertRaises(ValueError): prepare_bank(self.addon,count=count)
        font_path(self.addon,1).mkdir()
        with self.assertRaisesRegex(ValueError,'ordinary file'): prepare_bank(self.addon,count=1)


if __name__=='__main__':unittest.main()
