import argparse
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from companion.agent_stream import run_stream


class AgentStreamTests(unittest.TestCase):
    def invoke(self, script, *, timeout=4, prompt='test café; $(literal)', callback=None):
        args = argparse.Namespace(codex='codex', sandbox='read-only', project=Path.cwd(), timeout=timeout)
        real_popen = subprocess.Popen

        def fixture(command, **kwargs):
            self.assertEqual(command[1:3], ['exec', '--json'])
            self.assertFalse(kwargs['shell'])
            self.assertNotIn(prompt, command)
            return real_popen([sys.executable, '-u', '-c', script], **kwargs)

        with patch('companion.agent_stream.subprocess.Popen', side_effect=fixture):
            return run_stream(args, prompt, callback or (lambda _: None))

    def test_real_process_updates_before_completion_and_replaces_item(self):
        updates = []
        script = '''
import json,sys,time
sys.stdin.reconfigure(encoding='utf-8'); text=sys.stdin.read()
print(json.dumps({'type':'item.updated','item':{'id':'a','type':'agent_message','text':'Working text'}}),flush=True)
time.sleep(0.3)
print(json.dumps({'type':'item.completed','item':{'id':'a','type':'agent_message','text':text}}),flush=True)
print(json.dumps({'type':'item.completed','item':{'id':'tool','type':'command_execution','aggregated_output':'not a reply'}}),flush=True)
print(json.dumps({'type':'turn.completed'}),flush=True)
'''
        started = time.monotonic()
        result = self.invoke(script, callback=lambda text: updates.append((text, time.monotonic())))
        self.assertEqual(result, ('done', 'test café; $(literal)'))
        self.assertEqual([text for text, _ in updates], ['Working text', 'test café; $(literal)'])
        self.assertGreater(updates[1][1] - updates[0][1], 0.2)
        self.assertLess(time.monotonic() - started, 4)

    def test_error_missing_completion_timeout_and_non_json(self):
        result = self.invoke("import sys,json;sys.stdin.read();print('diagnostic');print(json.dumps({'type':'error','message':'blocked'}))")
        self.assertEqual(result, ('failed', 'blocked'))
        self.assertEqual(self.invoke("import sys;sys.stdin.read();print('no JSON')")[0], 'failed')
        started = time.monotonic()
        result = self.invoke("import sys,time;sys.stdin.read();time.sleep(20)", timeout=0.3)
        self.assertEqual(result[0], 'failed')
        self.assertIn('timed out', result[1])
        self.assertLess(time.monotonic() - started, 4)

    def test_anonymous_partial_message_is_not_duplicated(self):
        script = '''
import json,sys
sys.stdin.read()
for kind,text in [('item.updated','partial'),('item.completed','complete')]:
    print(json.dumps({'type':kind,'item':{'type':'agent_message','text':text}}),flush=True)
print(json.dumps({'type':'turn.completed'}),flush=True)
'''
        self.assertEqual(self.invoke(script), ('done', 'complete'))


if __name__ == '__main__':
    unittest.main()
