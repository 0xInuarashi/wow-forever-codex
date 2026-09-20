from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from tools.install_addon import install
from tools.probe_session import ASSETS


class InstallAddonTests(unittest.TestCase):
    def test_fresh_checkout_install_generates_assets_and_preserves_existing_data(self):
        # Full 65,535-slot provisioning is verified separately; keep this test
        # focused on the code/assets available from a clean Git checkout.
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'CodexPixelBridge'
            with patch('tools.install_addon.prepare_bank',return_value={'created':0}) as bank:
                install(destination)
                bank.assert_called_once_with(destination.resolve(),progress=None)
            toc=(destination/'CodexPixelBridge.toc').read_text()
            for name in toc.splitlines():
                if name and not name.startswith('#'):
                    self.assertTrue((destination/name).is_file(),name)
            self.assertEqual(len(list(destination.glob('reply*.tga'))),4096)
            self.assertEqual(len(list(destination.glob('fontprobe*.ttf'))),8)
            for name in ASSETS:
                with Image.open(destination/name) as image: self.assertEqual(image.size,(64,64))
            keep={'fontprobe01.ttf':b'live diagnostic','reply0001.tga':b'live image',
                  'probe.tga':b'live probe','fontreply0001.ttf':b'live reply'}
            for name,body in keep.items(): (destination/name).write_bytes(body)
            with patch('tools.install_addon.prepare_bank'):
                install(destination)
            for name,body in keep.items(): self.assertEqual((destination/name).read_bytes(),body)


if __name__=='__main__':unittest.main()
