import unittest

import markdown
from lamarkdown.ext import sections

import re
from textwrap import dedent


class SectionsTestCase(unittest.TestCase):

    def run_markdown(self, markdown_text, **kwargs):
        md = markdown.Markdown(
            extensions = ['lamarkdown.ext.sections'],
            extension_configs = {'lamarkdown.ext.sections':
            {
                **kwargs
            }}
        )
        return md.convert(dedent(markdown_text).strip())


    def test_basic_syntax(self):
        '''Check some sections!'''

        html = self.run_markdown(
            r'''
            # Heading

            ---

            Paragraph1

            Paragraph2

            ---

            Paragraph3

            --

            ----

            ---

            ---

            Paragraph4
            ''')

        self.assertRegex(
            html,
            fr'''(?x)
            \s* <section>
            \s* <h1>Heading</h1>
            \s* </section>
            \s* <section>
            \s* <p>Paragraph1</p>
            \s* <p>Paragraph2</p>
            \s* </section>
            \s* <section>
            \s* <p>Paragraph3</p>
            \s* <p>--</p>
            \s* <hr\s*/?>
            \s* </section>
            \s* <section>
            \s* </section>
            \s* <section>
            \s* <p>Paragraph4</p>
            \s* </section>
            \s*
            '''
        )


    def test_false_positives(self):
        '''Section dividers are only recognised (for now) if they're separate blocks.'''
        html = self.run_markdown(
            r'''
            Paragraph1
            ---

            ---
            Paragraph2

            Paragraph3
            ---
            Paragraph4
            ''')

        self.assertNotIn('<section>', html)


    def test_attr(self):
        '''Check that we can assign attributes to <section> tags, and that an section separator at
        the very top is only used for this purpose (so there's no initial empty section).'''
        html = self.run_markdown(
            r'''
            ---
            {.class1 #id1 myattr="1"}

            Paragraph1

            ---
            {.class2 #id2 myattr="2"}

            Paragraph2
            ''')

        sections = re.findall('<section[^>]+>', html)

        self.assertEqual(2, len(sections))
        self.assertIn('class="class1"', sections[0])
        self.assertIn('id="id1"',       sections[0])
        self.assertIn('myattr="1"',     sections[0])
        self.assertIn('class="class2"', sections[1])
        self.assertIn('id="id2"',       sections[1])
        self.assertIn('myattr="2"',     sections[1])


    def test_alt_separators(self):

        for separator in ['(((', '----', 'CHANGE SECTIONS!']:
            html = self.run_markdown(
                f'''
                Paragraph1

                {separator}

                Paragraph2
                ''',
                separator = separator)

            self.assertRegex(
                html,
                fr'''(?x)
                \s* <section>
                \s* <p>Paragraph1</p>
                \s* </section>
                \s* <section>
                \s* <p>Paragraph2</p>
                \s* </section>
                ''')
