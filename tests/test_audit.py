"""Tests 01–30 map to the numbered spec requirements.
Test 31 exhausts all 24 positive and 14 negative phrases, listed independently
below, including every phrase not exercised by tests 01–30. Each negative phrase
also checks span removal, so embedded positive phrases cannot leak through.
"""
import contextlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mouse_claim_audit import audit, claims, evidence, main, normalize

ROOT = Path(__file__).resolve().parents[1]
GOOD = 'import pyautogui\npyautogui.click(1, 2)\n'
POSITIVE = '''automates mouse input|automate mouse input|simulates mouse input|simulate mouse input|moves the mouse automatically|move the mouse automatically|clicks buttons automatically|click buttons automatically|performs mouse clicks automatically|sends mouse clicks|send mouse clicks|simulates mouse clicks|simulate mouse clicks|simulates mouse movement|simulate mouse movement|drags and drops automatically|drag and drop automatically|automated mouse clicks|simulated mouse clicks|simulated mouse movement|mouse click automation|mouse movement automation|mouse input automation|mouse automation'''.split('|')
NEGATIVE = '''does not send mouse clicks|does not simulate mouse clicks|does not simulate mouse movement|does not automate mouse input|does not simulate mouse input|does not move the mouse|does not click buttons|mouse automation not supported|mouse click automation not supported|no mouse automation|no mouse click automation|without mouse automation|without mouse click automation|no mouse input automation'''.split('|')


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        return target

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(self.root), '--json', *args])
        return code, json.loads(out.getvalue())

    def case(self, source, claim='automates mouse input', severity=None, file='app.py'):
        self.write('README.md', claim)
        if source is not None:
            self.write(file, source)
        code, result = self.cli()
        self.assertEqual(code, 2 if severity == 'HIGH' else 0)
        self.assertEqual([(f['rule'], f['severity']) for f in result['findings']],
                         [('documented-mouse-claim-false', severity)] if severity else [])
        return result

    def test_01_plain(self):
        self.case(GOOD)

    def test_02_alias(self):
        self.case('import pyautogui as pg\npg.moveTo(1,2)')

    def test_03_from_alias(self):
        self.case('from pyautogui import dragTo as dg\ndg(1,2)')

    def test_04_scroll(self):
        self.case('import pyautogui\npyautogui.scroll(1)')

    def test_05_bound(self):
        self.case('from pynput.mouse import Controller\nctl=Controller()\nctl.click(1)')

    def test_06_self(self):
        self.case('from pynput.mouse import Controller\nclass A:\n def f(self):\n  self.ctl=Controller()\n  self.ctl.move(1,2)')

    def test_07_chain(self):
        self.case('from pynput.mouse import Controller\nController().scroll(1,2)')

    def test_08_autopy(self):
        self.case('from autopy import mouse\nmouse.click()')

    def test_09_autopy_alias(self):
        self.case('import autopy as ap\nap.mouse.smooth_move(1,2)')

    def test_10_import(self):
        self.case('import pyautogui', severity='HIGH')

    def test_11_string(self):
        self.case('text="click"\nbutton="left"', severity='HIGH')

    def test_12_keyboard(self):
        self.case('import pyautogui\npyautogui.press("a")\npyautogui.typewrite("a")', severity='HIGH')

    def test_13_screenshot(self):
        self.case('import pyautogui\npyautogui.screenshot()', severity='HIGH')

    def test_14_input(self):
        self.case('input("click")', severity='HIGH')

    def test_15_listener(self):
        self.case('from pynput.mouse import Listener\na=Listener()\na.start()\nwidget.bind("click", handler)', severity='HIGH')

    def test_16_generic(self):
        self.case('button.click()', severity='HIGH')

    def test_17_unbound(self):
        self.case('from pynput.mouse import Controller\nctl.click()', severity='HIGH')

    def test_18_negative(self):
        self.write('README.md', 'no mouse automation')
        self.write('app.py', GOOD)
        code, result = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual([(f['rule'], f['severity']) for f in result['findings']], [('documented-no-mouse-claim-false', 'HIGH')])

    def test_19_no_claim(self):
        self.case(GOOD, 'A helpful tool.')

    def test_20_noun(self):
        self.case('import pyautogui', 'the mouse chapter explains delivery')

    def test_21_instruction(self):
        self.case('import pyautogui', 'click here to continue')

    def test_22_user_click(self):
        self.case(GOOD, 'click the button to start')

    def test_23_no_source(self):
        self.case(None, severity='HIGH')
        self.case(None, 'no mouse automation')

    def test_24_tests_only(self):
        self.case(GOOD, severity='MEDIUM', file='tests/helper.py')
        code, result = self.cli('--fail-on', 'MEDIUM')
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'FAIL')

    def test_25_fences(self):
        self.case(None, '```text\nautomates mouse input\n```')
        self.case(None, '`automates mouse input`', 'HIGH')

    def test_26_negation(self):
        self.assertEqual(claims('does not send mouse clicks'), (False, True))
        self.case(None, 'does not send mouse clicks')

    def test_27_self(self):
        result = audit(ROOT)
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['claims'], {'mouse': False, 'no_mouse': False})
        text = normalize((ROOT / 'README.md').read_text())
        for phrase in POSITIVE + NEGATIVE:
            self.assertIsNone(re.search(r'\b' + re.escape(phrase) + r'\b', text), phrase)

    def test_28_cli(self):
        run = subprocess.run([sys.executable, '-m', 'mouse_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout.strip()), (0, '0.1.0'))
        self.write('app.py', GOOD)
        self.write('docs/nested/claim.md', 'automates mouse input')
        self.assertTrue(self.cli()[1]['claims']['mouse'])
        self.assertFalse(self.cli('--ignore', 'docs/*')[1]['claims']['mouse'])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([str(self.root), '--verbose']), 0)
        self.assertIn('Evidence: app.py:2', output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main([str(self.root / 'absent')])
        self.assertEqual(exc.exception.code, 1)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(['--bad-option'])
        self.assertEqual(exc.exception.code, 1)

    def test_29_env_guard(self):
        self.write('.env', 'GUARD_MARKER_ONLY')
        original = Path.open
        opened = []
        def guarded(path, *args, **kwargs):
            opened.append(str(path))
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            audit(self.root)
            audit(ROOT / 'tests/fixtures')
        self.assertFalse(any(Path(p).name == '.env' for p in opened))

    def test_30_packaging(self):
        for path in list((ROOT / 'mouse_claim_audit').glob('*.py')) + list((ROOT / 'tests').glob('*.py')) + [ROOT / 'README.md']:
            self.assertIsNone(re.search(r'\bpy' + r'thon\b', path.read_text()), str(path))
        text = (ROOT / 'pyproject.toml').read_text()
        self.assertIn('setuptools>=77', text)
        self.assertIn('license = "MIT"', text)
        self.assertIn('>=3.9', text)
        self.assertIn('recursive-include tests', (ROOT / 'MANIFEST.in').read_text())

    def test_31_phrase_exhaustion(self):
        self.assertEqual(len(POSITIVE), 24)
        self.assertEqual(len(NEGATIVE), 14)
        for phrase in POSITIVE:
            with self.subTest(positive=phrase):
                self.assertEqual(claims(phrase), (True, False))
                self.case(None, phrase, 'HIGH')
        for phrase in NEGATIVE:
            with self.subTest(negative=phrase):
                self.assertEqual(claims(phrase), (False, True))
                self.write('README.md', phrase)
                self.write('app.py', GOOD)
                code, result = self.cli()
                self.assertEqual(code, 2)
                self.assertEqual([(f['rule'], f['severity']) for f in result['findings']], [('documented-no-mouse-claim-false', 'HIGH')])

    def test_32_provider_routes(self):
        from mouse_claim_audit import PG, PN, AP
        for method in PG:
            for source in ('import pyautogui as pg\npg.{}()'.format(method), 'from pyautogui import {} as action\naction()'.format(method)):
                with self.subTest(source=source):
                    self.assertTrue(evidence(source))
        for method in PN:
            for prefix in ('from pynput import mouse', 'import pynput.mouse as mouse'):
                self.assertTrue(evidence(prefix + '\nc=mouse.Controller()\nc.{}()'.format(method)))
        for method in AP:
            self.assertTrue(evidence('import autopy\nautopy.mouse.{}()'.format(method)))
        self.assertTrue(evidence('from pyautogui.extra import click as c\nc()'))
        self.assertTrue(evidence('from pynput.mouse.extra import Controller as C\nC().click()'))

    def test_33_non_evidence(self):
        for source in ('import pynput\nc=pynput.mouse.Controller()\nc.click()', 'mouse.click()', 'from other import click\nclick()', 'import keyboard\nkeyboard.send("a")', 'def click():\n print("click")\nclick()', '@app.get("/")\ndef f():\n return "click"', 'import subprocess\nsubprocess.run(["xdotool", "click", "1"])', 'import pyautogui\npyautogui.hotkey("a")\npyautogui.position()', '# pyautogui.click()\n"pyautogui.click()"'):
            with self.subTest(source=source):
                self.assertEqual(evidence(source), [])

    def test_34_scope_and_symlinks(self):
        self.write('README.md', 'automates mouse input')
        for path in ('fixtures/a.py', 'docs/a.py', 'examples/a.py'):
            self.write(path, GOOD)
        external = self.write('excluded/source.txt', GOOD)
        (self.root / 'linked.py').symlink_to(external)
        self.assertEqual(self.cli()[0], 2)
        self.write('unit_test.py', GOOD)
        self.assertEqual(self.cli()[1]['findings'][0]['severity'], 'MEDIUM')
        self.assertEqual(self.cli('--ignore', '*_test.py')[0], 2)

    def test_35_normalization(self):
        self.assertEqual(claims('AUTOMATES-MOUSE\nINPUT'), (True, False))
        self.assertEqual(claims("doesn't send mouse clicks"), (False, True))
        self.assertEqual(claims('automates mouse\n\ninput'), (False, False))
        self.assertEqual(claims('xautomates mouse inputx'), (False, False))
        self.assertEqual(claims('~~~\nautomates mouse input\n~~~'), (False, False))

    def test_36_module_pairing_and_negative_docs(self):
        self.write('README.md', 'automates mouse input')
        self.write('first.py', 'from pynput.mouse import Controller\nc=Controller()')
        self.write('second.py', 'c.click()')
        self.assertEqual(self.cli()[0], 2)
        self.write('first.py', GOOD)
        self.write('README.md', 'A tool.')
        self.write('tests/docs/negative.md', 'no mouse automation')
        self.assertEqual(self.cli()[1]['findings'][0]['rule'], 'documented-no-mouse-claim-false')


if __name__ == '__main__':
    unittest.main()
