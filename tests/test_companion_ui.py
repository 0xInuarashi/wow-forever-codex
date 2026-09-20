from argparse import Namespace
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch, Mock
from companion.app import App
from companion.protocol import encode, render
from companion.visual import encode_control


class CompanionUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.project=self.base/'empty'; self.project.mkdir()
        self.state=self.base/'state'
        self.root=tk.Tk(); self.root.withdraw()
        args=Namespace(state=self.state,backend='mock',project=self.project,
                       sandbox='read-only',region=[8,8,512,16])
        self.app=App(self.root,args)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_folder_switch_persists_and_keeps_capture_settings(self):
        self.assertIn('empty',self.app.project_hint.get())
        self.app.toggle()
        work=self.base/'real-project'; work.mkdir(); (work/'README.md').write_text('Project')
        self.assertTrue(self.app.set_project(work))
        settings=json.loads((self.state/'launcher.json').read_text())
        self.assertEqual(settings['project'],str(work.resolve()))
        self.assertTrue(settings['start_capture'])
        self.assertEqual(self.app.project_hint.get(),'')
        self.app.toggle()

    def test_completed_status_survives_repeated_screen_frames(self):
        key='3132333435363738:1'
        self.app.inbox.add(key,'hello'); self.app.inbox.update(key,'done','reply')
        self.app.show_job_status('done',key)
        self.app.toggle()
        with patch('companion.app.ImageGrab.grab',return_value=render(encode('hello')[0])):
            self.app.tick()
        self.assertIn('Done',self.app.job_status.get())
        self.assertEqual(self.app.jobs.unfinished_tasks,0)
        self.assertIn('Receiving',self.app.status.get())
        self.app.toggle()

    def test_reply_notification_fires_for_completion_and_respects_mute(self):
        self.app.inbox.add('test:1','hello')
        self.app.events.put(('test:1','done','A reply'))
        with patch.object(self.app.banner,'show') as banner, patch.object(self.root,'bell') as bell:
            self.app.tick()
            banner.assert_called_once_with('done','A reply')
            bell.assert_called_once()
            self.app.notify_enabled.set(False)
            self.app.save_notification_preference()
            self.app.events.put(('test:1','failed','A failure'))
            self.app.tick()
            self.assertEqual(banner.call_count,1)
            self.assertFalse(json.loads((self.state/'launcher.json').read_text())['notifications'])

    def test_banner_can_open_reply_and_dismiss(self):
        self.app.banner.show('done','Completed work. '*30)
        self.root.update_idletasks()
        self.assertEqual(self.app.banner.title.get(),'Codex replied')
        self.assertLessEqual(len(self.app.banner.preview.get()),181)
        with patch.object(self.app.banner,'open_reply') as open_reply:
            self.app.banner.open()
            open_reply.assert_called_once()
        self.assertIsNone(self.app.banner.window)

    def test_preview_control_delivers_saved_reply_without_queueing_agent(self):
        key = '3132333435363738:1'
        self.app.inbox.add(key, 'hello')
        self.app.inbox.update(key, 'done', 'actual saved reply')
        self.app.visual = Mock()
        self.app.toggle()
        with patch('companion.app.ImageGrab.grab', return_value=render(encode_control())):
            self.app.tick()
        self.app.visual.accept.assert_called_once()
        control, snapshot = self.app.visual.accept.call_args.args
        self.assertEqual(control.request, 1)
        self.assertEqual(snapshot['reply'], 'actual saved reply')
        self.assertEqual(self.app.jobs.unfinished_tasks, 0)
        self.assertEqual(self.app.inbox.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
        self.app.toggle()

    def test_image_write_failure_does_not_stop_outbound_capture(self):
        self.app.visual = Mock()
        self.app.visual.accept.side_effect = OSError('image is locked')
        self.app.toggle()
        with patch('companion.app.ImageGrab.grab', return_value=render(encode_control())):
            self.app.tick()
        self.assertTrue(self.app.active)
        self.assertIsNotNone(self.app.visual)
        self.assertIn('image is locked', (self.app.args.state/'transport.jsonl').read_text())
        self.app.visual.accept.side_effect=None
        self.app.return_retry_at=0
        with patch('companion.app.ImageGrab.grab', return_value=render(encode_control())):
            self.app.tick()
        self.assertEqual(self.app.visual.accept.call_count,2)
        self.app.toggle()

    def test_native_control_routes_to_font_writer_without_submitting_job(self):
        self.app.native = Mock()
        self.app.visual = Mock()
        self.app.toggle()
        with patch('companion.app.ImageGrab.grab',return_value=render(encode_control(kind='font'))):
            self.app.tick()
        self.app.native.accept.assert_called_once()
        self.app.visual.accept.assert_not_called()
        self.assertEqual(self.app.jobs.unfinished_tasks,0)
        self.assertEqual(self.app.inbox.db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        self.app.toggle()
