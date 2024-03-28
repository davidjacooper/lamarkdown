from ..util.mock_progress import MockProgress
from ..util.mock_cache import MockCache
from ..util.markdown_ext import entry_point_cls
import unittest
from unittest.mock import patch
from hamcrest import (all_of, assert_that, contains_exactly, contains_inanyorder, contains_string,
                      empty, has_entries, has_properties, has_property, instance_of, is_, not_,
                      not_none, same_instance, string_contains_in_order)

import lamarkdown.ext.latex
import markdown
import lxml

import base64
import os
from pathlib import Path
import re
import sys
import tempfile
from textwrap import dedent

sys.modules['la'] = sys.modules['lamarkdown.ext']


class LatexTestCase(unittest.TestCase):
    def setUp(self):
        self.progress = None
        self.tmp_dir_context = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp_dir_context.__enter__())

        self.tex_file = self.tmp_dir / 'output.tex'

        # Create a tiny Python script to act as a mock 'tex' compiler.
        self.mock_tex_command = self.tmp_dir / 'mock_tex_command'
        self.mock_tex_command.write_text(dedent(
            fr'''
            from pathlib import *
            import sys
            import shutil

            # If the .tex file (the one at the known location we're about to copy to) already
            # exists, find a new name. This lets us write test cases with multiple Latex
            # snippets.
            tex_file = {repr(self.tex_file)}
            if tex_file.exists():
                index = 1
                while (t := Path(str(tex_file) + str(index))).exists():
                    index += 1
                tex_file = t

            # Copy the .tex file to a known location, so the test case can find and read it.
            actual_tex_file = sys.argv[1]
            shutil.copyfile(actual_tex_file, tex_file)

            # Generate a mock .pdf file to satisfy the production code's checks.
            mock_pdf_file = sys.argv[2]
            Path(mock_pdf_file).write_text('mock')
            '''
        ))

        self.mock_svg = re.sub(
            r'\n\s*',
            '',
            '''
            <svg xmlns="http://www.w3.org/2000/svg" width="45" height="15" viewBox="1 1 1 1">
                <text x="0" y="15">mock</text>
            </svg>
            '''
        )

        # Create another tiny Python script to act as a mock 'pdf2svg' converter.
        self.mock_pdf2svg_command = self.tmp_dir / 'mock_pdf2svg_command'
        self.mock_pdf2svg_command.write_text(dedent(
            fr'''
            import pathlib, sys

            # Generate a mock output .svg file.
            pathlib.Path(sys.argv[2]).write_text('{self.mock_svg}')
            '''
        ))



    def tearDown(self):
        self.tmp_dir_context.__exit__(None, None, None)


    def run_markdown(self,
                     markdown_text: str,
                     extra_extensions: list = [],
                     expect_error: bool = False,
                     **kwargs):
        self.progress = MockProgress(expect_error = expect_error)
        md = markdown.Markdown(
            extensions = ['la.latex', *extra_extensions],
            extension_configs = {
                'la.latex': {
                    'build_dir': self.tmp_dir,
                    'progress': self.progress,
                    'tex': f'python {self.mock_tex_command} in.tex out.pdf',
                    'pdf_svg_converter': f'python {self.mock_pdf2svg_command} in.pdf out.svg',
                    **kwargs
                }
            }
        )
        return md.convert(dedent(markdown_text).strip())


    def assert_tex_regex(self, regex, file_index = ''):
        tex = Path(f'{self.tex_file}{file_index or ""}').read_text()
        self.assertRegex(
            tex,
            regex,
            f'generated Tex code (#{file_index or 0}) does not match expected pattern\n---actual '
            f'tex---\n{tex}\n---expected pattern---\n{dedent(regex).strip()}')

    @property
    def mock_svg_b64(self):
        return base64.b64encode(self.mock_svg.encode('utf-8')).decode('utf-8')


    def test_single_env(self):
        '''Check a single Latex environment.'''

        html = self.run_markdown(
            r'''
            Paragraph1

            \begin{tikzpicture}
                Latex code
            \end{tikzpicture}

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* \\begin \{tikzpicture\}
            \s* Latex[ ]code
            \s* \\end \{tikzpicture\}
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)
        self.assertIn(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}', html)


    def test_single_env_document(self):
        '''Check a complete embedded Latex document.'''

        html = self.run_markdown(
            r'''
            Paragraph1

            \begin{document}
                Latex code
            \end{document}

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)
        self.assertIn(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}', html)


    def test_single_env_preamble(self):
        '''Check a single Latex environment with preceding preamble.'''

        html = self.run_markdown(
            r'''
            Paragraph1

            \usepackage{xyz}
            \somemacro{abc}
            \begin{tikzpicture}
                Latex code
            \end{tikzpicture}

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\usepackage \{xyz\}
            \s* \\somemacro \{abc\}
            \s* \\begin \{document\}
            \s* \\begin \{tikzpicture\}
            \s* Latex[ ]code
            \s* \\end \{tikzpicture\}
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)
        self.assertIn(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}', html)


    def test_full_doc(self):
        html = self.run_markdown(
            r'''
            Paragraph1

            \documentclass{article}
            \somemacro{def}
            \begin{document}
                Latex code
            \end{document}

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass \{article\}
            \s* \\somemacro \{def\}
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)
        self.assertIn(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}', html)


    def test_attr(self):
        '''Check that attributes are assigned properly.'''

        html = self.run_markdown(
            r'''
            Paragraph1

            \begin{document}
                Latex code
            \end{document}
            {alt="alt text" width="5" #myid .myclass}

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)

        img_tag = re.search('<img[^>]+>', html).group(0)
        self.assertIn('alt="alt text"', img_tag)
        self.assertIn('width="5"', img_tag)
        self.assertIn('id="myid"', img_tag)
        self.assertIn('class="myclass"', img_tag)


    def test_latex_comments(self):
        '''Check that Latex '%' comments don't stuff up the parsing.'''

        html = self.run_markdown(
            r'''
            Paragraph1

            \usepackage{abc} % \begin{tikzpicture}
            \begin{document} % \end{document}
                Latex code   % \end{tikzpicture}
            \end{document}   % \documentclass

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\usepackage \{abc\} (\s*%[^\n]+)?
            \s* \\begin \{document\} (\s*%[^\n]+)?
            \s* Latex[ ]code         (\s*%[^\n]+)?
            \s* \\end \{document\}   (\s*%[^\n]+)?
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)
        self.assertIn(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}', html)


    def test_html_comments(self):
        '''
        Check that HTML comments don't stuff up the parsing. This is complicated (on the production
        side) by the fact that Python Markdown appears to do its own substitution trick on HTML
        comments, but not all of them; perhaps only those where the <!-- and --> appear on separate
        lines.'''

        html = self.run_markdown(
            r'''
            Paragraph1

            \usepackage{abc} <!-- \begin{tikzpicture} -->
            <!--
            \usepackage{xyz}
            -->
            \begin{document} <!-- \end{document} -->
                Latex code   <!-- \end{tikzpicture} -->
            \end{document}   <!-- \documentclass -->

            Paragraph2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\usepackage \{abc\}
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertIn('<p>Paragraph1</p>', html)
        self.assertIn('<p>Paragraph2</p>', html)
        self.assertIn(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}', html)


    def test_block_commented_out(self, **kwargs):
        '''
        Check that an entire Latex snippet is ignored if it occurs entirely within an HTML comment.
        '''

        self.run_markdown(
            r'''
            Paragraph1 <!--

            \begin{document}
                Latex code
            \end{document}  -->

            Paragraph2
            ''',
            strip_html_comments = True)

        self.assertFalse(
            self.tex_file.is_file(),
            'The .tex file should not have been created, because the Latex code was commented out.')


    # Note: I'm not sure how to construct the following test case properly.
    # Python Markdown intercepts some <!-- --> comments itself, but not all of them, meaning that
    # embedding Latex code in HTML comments *may or may not* make it visible to the latex
    # extension code. There's no definitive expectation on what should happen here.

    # def test_block_not_commented_out(self):
    #     html = self.run_markdown(
    #         r'''
    #         Paragraph1
    #         <!--
    #
    #         \begin{document}
    #             Latex code
    #         \end{document}  -->
    #
    #         Paragraph2
    #         ''',
    #         strip_html_comments = False)
    #
    #     self.assertTrue(
    #         self.tex_file.is_file(),
    #         'The .tex file should have been created. Though the Latex code was commented out,'
    #         'the comments should have been disregarded.')


    def test_html_comments_off(self):
        'Check that HTML comments remain visible within a Tex block, if the option is turned off.'

        self.run_markdown(
            r'''
            \begin{document}
                <!-- commented out -->
                Latex code
                <!-- also commented out -->
            \end{document}''',
            strip_html_comments = False)

        assert_that(
            Path(self.tex_file).read_text(),
            string_contains_in_order(
                r'\begin{document}',
                '<!-- commented out -->',
                'Latex code',
                '<!-- also commented out -->',
                r'\end{document}'
            ))


    def test_embedded_in_paragraph(self):
        '''
        Previously, when the extension used a BlockProcessor, it would only identify Latex snippets
        starting in a new block; effectively a new paragraph.
        '''

        html = self.run_markdown(
            r'''
            Text1
            \begin{document}
                Latex code
            \end{document}
            Text2
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertRegex(
            html,
            r'<p>Text1\s*'
            + re.escape(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}" />')
            + r'\s*Text2</p>')


    def test_embedded_in_list(self):
        '''
        Previously, when the extension used a BlockProcessor, Latex snippets embedded in lists
        couldn't contain blank lines.
        '''

        html = self.run_markdown(
            r'''
            * List item 1

            * List item 2

                \begin{document}
                    Latex code 1

                    Latex code 2

                    Latex code 3
                \end{document}

                Trailing paragraph

            * List item 3
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* Latex[ ]code[ ]1
            \s* Latex[ ]code[ ]2
            \s* Latex[ ]code[ ]3
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertRegex(
            html,
            fr'''(?x)
            \s* <ul>
            \s* <li> \s* <p> List[ ]item[ ]1 \s* </p> \s* </li>
            \s* <li>
            \s* <p> List[ ]item[ ]2 \s* </p>
            \s* <p> <img[ ]src="data:image/svg\+xml;base64,{re.escape(self.mock_svg_b64)}"
                \s* /? > \s* </p>
            \s* <p> Trailing[ ]paragraph \s* </p>
            \s* </li>
            \s* <li> \s* <p> List[ ]item[ ]3 \s* </p> \s* </li>
            \s* </ul>
            \s*
            ''')


    def test_embedding_as_svg_element(self):
        '''
        Check that we can embed SVG content using an <svg> element (not just an <img> element with
        a data URL).
        '''

        html = self.run_markdown(
            r'''
            Paragraph1

            \begin{document}
                Latex code
            \end{document}

            Paragraph2
            ''',
            embedding = 'svg_element')

        self.assertRegex(html, r'<svg[^>]*><text[^>]*>mock</text></svg>')


    def test_latex_options(self):
        '''Check that the 'prepend', 'doc_class' and 'doc_class_options' config options work.'''
        self.run_markdown(
            r'''
            Paragraph1

            \begin{document}
                Latex code
            \end{document}

            Paragraph2
            ''',
            prepend = r'\usepackage{mypackage}',
            doc_class = 'myclass',
            doc_class_options = 'myoptions')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass \[ myoptions \] \{ myclass \}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\usepackage \{mypackage\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')


    def test_prepend_full_doc(self):
        '''Check that the 'prepend' option works on a full document.'''
        self.run_markdown(
            r'''
            Paragraph1

            \documentclass{article}
            \begin{document}
                Latex code
            \end{document}

            Paragraph2
            ''',
            prepend = r'\usepackage{mypackage}'
        )

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass \{ article \}
            \s* \\usepackage \{mypackage\}
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')


    def test_multiple(self):
        '''Check that we can process multiple Latex snippets in a single markdown file.'''
        html = self.run_markdown(
            r'''
            Paragraph1

            \begin{document}
                Latex code 0
            \end{document}

            Paragraph2

            \begin{document}
                Latex code 1
            \end{document}

            Paragraph3

            \begin{document}
                Latex code 2
            \end{document}

            Paragraph4
            ''')

        for i in [0, 1, 2]:
            self.assert_tex_regex(
                fr'''(?x)
                ^\s* \\documentclass (\[\])? \{{standalone\}}
                \s* ( \\usepackage \{{tikz\}} )?
                \s* \\begin \{{document\}}
                \s* Latex[ ]code[ ]{i}
                \s* \\end \{{document\}}
                \s* $
                ''',
                file_index = i)

        for i in [1, 2, 3, 4]:
            self.assertIn(f'<p>Paragraph{i}</p>', html)

        self.assertEqual(
            3, html.count(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}'),
            'There should be 3 <img> elements, one for each Latex snippet')



    def test_multiple_cached(self):
        '''
        Check that, when processing multiple identical Latex snippets, we use the cache rather than
        re-compiling redundantly.
        '''

        html = self.run_markdown(
            r'''
            Paragraph1

            \begin{document}
                Latex code
            \end{document}

            Paragraph2

            \begin{document}
                Latex code
            \end{document}

            Paragraph3

            \begin{document}
                Latex code
            \end{document}

            Paragraph4
            ''')

        self.assert_tex_regex(r'''(?x)
            ^\s* \\documentclass (\[\])? \{standalone\}
            \s* ( \\usepackage \{tikz\} )?
            \s* \\begin \{document\}
            \s* Latex[ ]code
            \s* \\end \{document\}
            \s* $
        ''')

        self.assertFalse(Path(f'{self.tex_file}1').exists())
        self.assertFalse(Path(f'{self.tex_file}2').exists())

        for i in [1, 2, 3, 4]:
            self.assertIn(f'<p>Paragraph{i}</p>', html)

        self.assertEqual(
            3, html.count(f'<img src="data:image/svg+xml;base64,{self.mock_svg_b64}'),
            'There should be 3 <img> elements, one for each Latex snippet')


    def test_converter_corrections(self):
        svg = '''
            <svg version='1.1'
                 xmlns='http://www.w3.org/2000/svg'
                 xmlns:xlink='http://www.w3.org/1999/xlink'
                 width='40pt' height='30pt'
                 viewBox='0 0 1 1'>
            </svg>
        '''
        uncorrected_svg = svg.replace('pt', '')

        assert_that(
            lamarkdown.ext.latex.LatexCompiler.CONVERTER_CORRECTIONS['pdf2svg'](uncorrected_svg),
            is_(svg))


    def test_invalid_options(self):
        for option in ['embedding', 'math']:
            self.run_markdown(
                r'''
                \begin{document}
                    Latex code
                \end{document}
                ''',
                expect_error = True,
                **{option: 'notanoption'}
            )

            assert_that(
                self.progress.error_messages,
                contains_exactly(has_properties({
                    'location': 'la.latex',
                    'msg': contains_string(f'"{option}"')
                })))


    def test_build_dir_failure(self):
        '''Checks that a failure to write the .tex file results in an error message.'''

        # Cause the build directory to be non-existent.
        self.tmp_dir = self.tmp_dir / 'nonexistent'
        self.tmp_dir.write_text("Can't be a directory if it's a file.")

        self.run_markdown(
            r'''
            \begin{document}
                Latex code
            \end{document}
            ''',
            expect_error = True,
        )

        assert_that(
            self.progress.error_messages,
            contains_exactly(has_property('location', 'la.latex')))


    def test_timeout(self):
        r'''
        Certain tex code (e.g., \def\x{\x}\x) can produce infinite loops, and the la.latex extension
        should timeout after N seconds (3 by default) of no output.
        '''

        # Use a different mock 'tex' compiler here. It waits for only 1 second, but we set the
        # timeout to 0.5 seconds below. (Certainly no need for a real infinite loop!)
        self.mock_tex_command.write_text(dedent('''
            import pathlib, sys, time
            time.sleep(1)
            pathlib.Path(sys.argv[2]).write_text('mock PDF content')
        '''))

        self.run_markdown(
            r'''
            \begin{document}
                Latex code
            \end{document}
            ''',
            expect_error = True,
            timeout = 0.5
        )
        assert_that(
            self.progress.error_messages,
            contains_exactly(has_property('msg', contains_string('timed out'))))


    def test_non_timeout(self):
        '''
        The timeout for running external commands should be reset if we receive ongoing output.
        That is, a command can take longer than the specified timeout, provided it still appears to
        be doing something.

        WARNING: this test is known to fail occasionally, but tends to pass most of the time. I'm
        not certain whether this actually poses a problem.
        '''

        # Use a different mock 'tex' compiler here. It waits 1.2 seconds collectively, more
        # than the timeout value, but with intervening output to 'keep it alive'.
        self.mock_tex_command.write_text(dedent('''
            import pathlib, sys, time
            time.sleep(0.4)
            print('keepalive output')
            time.sleep(0.4)
            print('keepalive output')
            time.sleep(0.4)
            print('keepalive output')
            pathlib.Path(sys.argv[2]).write_text('mock PDF content')
        '''))

        # Ensures that the mock compiler doesn't buffer its output.
        os.environ["PYTHONUNBUFFERED"] = "1"

        self.run_markdown(
            r'''
            \begin{document}
                Latex code
            \end{document}
            ''',
            expect_error = True,
            timeout = 0.5
        )
        assert_that(
            self.progress.error_messages,
            empty())


    def test_tex_command_failure(self):

        def md(**kwargs):
            self.run_markdown(
                r'''
                \begin{document}
                \end{document}
                ''',
                expect_error = True,
                **kwargs)

        # Basic tex command failure
        self.mock_tex_command.write_text('import sys ; sys.exit(1)')
        md()
        assert_that(
            self.progress.error_messages,
            contains_exactly(has_properties({
                'location': 'la.latex',
                'msg': contains_string('returned error code 1'),
                'output': '',
            })))

        for verbose_errors, excl_matcher in [
            (False, not_(contains_string('excluded'))),
            (True,  contains_string('excluded'))
        ]:

            # With error message
            self.mock_tex_command.write_text(dedent('''
                import sys
                print("excluded")
                print("! mock error message")
                print("included")
                sys.exit(1)
            '''))
            md(verbose_errors = verbose_errors)
            assert_that(
                self.progress.error_messages,
                # contains_exactly(has_property('msg', contains_string('mock error message'))))
                contains_exactly(has_properties({
                    'location': 'la.latex',
                    'msg': contains_string('mock error message'),
                    'output': all_of(
                        excl_matcher,
                        contains_string('included'))
                })))

            # With error message and line number
            self.mock_tex_command.write_text(dedent('''
                import sys
                print("excluded")
                print("! mock error message")
                print("included")
                print("l.99")
                sys.exit(1)
            '''))
            md(verbose_errors = verbose_errors)
            assert_that(
                self.progress.error_messages,
                # contains_exactly(has_property('msg', contains_string('mock error message'))))
                contains_exactly(has_properties({
                    'location': 'la.latex',
                    'msg': contains_string('mock error message'),
                    'output': all_of(
                        excl_matcher,
                        contains_string('included')),
                    'highlight_lines': {98, 99}
                })))


    def test_tex_command_output_failure(self):
        '''Checks that an error is produced if the Tex command fails to output a .pdf file.'''

        # Our mock 'tex' compiler can be trivial in this case
        self.mock_tex_command.write_text('\n')

        self.run_markdown(
            r'''
            \begin{document}
                Latex code
            \end{document}
            ''',
            expect_error = True,
        )

        assert_that(
            self.progress.error_messages,
            contains_exactly(has_property('location', 'la.latex')))


    def test_pdf_command_output_failure(self):
        '''Checks that an error is produced if the Tex command fails to output a .pdf file.'''

        # Our mock 'tex' compiler can be trivial in this case
        self.mock_tex_command.write_text('\n')

        self.run_markdown(
            r'''
            \begin{document}
                Latex code
            \end{document}
            ''',
            expect_error = True,
        )

        assert_that(
            self.progress.error_messages,
            contains_exactly(has_property('location', 'la.latex')))


    def test_svg_command_output_failure(self):
        '''Checks that an error is produced if the pdf2svg command fails to output an .svg file,
        or the viewBox attribute is missing or zero-sized.'''


        for mock_svg_code in [
            '\n',

            r'''
            import pathlib, sys
            pathlib.Path(sys.argv[2]).write_text('<svg></svg>')
            ''',

            r'''
            import pathlib, sys
            pathlib.Path(sys.argv[2]).write_text('<svg viewBox="0 0 0 0"></svg>')
            '''
        ]:
            self.mock_pdf2svg_command.write_text(dedent(mock_svg_code))
            self.run_markdown(
                r'''
                \begin{document}
                    Latex code
                \end{document}
                ''',
                expect_error = True,
            )

            assert_that(
                self.progress.error_messages,
                contains_exactly(has_property('location', 'la.latex')))


    def test_duplication(self):
        '''
        With the 'toc' extension (and possibly in other circumstances), Markdown postprocessors are
        called multiple times. We want to ensure that the Tex command _isn't_, as this would be a
        significant drag on performance.
        '''

        mock_cache = MockCache(store = False)

        self.run_markdown(
            r'''
            \begin{document}
                Latex code
            \end{document}
            ''',
            extra_extensions = ['toc'],
            cache = mock_cache
        )

        self.assertFalse(Path(f'{self.tex_file}1').exists(),
                         f'Second output file {self.tex_file}1 shouldn\'t be generated')
        self.assertEqual(len(mock_cache.set_calls), 1, 'Number of times cache.set() was called')



    def test_math_ignored(self):
        html = self.run_markdown(
            r'''
            Text1 $math$ Text2

            Text1 $$math$$ Text2
            ''',
            math = 'ignore')

        root = lxml.html.fromstring(html)

        assert_that(
            root.xpath('//math | //svg | //img'),
            empty())

        self.assertFalse(self.tex_file.exists())


    def test_math_escaped(self):
        for input_text,          expected_output in [
            (r'\$math$',         r'$math$'),
            (r'\\\$math$',       r'\$math$'),
            (r'\\\\\\\\\$math$', r'\\\\$math$'),
            (r'\$x\\\$y\\\\\$z', r'$x\$y\\$z'),
        ]:
            html = self.run_markdown(
                f'Text1{input_text}Text2',
                math = 'mathml')

            root = lxml.html.fromstring(html)
            assert_that(
                root.xpath('//math | //svg | //img'),
                empty())

            assert_that(
                html,
                contains_string(f'Text1{expected_output}Text2'))

            self.assertFalse(self.tex_file.exists())


    def test_math_attr(self):
        for math in ['latex', 'mathml']:
            for embedding in ['data_uri', 'svg_element']:
                html = self.run_markdown(
                    r'''
                    Text1 $math${.test-class #test-id test-attr="test-value"} Text2

                    Text1 $$math$${test-attr="test-value" .test-class #test-id} Text2
                    ''',
                    math = math,
                    embedding = embedding)

                for element in lxml.html.fromstring(html).xpath('//math | //svg | //img'):
                    assert_that(
                        element.attrib,
                        has_entries({'id': 'test-id',
                                     'class': 'test-class',
                                     'test-attr': 'test-value'}))


    def test_math_corner_cases(self):
        for inp in ['$x$', '$$x$$', '$x$$', '$$x$', ' $x$ ', ' $$x$$ ', 'x$y$z', 'x$$y$$z',
                    'x$y$', '$x$y']:
            assert_that(
                lxml.html.fromstring(self.run_markdown(inp)).xpath('//math | //svg | //img'),
                contains_exactly(not_none()))

        for inp in ['$', '$$', ' $$ ', ' x$$y ', '$$$', '$$$$', '$$$$$',
                    '$x', 'x$', '$$x', 'x$$', ' x$ ', ' $x ', '$xy']:
            assert_that(
                lxml.html.fromstring(self.run_markdown(inp)).xpath('//math | //svg | //img'),
                empty())


    def test_math_inline_latex(self):

        for embedding, tag in [
            ('data_uri', 'img'),
            ('svg_element', 'svg'),
        ]:
            html1 = self.run_markdown(
                r'''
                Text1 $inline-math0$

                $inline-math1$ Text2

                Text1 $inline-math2$ Text2
                ''',
                math = 'latex',
                embedding = embedding)

            assert_that(
                lxml.html.fromstring(html1).xpath(f'count(//{tag})'),
                is_(3))

            for index in [0, 1, 2]:
                self.assert_tex_regex(
                    fr'''(?x)
                    \s* \\begin \{{document\}}
                    \s* \$inline-math{index}\$
                    \s* \\end \{{document\}}
                    ''',
                    file_index = index
                )

            html2 = self.run_markdown(
                r'''
                Text1 $ inline-math3$ Text2

                Text1 $inline-math4 $ Text2

                Text1 $
                inline-math5$ Text2

                Text1 $inline-math6
                $ Text2
                ''',
                math = 'latex',
                embedding = embedding)

            assert_that(
                lxml.html.fromstring(html2).xpath(f'//{tag}'),
                empty())


    def test_math_block_latex(self):

        for embedding, tag in [
            ('data_uri', 'img'),
            ('svg_element', 'svg'),
        ]:
            html = self.run_markdown(
                r'''
                Text1 $$block-math0$$

                $$block-math1$$ Text2

                Text1 $$block-math2$$ Text2

                Text1 $$ block-math3$$ Text2

                Text1 $$block-math4 $$ Text2

                Text1 $$
                block-math5$$ Text2

                Text1 $$block-math6
                $$ Text2
                ''',
                math = 'latex',
                embedding = embedding)

            assert_that(
                lxml.html.fromstring(html).xpath(f'count(//{tag})'),
                is_(7))

            for index in [0, 1, 2, 3, 4, 5, 6]:
                self.assert_tex_regex(
                    fr'''(?x)
                    \s* \\begin \{{document\}}
                    \s* \$\\displaystyle ({{}} | \s) \s* block-math{index} \s* \$
                    \s* \\end \{{document\}}
                    ''',
                    file_index = index
                )


    @patch('latex2mathml.converter.convert',
           lambda latex, display = 'inline': f'<math>{latex}-{display}</math>')
    def test_math_mathml(self):

        html = self.run_markdown(
            r'''
            Text1 $math0$

            $math1$ Text2

            Text1 $math2$ Text2

            Text1 $$math3$$

            $$math4$$ Text2

            Text1 $$math5$$ Text2
            ''',
            math = 'mathml')

        assert_that(
            lxml.html.fromstring(html).xpath('//math/text()'),
            contains_exactly('math0-inline', 'math1-inline', 'math2-inline',
                             'math3-block', 'math4-block', 'math5-block'))

        self.assertFalse(self.tex_file.exists())



    def test_dependency_recognition(self):

        home = Path.home()
        cwd = Path.cwd()

        with self.mock_tex_command.open('a') as writer:
            # Augment the mock tex compiler, getting it to also output a .fls file (which the
            # standard xetex/pdftex would do with the -recorder flag).

            writer.write(dedent(rf'''
                from pathlib import *
                from textwrap import dedent
                cwd = {repr(cwd)}
            '''))

            writer.write(dedent(r'''
                home = Path.home()
                outside_home = home.parent

                Path(sys.argv[2][:-4] + '.fls').write_text(dedent(f"""
                    INPUT { Path('.') / 'local-pkg1.sty'}
                    OUTPUT {Path('.') / 'local-pkg1a.sty'}
                    INPUT { Path('.') / 'dir1' / 'local-pkg2.sty'}
                    OUTPUT {Path('.') / 'dir1' / 'local-pkg2a.sty'}
                    INPUT { cwd / 'local-pkg3.sty'}
                    OUTPUT {cwd / 'local-pkg3a.sty'}
                    INPUT { cwd / 'dir2' / 'local-pkg4.sty'}
                    OUTPUT {cwd / 'dir2' / 'local-pkg4a.sty'}
                    INPUT { home / 'local-pkg5.sty'}
                    OUTPUT {home / 'local-pkg5a.sty'}
                    INPUT { home / 'dir3' / 'local-pkg6.sty'}
                    OUTPUT {home / 'dir3' / 'local-pkg6a.sty'}
                    INPUT { outside_home / 'local-pkgX.sty'}
                    OUTPUT {outside_home / 'local-pkgX.sty'}
                    INPUT { outside_home / 'dirX' / 'local-pkgX.sty'}
                    OUTPUT {outside_home / 'dirX' / 'local-pkgX.sty'}
                """))
            '''))

        live_update_deps = set()
        _ = self.run_markdown(
            r'''
            \begin{document}
            \end{document}
            ''',
            live_update_deps = live_update_deps
        )

        assert_that(
            live_update_deps,
            contains_inanyorder(
                cwd / 'local-pkg1.sty',
                cwd / 'dir1' / 'local-pkg2.sty',
                cwd / 'local-pkg3.sty',
                cwd / 'dir2' / 'local-pkg4.sty',
                home / 'local-pkg5.sty',
                home / 'dir3' / 'local-pkg6.sty',
            )
        )
        assert_that(len(live_update_deps), is_(6))


    def test_dependency_changes(self):
        '''Does recompiling happen when a dependency file changes?'''

        cache = {}
        live_update_deps = set()
        dependency_file = self.tmp_dir / 'dep-file.sty'
        flag_file       = self.tmp_dir / 'flag-file.txt'

        with self.mock_tex_command.open('a') as f:
            f.write(
                f'Path(sys.argv[2]).with_suffix(".fls").write_text("INPUT {dependency_file}")\n')

        dependency_file.write_text('1')

        # The dependency file must be in the current directory (or, theoretically, the home dir),
        # or else it won't be considered.
        orig_cwd = Path.cwd()
        os.chdir(self.tmp_dir)

        self.run_markdown(
            r'''
            \begin{document}
            \end{document}
            ''',
            cache = cache,
            live_update_deps = live_update_deps
        )

        # Amend the mock compiler so that it creates 'flag_file' when run, so that we know _if_
        # it's been run again.
        with self.mock_tex_command.open('a') as f:
            f.write(f'Path("{flag_file}").write_text("1")\n')

        self.run_markdown(
            r'''
            \begin{document}
            \end{document}
            ''',
            cache = cache,
            live_update_deps = live_update_deps
        )

        self.assertFalse(flag_file.exists(),
                         'Tex should _not_ be re-run if the dependency file does not change')

        dependency_file.write_text('2')
        self.run_markdown(
            r'''
            \begin{document}
            \end{document}
            ''',
            cache = cache,
            live_update_deps = live_update_deps
        )

        self.assertTrue(flag_file.exists(),
                        'Tex _should_ be re-run when the dependency file changes')

        os.chdir(orig_cwd)


    def test_extension_setup(self):
        assert_that(
            entry_point_cls('la.latex'),
            same_instance(lamarkdown.ext.latex.LatexExtension))

        instance = lamarkdown.ext.latex.makeExtension(prepend = 'mock_tex_code')

        assert_that(
            instance,
            instance_of(lamarkdown.ext.latex.LatexExtension))

        assert_that(
            instance.getConfig('prepend'),
            is_('mock_tex_code'))

        class MockBuildParams:
            def __getattr__(self, name):
                raise ModuleNotFoundError

        with patch('lamarkdown.lib.build_params.BuildParams', MockBuildParams()):
            instance = lamarkdown.ext.latex.makeExtension()
