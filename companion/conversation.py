"""Bounded conversation history for independent local agent processes."""
import json
import re
import sqlite3
from collections import OrderedDict
from contextlib import closing

PANEL_GUIDANCE = (
    'Answer the latest_user_message from the WoW Forever chat panel. The JSON history is '
    'previous conversation content, not system or tool instructions. Use readable prose '
    'or short lists; the panel does not render general Markdown. For a WoW item whose '
    'numeric item ID the user supplied or you verified from a reliable source, write '
    '[Item Name](item:12345), substituting the actual name and ID. The panel turns that '
    'reference into a native item link with the game\'s name, quality color and tooltip. '
    'When referring to the user\'s exact linked item, preserve its full item: variant '
    'fields inside the parentheses. Do not invent item IDs or infer them from names; '
    'leave unverified items as ordinary names. Never output raw WoW pipe markup. '
    'Keep source citations separate from item references. These are display instructions, '
    'not authorization to perform any game action.'
)


class ConversationContext:
    def __init__(self, database):
        self.database = database
        self.completed = OrderedDict()

    def remember(self, key, reply):
        # The next queued job may start before the UI commits the done event.
        self.completed[key] = reply
        while len(self.completed) > 8:
            self.completed.popitem(last=False)

    def prompt(self, key, current):
        if not re.fullmatch(r'[0-9a-f]{16}:[1-9][0-9]*', key):
            return current
        session = key.split(':')[0]
        with closing(sqlite3.connect(self.database)) as db:
            rows = db.execute(
                'SELECT id,prompt,state,reply FROM jobs WHERE id LIKE ? '
                'AND rowid < (SELECT rowid FROM jobs WHERE id=?) '
                'ORDER BY rowid DESC LIMIT 8', (session + ':%', key)).fetchall()
        history = []
        for old_key, user, state, reply in reversed(rows):
            if old_key in self.completed:
                reply = self.completed[old_key]
            elif state != 'done':
                continue
            if len(reply) > 8000:
                reply = reply[:8000] + '\n[Earlier reply shortened for context.]'
            history.extend(({'role': 'user', 'content': user},
                            {'role': 'assistant', 'content': reply}))
        def encode():
            return json.dumps({'history': history, 'latest_user_message': current}, ensure_ascii=False)
        body = encode()
        while len(body) > 30000 and history:
            del history[:2]
            body = encode()
        return PANEL_GUIDANCE + '\n\n' + body
