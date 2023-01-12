import unittest

import markdown
from lamarkdown.ext import eval

import datetime
import re
from textwrap import dedent
import xml.etree.ElementTree


class MockMsg:
    def as_dom_element(self, *a, **l):
        return xml.etree.ElementTree.Element('mock')

class MockProgress:
    def error(self, *a, **k):                return MockMsg()
    def error_from_exception(self, *a, **k): return MockMsg()


class EvalTestCase(unittest.TestCase):

    def run_markdown(self, markdown_text, **kwargs):
        md = markdown.Markdown(
            extensions = ['lamarkdown.ext.eval'],
            extension_configs = {'lamarkdown.ext.eval':
            {
                'progress': MockProgress(),
                **kwargs
            }}
        )
        return md.convert(dedent(markdown_text).strip())


    def test_date(self):
        html = self.run_markdown(
            r'''
            Sometext $`date` sometext
            ''')

        self.assertRegex(
            html,
            fr'''(?x)
            <p>Sometext[ ]
            <span>
            {re.escape(str(datetime.date.today())).replace(' ', '[ ]')}
            </span>
            [ ]sometext</p>
            '''
        )

    def test_custom_replacement(self):
        html = self.run_markdown(
            r'''
            Sometext $`xyz` sometext
            ''',
            replace = {'xyz': 'test replacement'}
        )

        self.assertRegex(
            html,
            fr'''(?x)
            <p>Sometext[ ]
            <span>
            test[ ]replacement
            </span>
            [ ]sometext</p>
            '''
        )


    def test_code_eval(self):
        html = self.run_markdown(
            r'''
            Sometext $`111+222` sometext
            ''',
            allow_code = True
        )

        self.assertRegex(
            html,
            fr'''(?x)
            <p>Sometext[ ]
            <span>
            333
            </span>
            [ ]sometext</p>
            '''
        )


    def test_code_eval_disabled(self):
        html = self.run_markdown(
            r'''
            Sometext $`111+222` sometext
            ''',
            allow_code = False
        )

        self.assertNotIn('333', html)


    def test_delimiter(self):
        html = self.run_markdown(
            r'''
            Sometext $```'triple delimiter'``` sometext
            ''',
            allow_code = True
        )

        self.assertIn('triple delimiter', html)


    def test_alt_delimiter(self):
        html = self.run_markdown(
            r'''
            Sometext #///'alt delimiter'///& sometext
            ''',
            allow_code = True,
            start = '#',
            end = '&',
            delimiter = '/'
        )

        self.assertIn('alt delimiter', html)
