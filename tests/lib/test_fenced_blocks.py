from ..util.mock_progress import MockProgress
from lamarkdown.lib import fenced_blocks

import unittest
from unittest.mock import Mock, PropertyMock

from pathlib import Path
import sys
import tempfile


class FencedBlocksTestCase(unittest.TestCase):

    def test_command_formatter(self):
        # It's a safe-ish bet that 'python3' is installed on the test machine.
        fmt = fenced_blocks.command_formatter(
            Mock(),
            ['python3', '-c', r'text = input() ; print(f"<div>{text}</div>")']
        )

        output = fmt('Hello', 'mock-lang', 'mock-class', {}, None).strip()
        self.assertEqual('<div>Hello</div>', output)


    def test_caching_formatter(self):
        mock_formatter = Mock()
        mock_formatter.return_value = '<div>Hello</div>'

        mock_build_params = Mock()
        type(mock_build_params).build_cache = PropertyMock(return_value = {})  # Trivial 'cache'

        fmt = fenced_blocks.caching_formatter(mock_build_params, 'mock', mock_formatter)

        for source, language, css_class, options in [
            ('text1', 'lang1', 'class1', {'op': 1}),
            ('text1', 'lang1', 'class1', {'op': 1}),

            ('text1', 'lang1', 'class1', {'op': 2}),
            ('text1', 'lang1', 'class2', {'op': 1}),
            ('text1', 'lang2', 'class1', {'op': 1}),
            ('text2', 'lang1', 'class1', {'op': 1}),

            ('text2', 'lang2', 'class2', {'op': 2}),
            ('text2', 'lang2', 'class2', {'op': 2}),
        ]:
            result = fmt(source, language, css_class, options, None).strip()
            self.assertEqual('<div>Hello</div>', result)

        mock_formatter.assert_any_call('text1', 'lang1', 'class1', {'op': 1}, None)
        mock_formatter.assert_any_call('text1', 'lang1', 'class1', {'op': 2}, None)
        mock_formatter.assert_any_call('text1', 'lang1', 'class2', {'op': 1}, None)
        mock_formatter.assert_any_call('text1', 'lang2', 'class1', {'op': 1}, None)
        mock_formatter.assert_any_call('text2', 'lang1', 'class1', {'op': 1}, None)
        mock_formatter.assert_any_call('text2', 'lang2', 'class2', {'op': 2}, None)
        self.assertEqual(6, mock_formatter.call_count)


    def test_exec_formatter(self):
        mock_build_params = Mock()

        mock_formatter = Mock()
        mock_formatter.return_value = '<div>Hello</div>'

        fmt = fenced_blocks.exec_formatter(mock_build_params, 'mock', mock_formatter)

        type(mock_build_params).allow_exec = PropertyMock(return_value = True)
        result = fmt('text', 'lang', 'class', {}, None)
        self.assertEqual('<div>Hello</div>', result)
        mock_build_params.progress.error.assert_not_called()

        type(mock_build_params).allow_exec = PropertyMock(return_value = False)
        result = fmt('text', 'lang', 'class', {}, None)
        self.assertNotEqual('<div>Hello</div>', result)
        mock_build_params.progress.error.assert_called_once()


    def test_attr_formatter(self):
        mock_formatter = Mock()

        fmt = fenced_blocks.attr_formatter(mock_formatter)

        for base_html,              cls,  classes,      id, attrs, expected in [
            ('<A>X</A>',            '',   [],           None, {},  '<A>X</A>'),
            ('<A>X</A>',            'c1', [],           None, {},  '<A class="c1">X</A>'),
            ('<A>X</A>',            '',   ['c2'],       None, {},  '<A class="c2">X</A>'),
            ('<A>X</A>',            '',   ['c2', 'c3'], None, {},  '<A class="c2 c3">X</A>'),
            ('<A>X</A>',            'c1', ['c2'],       None, {},  '<A class="c1 c2">X</A>'),
            ('<A>X</A>',            'c1', ['c2', 'c3'], None, {},  '<A class="c1 c2 c3">X</A>'),
            ('<A class="c0">X</A>', 'c1', [],           None, {},  '<A class="c0 c1">X</A>'),
            ('<A class="c0">X</A>', '',   ['c2'],       None, {},  '<A class="c0 c2">X</A>'),
            ('<A class="c0">X</A>', '',   ['c2', 'c3'], None, {},  '<A class="c0 c2 c3">X</A>'),
            ('<A class="c0">X</A>', 'c1', ['c2'],       None, {},  '<A class="c0 c1 c2">X</A>'),
            ('<A class="c0">X</A>', 'c1', ['c2', 'c3'], None, {},  '<A class="c0 c1 c2 c3">X</A>'),

            ('<A>X</A>',            '',   [],           'i1', {},  '<A id="i1">X</A>'),
            ('<A id="i0">X</A>',    '',   [],           'i1', {},  '<A id="i1">X</A>'),

            ('<A a="1">X</A>', '', [], None, {'a': 2, 'b': 3}, '<A a="2" b="3">X</A>'),
            ('<A a="1">X</A>', '', [], None, {'b': 3, 'c': 4}, '<A a="1" b="3" c="4">X</A>'),

            ('<A class="c0" id="i0">X</A>', 'c1', ['c2', 'c3'], 'i1', {'a': 2, 'b': 3},
             '<A class="c0 c1 c2 c3" id="i1" a="2" b="3">X</A>'),
        ]:
            # NOTE: we're cheating a bit here by relying on a predictable ordering of class, id
            # and other attributes.

            mock_formatter.return_value = base_html
            result = fmt('text', 'lang', cls, {}, None,
                         classes = classes, id_value = id, attrs = attrs)
            self.assertEqual(expected, result)


    def test_matplotlib_formatter(self):
        # Matplotlib isn't actually a dependency, so mock the entire module.
        sys.modules['matplotlib'] = Mock()
        sys.modules['matplotlib.pyplot'] = Mock()
        import matplotlib.pyplot as mock_plot

        # Stub implementation of matplotlib.pyplot.save_fig().
        def save_fig_stub(buf, *a, **k):
            buf.write(b'<svg>Hello</svg>')
        type(mock_plot).savefig = PropertyMock(return_value = save_fig_stub)

        mock_build_params = Mock()

        # Stub implementation of arbitrary plotting function.
        mock_plot_fn = Mock()
        test_env = {'mock_plot_fn': mock_plot_fn}
        type(mock_build_params).env = PropertyMock(return_value = test_env)

        fmt = fenced_blocks.matplotlib_formatter(mock_build_params)

        result = fmt('mock_plot_fn()', 'lang', 'class', {}, None).strip()
        self.assertEqual('<img src="data:image/svg+xml;base64,PHN2Zz5IZWxsbzwvc3ZnPg==" />',
                         result)
        mock_plot_fn.assert_called_once()
        mock_plot.clf.assert_called_once()


    def test_r_plot_formatter(self):
        # NOTE: the production function contains R code, so we can't get out of invoking R itself.
        with tempfile.TemporaryDirectory() as dir:
            mock_build_params = Mock()
            type(mock_build_params).build_dir = PropertyMock(return_value = Path(dir))
            type(mock_build_params).progress = PropertyMock(return_value = MockProgress())

            fmt = fenced_blocks.r_plot_formatter(mock_build_params)
            result = fmt('dev.new(); barplot(1:2)', 'lang', 'class', {}, None).strip()

            self.assertRegex(
                result,
                r'<img[ ]src="data:image/svg\+xml;base64,[A-Za-z0-9+/]+=*"[ ]/>')
