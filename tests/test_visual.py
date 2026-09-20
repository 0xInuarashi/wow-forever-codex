import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from companion.protocol import decode_image, render, Assembler
from companion.visual import (BANK_SIZE, VisualBridge, encode_control, parse_control,
                              placeholder, render_reply, slot_path)

ROOT = Path(__file__).resolve().parents[1]


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addon = Path(self.temp.name) / 'CodexPixelBridge'
        self.addon.mkdir()
        (self.addon / 'CodexPixelBridge.toc').write_text('test')
        for i in [1, 2, 3, 4, 33, BANK_SIZE]:
            placeholder().save(slot_path(self.addon, i), format='TGA')
        self.now = 10.0
        self.bridge = VisualBridge(self.addon, clock=lambda: self.now)
        self.snapshot = {'id': b'12345678'.hex() + ':1', 'prompt': 'Test', 'state': 'done', 'reply': 'A real reply'}

    def tearDown(self):
        self.temp.cleanup()

    def control(self, **kwargs):
        return parse_control(encode_control(**kwargs))

    def test_control_pixels_are_valid_but_never_an_agent_prompt(self):
        frame = encode_control()
        self.assertEqual(decode_image(render(frame)), frame)
        self.assertEqual(parse_control(frame).slot, 1)
        with self.assertRaises(ValueError):
            Assembler().accept(frame)
        bad = bytearray(frame); bad[25] ^= 1
        with self.assertRaises(ValueError):
            parse_control(bad)
        for kwargs in [{'slot': BANK_SIZE + 2}, {'page': 0}, {'remaining_ms': 99999}, {'request': 0}]:
            with self.assertRaises(ValueError):
                encode_control(**kwargs)

    def test_transparent_slots_keep_reply_and_checkpoint_flattens_stack(self):
        self.assertTrue(self.bridge.accept(self.control(), self.snapshot))
        with Image.open(slot_path(self.addon, 1)) as first:
            self.assertEqual(first.size, (512, 512))
            before = first.convert('RGBA')
        self.now += 5
        self.assertTrue(self.bridge.accept(self.control(slot=2), self.snapshot))
        with Image.open(slot_path(self.addon, 2)) as empty:
            self.assertEqual(empty.getpixel((0, 0))[3], 0)
            combined = Image.alpha_composite(before, empty.resize(before.size))
            self.assertEqual(before.tobytes(), combined.tobytes())
        self.now += 5
        self.assertTrue(self.bridge.accept(self.control(slot=33), self.snapshot))
        with Image.open(slot_path(self.addon, 33)) as checkpoint:
            self.assertEqual(checkpoint.convert('RGBA').tobytes(), before.tobytes())

    def test_changed_reply_and_page_force_new_snapshot(self):
        self.bridge.accept(self.control(), self.snapshot)
        self.now += 5
        updated = dict(self.snapshot, reply='A newer reply')
        self.bridge.accept(self.control(slot=2), updated)
        with Image.open(slot_path(self.addon, 2)) as image:
            self.assertEqual(image.size, (512, 512))
        self.now += 5
        self.bridge.accept(self.control(slot=3, page=2), updated)
        with Image.open(slot_path(self.addon, 3)) as image:
            self.assertEqual(image.size, (512, 512))

    def test_next_past_last_page_keeps_reply_visible(self):
        first = render_reply(self.snapshot, 1)
        self.assertEqual(first.tobytes(), render_reply(self.snapshot, 2).tobytes())
        long_reply = dict(self.snapshot, reply='\n'.join(f'Line {i}' for i in range(25)))
        last = render_reply(long_reply, 2)
        self.assertNotEqual(render_reply(long_reply, 1).tobytes(), last.tobytes())
        self.assertEqual(last.tobytes(), render_reply(long_reply, 128).tobytes())

    def test_second_request_replaces_first_and_survives_extra_next(self):
        self.bridge.accept(self.control(), self.snapshot)
        self.now += 5
        second = dict(self.snapshot, id=b'12345678'.hex()+':2', prompt='Second question',
                      state='working', reply='')
        self.bridge.accept(self.control(slot=2, request=2), second)
        self.now += 5
        second.update(state='done', reply='The complete second reply.')
        self.bridge.accept(self.control(slot=3, request=2, page=2), second)
        with Image.open(slot_path(self.addon, 3)) as image:
            self.assertEqual(image.tobytes(), render_reply(second, 1).tobytes())
        self.now += 5
        self.bridge.accept(self.control(slot=4, request=2, page=2), second)
        with Image.open(slot_path(self.addon, 4)) as image:
            self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_deadline_frozen_frame_missing_file_and_wrong_job(self):
        frame = self.control()
        self.bridge.accept(frame, self.snapshot)
        original = slot_path(self.addon, 1).read_bytes()
        self.now += 6
        self.assertFalse(self.bridge.accept(frame, dict(self.snapshot, reply='too late')))
        self.assertEqual(slot_path(self.addon, 1).read_bytes(), original)
        with patch('companion.visual.render_reply', wraps=render_reply) as render_call:
            self.bridge.accept(self.control(slot=2), dict(self.snapshot, id='wrong'))
            self.assertEqual(render_call.call_args.args[0]['state'], 'waiting')
        self.now += 5
        with self.assertRaises(ValueError):
            self.bridge.accept(self.control(slot=5), self.snapshot)
        self.assertFalse(slot_path(self.addon, 5).exists())

    def test_render_overrun_skips_commit_and_uses_cached_image_next_slot(self):
        def slow_render(*args):
            self.now += 8
            return render_reply(*args)
        with patch('companion.visual.render_reply', side_effect=slow_render) as render_call:
            self.assertFalse(self.bridge.accept(self.control(), self.snapshot))
            self.assertTrue(self.bridge.accept(self.control(slot=2), self.snapshot))
            self.assertEqual(render_call.call_count, 1)

    def test_lua_control_and_native_texture_pool_are_bounded(self):
        try:
            from lupa.lua51 import LuaRuntime
        except ImportError:
            self.skipTest('Install Lupa for Lua 5.1 checks')
        lua = LuaRuntime(encoding=None)
        lua.execute(b'''
        now=0; widgets={}; UIParent={}
        local methods={}
        function methods:SetScript(k,v) self.scripts[k]=v end
        function methods:SetTexture(v) self.path=v end
        function methods:Hide() self.shown=false end
        function methods:Show() self.shown=true end
        local function widget(kind)
            local w=setmetatable({kind=kind,scripts={}}, {__index=function(t,k) return methods[k] or function() end end})
            table.insert(widgets,w); return w
        end
        function methods:CreateTexture() return widget('texture') end
        function methods:CreateFontString() return widget('font') end
        function CreateFrame() return widget('frame') end
        function GetTime() return now end
        ''')
        ns = lua.table()
        lua.execute((ROOT / 'addon/CodexPixelBridge/Protocol.lua').read_bytes(), b'CodexPixelBridge', ns)
        ns[b'Panel'] = lua.eval(b'CreateFrame()')
        ns[b'Minimap'] = lua.eval(b'CreateFrame()')
        ns[b'SetStatus'] = lambda *_: None
        lua.execute((ROOT / 'addon/CodexPixelBridge/Visual.lua').read_bytes(), b'CodexPixelBridge', ns)
        self.assertFalse(parse_control(ns[b'VisualControl'](b'12345678')).active)
        ns[b'OnPromptSubmitted'](1)
        self.assertEqual(parse_control(ns[b'VisualControl'](b'12345678')).remaining_ms, 6000)
        lua.execute(b"now=6; for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate() end end")
        control = parse_control(ns[b'VisualControl'](b'12345678'))
        self.assertEqual((control.slot, control.loaded), (2, 1))
        ns[b'ChangeVisualPage'](1)
        self.assertEqual(parse_control(ns[b'VisualControl'](b'12345678')).page, 2)
        lua.execute(b"count=0; for _,w in ipairs(widgets) do if w.kind=='texture' then count=count+1 end end")
        self.assertEqual(lua.globals()[b'count'], 64)
        for index in range(2, BANK_SIZE + 1):
            if index % 100 == 0:
                ns[b'OnPromptSubmitted'](1)
            lua.execute(b"now=now+5; for _,w in ipairs(widgets) do if w.scripts.OnUpdate then w.scripts.OnUpdate() end end")
        control = parse_control(ns[b'VisualControl'](b'12345678'))
        self.assertEqual(control.slot, BANK_SIZE + 1)
        self.assertFalse(control.active)

    def test_large_image_budget_survives_companion_restart(self):
        budget = Path(self.temp.name) / 'budget.json'
        with patch('companion.visual.MAX_FULL_IMAGES', 1):
            bridge = VisualBridge(self.addon, clock=lambda: self.now, budget_path=budget)
            bridge.accept(self.control(), self.snapshot)
            self.now += 5
            resumed = VisualBridge(self.addon, clock=lambda: self.now, budget_path=budget)
            resumed.accept(self.control(slot=2), dict(self.snapshot, reply='new'))
            with Image.open(slot_path(self.addon, 2)) as image:
                self.assertEqual(image.size, (128, 128))
            self.now += 5
            resumed.accept(self.control(slot=3), self.snapshot)
            with Image.open(slot_path(self.addon, 3)) as image:
                self.assertEqual(image.size, (2, 2))
            self.now += 5
            new_control = self.control(session=b'new-load')
            resumed.accept(new_control, dict(self.snapshot, id=b'new-load'.hex()+':1'))
            with Image.open(slot_path(self.addon, 1)) as image:
                self.assertEqual(image.size, (512, 512))

    def test_inactive_preview_can_resume_on_same_unused_slot(self):
        self.assertFalse(self.bridge.accept(self.control(active=False, remaining_ms=0), self.snapshot))
        self.now += 30
        self.assertTrue(self.bridge.accept(self.control(remaining_ms=6000), self.snapshot))


if __name__ == '__main__':
    unittest.main()
