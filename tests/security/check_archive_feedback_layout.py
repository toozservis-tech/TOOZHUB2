"""Pure rendered-HTML feedback contract, with no HTTP, database or product mutation.

Execute the actual customer_web string renderer from its AST with only a response
capture and its actual constant CSP import. The application module is not imported,
so database/bootstrap configuration is not loaded. This is not browser visual QA.
"""
from pathlib import Path
from html.parser import HTMLParser
import ast
import builtins
import re
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Layout(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.stack = []
        self.alerts = []
        self.scripts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id') == 'alertContainer':
            self.alerts.append({'attrs': attrs, 'ancestors': self.stack.copy()})
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])
        if tag not in VOID:
            self.stack.append({'tag': tag, **attrs})

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                self.stack = self.stack[:index]
                break


def render_actual_customer_html():
    policy = ast.parse((ROOT / 'src/core/browser_policy.py').read_text())
    assignment = next(node for node in policy.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'LEGACY_ADMIN_CONTENT_SECURITY_POLICY'
                              for target in node.targets))
    csp = ast.literal_eval(assignment.value)
    source = ROOT / 'src/server/web_access.py'
    function = next(node for node in ast.parse(source.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'customer_web')
    function.decorator_list = []

    def import_constant(name, globals=None, locals=None, fromlist=(), level=0):
        if name != 'src.core.browser_policy' or tuple(fromlist) != ('LEGACY_ADMIN_CONTENT_SECURITY_POLICY',) or level:
            raise AssertionError('Customer string renderer added an unreviewed import: ' + name)
        return SimpleNamespace(LEGACY_ADMIN_CONTENT_SECURITY_POLICY=csp)

    namespace = {'__file__': str(source), 'Path': Path,
                 'HTMLResponse': lambda html, headers: SimpleNamespace(body=html, headers=headers),
                 '__builtins__': {**vars(builtins), '__import__': import_constant}}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['customer_web'](), csp


class ArchiveFeedbackLayout(unittest.TestCase):
    def test_single_live_region_is_outside_hidden_auth_in_raw_and_actual_customer_renderer(self):
        raw = (ROOT / 'web/index.html').read_text()
        response, _ = render_actual_customer_html()
        for label, html in [('raw', raw), ('customer', response.body)]:
            with self.subTest(label=label):
                parsed = Layout(html)
                self.assertEqual(len(parsed.alerts), 1)
                alert = parsed.alerts[0]
                self.assertEqual(alert['attrs'].get('role'), 'status')
                self.assertEqual(alert['attrs'].get('aria-live'), 'polite')
                self.assertEqual(alert['attrs'].get('aria-atomic'), 'true')
                for ancestor in alert['ancestors']:
                    self.assertNotEqual(ancestor.get('id'), 'authSection')
                    self.assertNotIn('hidden', ancestor.get('class', '').split())
                    self.assertNotIn('hidden', ancestor)
                css = re.search(r'#alertContainer\s*\{([^}]+)\}', html).group(1)
                self.assertRegex(css, r'position:\s*fixed')
                self.assertRegex(css, r'width:\s*min\(560px,\s*calc\(100%\s*-\s*24px\)\)')
                self.assertRegex(css, r'overflow-wrap:\s*anywhere')
                self.assertGreater(int(re.search(r'z-index:\s*(\d+)', css).group(1)), 2_000_000_000)

    def test_actual_customer_renderer_keeps_existing_session_and_csp_boundaries(self):
        response, csp = render_actual_customer_html()
        scripts = Layout(response.body).scripts
        self.assertIn('/web/customer-session.js', scripts)
        self.assertNotIn('/admin-session.js', scripts)
        self.assertIn('customer-features.js', scripts)
        self.assertEqual(response.headers['Content-Security-Policy'], csp)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')


if __name__ == '__main__':
    unittest.main(verbosity=2)
