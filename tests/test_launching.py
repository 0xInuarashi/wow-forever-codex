import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from companion.launching import find_codex


class DiscoveryTests(unittest.TestCase):
    def test_explorer_without_codex_on_path(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'OpenAI/Codex/bin/desktop-version/codex.exe'
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b'fixture')
            with patch.dict(os.environ, {'LOCALAPPDATA': temp}), patch('shutil.which', return_value=None):
                self.assertEqual(find_codex(), str(exe.resolve()))
                self.assertEqual(find_codex(str(Path(temp)/'removed-version.exe')), str(exe.resolve()))

    def test_remembered_install_precedes_other_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'codex.exe'
            exe.write_bytes(b'fixture')
            with patch('shutil.which', side_effect=AssertionError('Should use remembered path')):
                self.assertEqual(find_codex(str(exe)), str(exe.resolve()))

    def test_missing_install_returns_no_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {'LOCALAPPDATA': temp}), patch('shutil.which', return_value=None):
                self.assertEqual(find_codex(), '')

    def test_current_app_version_selected_after_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'OpenAI/Codex/bin'
            old, new = root/'old/codex.exe', root/'new/codex.exe'
            for exe in (old, new):
                exe.parent.mkdir(parents=True); exe.write_bytes(b'fixture')
            os.utime(old, (1000,1000)); os.utime(new, (2000,2000))
            with patch.dict(os.environ, {'LOCALAPPDATA': temp}), patch('shutil.which', return_value=None):
                self.assertEqual(find_codex(), str(new.resolve()))
