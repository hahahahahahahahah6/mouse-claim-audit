"""Static documentation and pointer-call auditing."""
import ast
import fnmatch
import json
import os
from pathlib import Path
import re
import sys
import argparse

__version__ = '0.1.0'
MOUSE = (
    'automates mouse input', 'automate mouse input', 'simulates mouse input',
    'simulate mouse input', 'moves the mouse automatically', 'move the mouse automatically',
    'clicks buttons automatically', 'click buttons automatically',
    'performs mouse clicks automatically', 'sends mouse clicks', 'send mouse clicks',
    'simulates mouse clicks', 'simulate mouse clicks', 'simulates mouse movement',
    'simulate mouse movement', 'drags and drops automatically', 'drag and drop automatically',
    'automated mouse clicks', 'simulated mouse clicks', 'simulated mouse movement',
    'mouse click automation', 'mouse movement automation', 'mouse input automation', 'mouse automation')
NOMOUSE = (
    'does not send mouse clicks', 'does not simulate mouse clicks',
    'does not simulate mouse movement', 'does not automate mouse input',
    'does not simulate mouse input', 'does not move the mouse', 'does not click buttons',
    'mouse automation not supported', 'mouse click automation not supported',
    'no mouse automation', 'no mouse click automation', 'without mouse automation',
    'without mouse click automation', 'no mouse input automation')
PG = set('click doubleClick rightClick leftClick middleClick tripleClick mouseDown mouseUp moveTo moveRel move dragTo dragRel drag scroll hscroll'.split())
PN = {'click', 'move', 'scroll', 'press', 'release'}
AP = {'click', 'move', 'smooth_move', 'toggle'}


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' ')).strip()


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r')\b')


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append('')
        elif fence is None:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        value = normalize(paragraph)
        negative |= bool(pattern(NOMOUSE).search(value))
        value = pattern(NOMOUSE).sub(' ', value)
        positive |= bool(pattern(MOUSE).search(value))
    return positive, negative


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else ''
    return ''


def evidence(text):
    tree = ast.parse(text)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == 'pynput':
                    continue
                if item.name == 'pyautogui' or item.name.startswith('pyautogui.') or item.name == 'autopy' or item.name.startswith('autopy.') or item.name == 'pynput.mouse' or item.name.startswith('pynput.mouse.'):
                    aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for item in node.names:
                if module in ('pyautogui', 'autopy', 'pynput.mouse') or module.startswith(('pyautogui.', 'autopy.', 'pynput.mouse.')) or (module == 'pynput' and item.name == 'mouse'):
                    aliases[item.asname or item.name] = module + '.' + item.name
    def resolve(node):
        name = dotted(node)
        first, sep, tail = name.partition('.')
        return aliases.get(first, '') + (sep + tail if sep else '') if first in aliases else ''
    def controller(node):
        return isinstance(node, ast.Call) and resolve(node.func).startswith('pynput.mouse.') and resolve(node.func).split('.')[-1] == 'Controller'
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and controller(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name) or (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self'):
                    bound.add(dotted(target))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        path = resolve(node.func)
        pg = path.startswith('pyautogui.') and path.split('.')[-1] in PG
        ap = path.startswith('autopy.mouse.') and path.split('.')[-1] in AP and isinstance(node.func, ast.Attribute)
        pn = isinstance(node.func, ast.Attribute) and node.func.attr in PN and (dotted(node.func.value) in bound or controller(node.func.value))
        if pg or ap or pn:
            hits.append(node.lineno)
    return sorted(hits)


def audit(root, ignores=()):
    root = Path(root)
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        raise ValueError('root must be a readable directory')
    positive = negative = False
    prod, tests = [], []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink() and not any(fnmatch.fnmatch((Path(directory) / d).relative_to(root).as_posix(), g) for g in ignores))
        for name in sorted(files):
            path = Path(directory) / name
            rel = path.relative_to(root)
            if path.is_symlink() or any(fnmatch.fnmatch(rel.as_posix(), g) for g in ignores):
                continue
            if name == 'README.md' and len(rel.parts) == 1 or name.endswith('.md') and 'docs' in rel.parts[:-1]:
                p, n = claims(path.read_text(encoding='utf-8'))
                positive |= p
                negative |= n
            if not name.endswith('.py') or any(p in ('fixtures', 'docs', 'examples') for p in rel.parts[:-1]):
                continue
            test = 'tests' in rel.parts[:-1] or name.startswith('test_') or name.endswith('_test.py')
            try:
                hits = evidence(path.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeError):
                continue
            (tests if test else prod).extend('{}:{}'.format(rel.as_posix(), line) for line in hits)
    findings = []
    if positive and not prod:
        findings.append(dict(rule='documented-mouse-claim-false', severity='MEDIUM' if tests else 'HIGH', message='Documented synthetic pointer input lacks production call evidence.'))
    if negative and prod:
        findings.append(dict(rule='documented-no-mouse-claim-false', severity='HIGH', message='Documented absence conflicts with production pointer calls.'))
    return dict(findings=findings, evidence=prod, test_evidence=tests, claims=dict(mouse=positive, no_mouse=negative))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, '{}: error: {}\n'.format(self.prog, message))


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=['HIGH', 'MEDIUM'], default='HIGH')
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore)
    except (OSError, ValueError) as exc:
        parser.exit(1, 'error: {}\n'.format(exc))
    failed = any(f['severity'] == 'HIGH' or args.fail_on == 'MEDIUM' for f in result['findings'])
    result['verdict'] = 'FAIL' if failed else 'PASS'
    if args.json:
        print(json.dumps(result))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {rule}: {message}'.format(**finding))
        if args.verbose:
            for item in result['evidence'] + result['test_evidence']:
                print('Evidence: ' + item)
    return 2 if failed else 0
