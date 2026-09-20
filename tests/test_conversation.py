import json
from pathlib import Path
import tempfile
import unittest

from companion.app import Inbox
from companion.conversation import ConversationContext


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'inbox.sqlite3'
        self.inbox = Inbox(self.path)
        self.context = ConversationContext(self.path)
        self.session = '1234567890abcdef:'

    def tearDown(self):
        self.inbox.db.close()
        self.temp.cleanup()

    def add(self, key, prompt, state='done', reply='answer'):
        self.inbox.add(key, prompt)
        self.inbox.update(key, state, reply)

    def decoded(self, key, prompt='follow up'):
        return json.loads(self.context.prompt(key, prompt).split('\n\n', 1)[1])

    def test_history_is_ordered_and_scoped_to_prior_successful_same_session_jobs(self):
        self.add(self.session+'1', 'What is Comprehension?', reply='A Mage skill.')
        self.add('fedcba0987654321:1', 'unrelated conversation')
        self.add(self.session+'2', 'failed question', 'failed', 'error')
        self.add(self.session+'3', 'Can other classes learn it?', 'queued', '')
        self.add(self.session+'4', 'future message')
        data=self.decoded(self.session+'3', 'Can other classes learn it?')
        self.assertEqual(data['history'], [{'role':'user','content':'What is Comprehension?'},
                                          {'role':'assistant','content':'A Mage skill.'}])
        self.assertEqual(data['latest_user_message'], 'Can other classes learn it?')
        self.assertEqual(self.decoded(self.session+'1','hello'), {'history':[], 'latest_user_message':'hello'})

    def test_first_prompt_includes_item_link_format_without_changing_user_text(self):
        raw='What is [Empty Vial] (item ID 3371; link=item:3371::::::::8:1485:::::::::)?'
        self.add(self.session+'1',raw,'queued','')
        prompt=self.context.prompt(self.session+'1',raw)
        self.assertIn('[Item Name](item:12345)',prompt)
        self.assertIn('Do not invent item IDs',prompt)
        self.assertEqual(self.decoded(self.session+'1',raw)['latest_user_message'],raw)

    def test_queued_followup_sees_completion_before_ui_database_commit(self):
        self.add(self.session+'1', 'first', 'streaming', 'partial')
        self.add(self.session+'2', 'second', 'queued', '')
        self.context.remember(self.session+'1', 'actual final reply')
        self.assertEqual(self.decoded(self.session+'2')['history'][-1]['content'], 'actual final reply')
        self.inbox.update(self.session+'1', 'done', 'actual final reply')
        self.context=ConversationContext(self.path)
        self.assertEqual(self.decoded(self.session+'2')['history'][-1]['content'], 'actual final reply')

    def test_context_is_bounded_and_preserves_latest_prompt_literally(self):
        for n in range(1,12): self.add(self.session+str(n), 'question '+str(n), reply='🌏'*30000)
        self.add(self.session+'12', 'newest', 'queued', '')
        latest='$(do not execute); "answer this" café'
        output=self.context.prompt(self.session+'12',latest)
        self.assertLess(len(output),31000)
        data=json.loads(output.split('\n\n',1)[1])
        self.assertEqual(data['latest_user_message'],latest)
        self.assertEqual(data['history'][-2]['content'],'question 11')
        self.assertIn('shortened',data['history'][-1]['content'])
