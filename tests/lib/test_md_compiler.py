from ..util.mock_progress import MockProgress
from ..util.mock_cache import MockCache
from lamarkdown.lib import md_compiler, build_params, directives

import unittest
from unittest.mock import patch
from hamcrest import (assert_that, contains_exactly, contains_string, empty,
                      equal_to_ignoring_whitespace, has_entries, has_items, instance_of, is_,
                      is_not, matches_regexp, not_, only_contains, same_instance)

import lxml
import cssutils

import base64
import collections
import mimetypes
import os
from pathlib import Path
import tempfile
from textwrap import dedent

# TODO: also test these API properties:
# - css_vars
# - build_dir
# - env
# - params


class MdCompilerTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cssutils.log.setLevel('CRITICAL')

    def setUp(self):
        self.tmp_dir_context = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp_dir_context.__enter__())
        self.html_file = self.tmp_dir / 'testdoc.html'
        self.orig_dir = Path.cwd()
        os.chdir(self.tmp_dir)

        self.css_parser = cssutils.CSSParser(
            parseComments = False,
            validate = True
        )


    def tearDown(self):
        self.tmp_dir_context.__exit__(None, None, None)
        os.chdir(self.orig_dir)


    def set_results(self, html_file: Path, html_parser):
        # Parse with lxml to ensure that the output is well formed, and to allow it to be queried
        # with XPath expressions.
        self.root = lxml.html.parse(html_file, html_parser)

        # Now find and parse the CSS code, if any:
        self.css_sheets = [self.css_parser.parseString(t)
                           for t in self.root.xpath('/html/head/style/text()')]

        self.full_html = lxml.html.tostring(self.root, with_tail = False, encoding = 'unicode')

        # We probably want to just check the whole <body> element at once though.
        self.body_html = lxml.html.tostring(self.root.find('body'),
                                            with_tail = False,
                                            encoding = 'unicode')


    def run_md_compiler(self,
                        markdown = '',
                        build = None,
                        build_defaults = True,
                        is_live = False,
                        recover = False):

        doc_file   = self.tmp_dir / 'testdoc.md'
        build_file = self.tmp_dir / 'testbuild.py'
        build_dir  = self.tmp_dir / 'build'

        doc_file.write_text(dedent(markdown))
        if build is not None:
            build_file.write_text(dedent(build))

        build_files = [build_file] if build else []
        build_cache = MockCache()
        fetch_cache = MockCache()
        progress = MockProgress()

        bp = build_params.BuildParams(
            src_file            = doc_file,
            target_file         = self.html_file,
            build_files         = build_files,
            build_dir           = build_dir,
            build_defaults      = build_defaults,
            build_cache         = build_cache,
            fetch_cache         = fetch_cache,
            progress            = progress,
            directives          = directives.Directives(progress),
            is_live             = is_live,
            allow_exec_cmdline  = False
        )

        self.build_params = md_compiler.compile(bp)

        assert_that(
            self.build_params,
            has_items(is_not(same_instance(bp))),
            'build_params'
        )
        assert_that(
            self.build_params,
            has_items(instance_of(build_params.BuildParams)),
            'build_params'
        )

        for prop, value in {
            'src_file':             doc_file,
            'target_file':          self.html_file,
            'build_files':          build_files,
            'build_dir':            build_dir,
            'build_defaults':       build_defaults,
            'build_cache':          build_cache,
            'fetch_cache':          fetch_cache,
            'progress':             progress,
            'is_live':              is_live,
            'allow_exec_cmdline':   False
        }.items():
            for i, bp in enumerate(self.build_params):
                assert_that(
                    bp.__dict__[prop],
                    is_(value),
                    f'build_params[{i}].{prop}'
                )

        self.set_results(
            self.html_file,
            lxml.html.HTMLParser(
                recover = recover,  # Accept (according to lxml/libxml) broken HTML?
                no_network = True,  # Don't load remote resources
            )
        )


    def test_basic(self):
        self.run_md_compiler(
            r'''
            # Heading

            Paragraph1
            ''',
            build_defaults = False)

        # The meta charset declaration should be there as a matter of course.
        assert_that(
            self.root.xpath('count(/html/head/meta[@charset="utf-8"])'),
            is_(1))

        # The title should be taken from the <h1> element.
        assert_that(
            self.root.xpath('/html/head/title/text()'),
            contains_exactly('Heading'))

        # Check the document structure.
        assert_that(
            self.body_html,
            matches_regexp(
                r'''(?x)
                \s* <body>
                \s* <h1> Heading </h1>
                \s* <p> Paragraph1 </p>
                \s* </body>
                \s*
                '''
            )
        )



    @patch('lamarkdown.lib.resources.read_url')
    def test_basic_defaults(self, mock_read_url):
        """
        This innocuous-seeming code is more integration test than unit test. Since it includes the
        build defaults (unlike the bare-bones test_basic()), it indirectly invokes quite a lot of
        Lamarkdown.
        """
        mock_read_url.side_effect = lambda url, *a, **k: (False,
                                                          b'mock content',
                                                          mimetypes.guess_type(url))
        self.run_md_compiler(
            r'''
            # Heading

            Paragraph1
            ''')

        assert_that(
            self.root.xpath('//h1/text()'),
            contains_exactly('Heading'))

        assert_that(
            self.root.xpath('//p/text()'),
            contains_exactly('Paragraph1'))


    def test_title(self):
        build = r'''
            import lamarkdown as la
            la('meta')
        '''

        # Ways of unambiguously specifying a title
        for md in [
            'title: The Title\n# False Title',
            '# The Title\n## False Title',
            '## The Title\n### False Title',
            '### The Title\n#### False Title',
            '#### The Title\n##### False Title',
            '##### The Title\n###### False Title',
            '###### The Title',
        ]:
            self.run_md_compiler(md, build = build, build_defaults = False)
            assert_that(
                self.root.xpath('/html/head/title/text()'),
                contains_exactly('The Title'))

        # Cases resulting in a default title (due to omission or ambiguity)
        for md in [
            '',
            'Some text',
            '# Title 1\n# Title 2',
            '## Title 1\n## Title 2',
            '### Title 1\n### Title 2',
            '#### Title 1\n#### Title 2',
            '##### Title 1\n##### Title 2',
            '###### Title 1\n###### Title 2',
        ]:
            self.run_md_compiler(md, build = build, build_defaults = False)
            assert_that(
                self.root.xpath('/html/head/title/text()'),
                contains_exactly('testdoc'))

        # Cases resulting in title suppression
        for md in [
            'title: \n# False Title',
            '#\n## False Title',
            '##\n### False Title',
            '###\n#### False Title',
            '####\n##### False Title',
            '#####\n###### False Title',
            '######'
        ]:
            self.run_md_compiler(md, build = build, build_defaults = False)
            assert_that(
                self.root.xpath('/html/head/title'),
                empty())



    def test_css(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading

                Paragraph1
                ''',
            build = r'''
                import lamarkdown as la
                la.css(r"h1 { background: blue; font-weight: bold; }")
                la.css(r"h2 { background: green; }")

                # Testing selectors: 'h3' should not match (there's no '### Sub-sub-heading' in the
                # markdown document), but 'h1' should. Note: we're testing the 'if_selector'
                # parameter. The 'h3' at the start of the CSS is irrelevant to our test.

                la.css(r"h3 { background: yellow; }",  if_selectors = ["h3"])
                la.css(r"h3 { background: yellow; }",  if_selectors = "h3")
                la.css(r"h3 { background: magenta; }", if_selectors = ["h3", "h1"])

                # Testing XPaths: "//h5" should not match, but "//h1" should.

                la.css(r"h4 { background: yellow; }",  if_xpaths = ["//h5"])
                la.css(r"h4 { background: yellow; }",  if_xpaths = "//h5")
                la.css(r"h4 { background: orange; }",  if_xpaths = ["//h5", "//h1"])

                # Testing rule creation with pre-selected selectors. "li" and "span" don't match,
                # but "p" does.

                la.css_rule(["li", "p", "span"], r"color: red")

                # Testing that comments get stripped, but not strings containing comment syntax.

                la.css("""
                    /* a\nbc */ .xyz { /*d\nef*/
                        /*mno*/ font-family: "/* pqr */" /*stu*/
                    } /*v\nwx*/
                    /*yz*/
                """)
                ''',
            build_defaults = False
        )

        expected_css = self.css_parser.parseString(
            r'''
            h1 {
                background: blue;
                font-weight: bold;
            }
            h2 { background: green; }
            h3 { background: magenta; }
            h4 { background: orange; }
            p {
                color: red;
            }
            .xyz {
                font-family: "/* pqr */";
            }
            ''')

        assert_that(
            [s.cssText for s in self.css_sheets],
            contains_exactly(expected_css.cssText)
        )

        assert_that(
            self.root.xpath('/html/head/style/text()')[0],
            is_not(matches_regexp(r'[^"]/\*|\*/[^"]'))
        )


    def test_js(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading

                Paragraph1
                ''',
            build = r'''
                import lamarkdown as la
                la.js(r"console.log('a')")
                la.js(r"console.log('b')")
                la.js(r"console.log('c')", if_selectors = ["h3"])
                la.js(r"console.log('d')", if_selectors = ["h3", "h1"])
                la.js(r"console.log('e')", if_xpaths = "//h5")
                la.js(r"console.log('f')", if_xpaths = ["//h5", "//h1"])
                ''',
            build_defaults = False
        )

        expected_js = dedent(r'''
            console.log('a')
            console.log('b')
            console.log('d')
            console.log('f')
        ''')

        assert_that(
            self.root.xpath('/html/body/script/text()')[0].strip(),
            is_(expected_js.strip()))


    def test_css_js_files(self):

        # Create mock .css and .js files. Lamarkdown *might* check that these exist, but it
        # shouldn't matter what they contain.
        (self.tmp_dir / 'cssfile.css').write_text('')
        (self.tmp_dir / 'jsfile.js').write_text('')

        for code in [
            # Ensure that stylesheets and scripts are not embedded.
            'la.embed(False)',
            'la.embed(lambda url, **k: not (url and (url.endswith("css") or url.endswith("js"))))',
            'la.embed(lambda mime, **k: mime not in ["text/css", "application/javascript"])',
            'la.embed(lambda tag,  **k: tag not in ["style", "script"])'
        ]:
            self.run_md_compiler(
                markdown = r'''
                    # Heading

                    Paragraph1
                    ''',
                build = fr'''
                    import lamarkdown as la
                    {code}
                    la.css_files("cssfile.css")
                    la.js_files("jsfile.js")
                    ''',
                build_defaults = False
            )

            # Assert that the <link rel="stylesheet" href="..."> element exists.
            assert_that(
                self.root.xpath('count(/html/head/link[@rel="stylesheet"][@href="cssfile.css"])'),
                is_(1))

            # Assert that the <script src="..."> element exists, and that it comes after <p>.
            assert_that(
                self.root.xpath('count(/html/body/p/following-sibling::script[@src="jsfile.js"])'),
                is_(1))


    def test_css_js_files_embedded(self):

        # Create mock .css and .js files. We're embedding them, so their contents do matter here.
        (self.tmp_dir / 'cssfile.css').write_text(
            '/*abc\ndef*/p{/*abc\ndef*/color:blue}/*abc\ndef*/')

        (self.tmp_dir / 'jsfile.js').write_text('console.log(1)')

        for code in [
            # Ensure that stylesheets and scripts _are_ embedded.
            '',
            'la.embed(True)',
            'la.embed(lambda url,  **k: url and (url.endswith("css") or url.endswith("js")))',
            'la.embed(lambda mime, **k: mime in ["text/css", "application/javascript"])',
            'la.embed(lambda tag,  **k: tag in ["style", "script"])'
        ]:
            self.run_md_compiler(
                markdown = r'''
                    # Heading

                    Paragraph1
                    ''',
                build = fr'''
                    import lamarkdown as la
                    {code}
                    la.css_files("cssfile.css")
                    la.js_files("jsfile.js")
                    ''',
                build_defaults = False
            )

            # Assert that the <style>...</style> element exists, with the right content.
            assert_that(
                self.root.xpath('/html/head/style/text()'),
                only_contains(equal_to_ignoring_whitespace('p{color:blue}')))

            # Assert that the <script>...</script> element exists, with the right content.
            assert_that(
                self.root.xpath('/html/body/script/text()'),
                only_contains(equal_to_ignoring_whitespace('console.log(1)')))


    def test_element_embedding(self):

        # A trivially-small .gif and .wav file. We need to know the file content, because we'll be
        # checking for it (base64 encoded).

        gif_bytes = (b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00'
                     b'\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
        wav_bytes = (b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X'
                     b'\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')

        (self.tmp_dir / 'image.gif').write_bytes(gif_bytes)
        (self.tmp_dir / 'audio.wav').write_bytes(wav_bytes)

        for embed_spec in [
            'True',
            'lambda url,  **k: url and (url.endswith("gif") or url.endswith("wav"))',
            'lambda mime, **k: mime in ["image/gif", "audio/x-wav"]',
            'lambda tag,  **k: tag in ["img", "audio"]'
        ]:
            self.run_md_compiler(
                markdown = r'''
                    # Heading

                    ![Text](image.gif)
                    <audio src="audio.wav" type="audio/x-wav" />
                ''',
                build = rf'''
                    import lamarkdown as la
                    la.embed({embed_spec})
                ''',

                # lxml/libxml complains about <audio> (and other HTML 5 tags) being invalid. I'm not
                # sure whether/how it can be pursuaded to accept them, other than by turning on
                # 'recovery' of (supposedly) broken HTML.
                recover = True
            )

            assert_that(
                self.root.xpath('//img/@src'),
                only_contains(f'data:image/gif;base64,{base64.b64encode(gif_bytes).decode()}'))

            assert_that(
                self.root.xpath('//audio/@src'),
                only_contains(f'data:audio/x-wav;base64,{base64.b64encode(wav_bytes).decode()}'))


    @patch('lamarkdown.lib.resources.read_url')
    def test_element_non_embedding(self, mock_read_url):
        mock_read_url.return_value = (False, b'', None)

        for embed_spec in [
            'False',
            'lambda url,  **k: not (url and (url.endswith("gif") or url.endswith("wav")))',
            'lambda mime, **k: mime not in ["image/gif", "audio/x-wav"]',
            'lambda tag,  **k: tag not in ["img", "audio"]'
        ]:
            self.run_md_compiler(
                markdown = r'''
                    # Heading

                    ![Text](image.gif)
                    <audio src="audio.wav" type="audio/x-wav" />
                ''',
                build = rf'''
                    import lamarkdown as la
                    la.embed({embed_spec})
                ''',

                # lxml/libxml complains about <audio> (and other HTML 5 tags) being invalid. I'm not
                # sure whether/how it can be pursuaded to accept them, other than by turning on
                # 'recovery' of (supposedly) broken HTML.
                recover = True
            )

            assert_that(
                self.root.xpath('//img/@src'),
                only_contains('image.gif'))

            assert_that(
                self.root.xpath('//audio/@src'),
                only_contains('audio.wav'))


    @patch('lamarkdown.lib.resources.read_url')
    def test_image_scaling(self, mock_read_url):
        mock_read_url.return_value = (False, b'', 'image/png')

        for tag,       suffix in [
            ('svg',    '><g></g></svg>'),
            ('img',    ' src="dummy.png">'),
            ('source', ' src="dummy.png">')
        ]:
            self.run_md_compiler(
                markdown = rf'''
                    # Heading
                    <{tag} id="a" width="10" height="15"{suffix}
                    <{tag} id="b" width="10" height="15" size="3"{suffix}
                    <{tag} id="c" width="10" height="15" md-scale="5"{suffix}
                    <{tag} id="d" width="10" height="15" size="3" md-scale="5"{suffix}
                ''',
                build = r'''
                    import lamarkdown as la
                    la.scale(lambda attr={}, **k: float(attr["size"]) if "size" in attr else 2)
                ''',
                recover = True  # Apparently lxml/libxml doesn't like the <svg> tag?
            )

            # <{tag} id="a">: scale by 2
            assert_that(self.root.xpath(f'//{tag}[@id="a"]/@width'),  contains_exactly('20'))
            assert_that(self.root.xpath(f'//{tag}[@id="a"]/@height'), contains_exactly('30'))

            # <{tag} id="b">: scale by 3
            assert_that(self.root.xpath(f'//{tag}[@id="b"]/@width'),  contains_exactly('30'))
            assert_that(self.root.xpath(f'//{tag}[@id="b"]/@height'), contains_exactly('45'))

            # <{tag} id="c">: scale by 2*5
            assert_that(self.root.xpath(f'//{tag}[@id="c"]/@width'),  contains_exactly('100'))
            assert_that(self.root.xpath(f'//{tag}[@id="c"]/@height'), contains_exactly('150'))

            # <{tag} id="d">: scale by 3*5
            assert_that(self.root.xpath(f'//{tag}[@id="d"]/@width'),  contains_exactly('150'))
            assert_that(self.root.xpath(f'//{tag}[@id="d"]/@height'), contains_exactly('225'))


    def test_disentangle_svgs(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading
                <svg><defs><g id="alpha" /><g id="beta" /></svg>
                <svg><defs><g id="alpha" /><g id="beta" /></svg>
            ''',
            build_defaults = False,
            recover = True  # Apparently lxml/libxml doesn't like the <svg> tag?
        )

        new_ids = collections.Counter(self.root.xpath('//@id'))
        assert_that(new_ids, has_entries({id: 1 for id in new_ids}))


    def test_variants(self):
        '''Checks whether we can compile variant documents, and in particular tests these API
        functions: variants(), base_name(), name(), target() and prune().'''

        self.run_md_compiler(
            markdown = r'''
                # Heading

                Paragraph1

                Paragraph2
                ''',
            build = r'''
                import lamarkdown as la
                def variant_a():
                    la.base_name()

                def variant_b():
                    la.name = "variant_b1"

                def variant_c():
                    la.target(lambda original: f"{original}.variant_c1.html")

                def variant_d():
                    def d1():
                        la.css(r"h1 { color: red; }")

                    def d2():
                        la.css(r"h1 { color: blue; }")

                    la.variants(d1, d2)
                    la.css(r"h1 { color: red; }")

                def variant_e():
                    la.prune("p")

                def variant_f():
                    la.prune("h1")

                la.variants(variant_a, variant_b, variant_c, variant_d, variant_e, variant_f)
            ''',
            build_defaults = False
        )

        def for_(f):
            self.set_results(
                self.tmp_dir / (f + '.html'),
                lxml.html.HTMLParser(recover = False, no_network = True)
            )

        def exists():
            assert_that(
                self.root.xpath('/html/body/h1/text()'), contains_exactly('Heading'))

        # Check variant A, which should have the default name.
        exists()

        # Check variant B, where we pick a custom variant name (target suffix).
        for_('testdoc_variant_b1')
        exists()

        # Check variant C, where we pick a different target name, based on the original name,
        # using a function.
        for_('testdoc.html.variant_c1')
        exists()

        # Check sub-variants D1 and D2:
        for_('testdoc_variant_d_d1')
        assert_that(self.css_sheets[0].cssText.decode(), contains_string('color: red'))

        for_('testdoc_variant_d_d2')
        assert_that(self.css_sheets[0].cssText.decode(), contains_string('color: blue'))

        # Check variant E, which should be missing its 'p' elements:
        for_('testdoc_variant_e')
        assert_that(self.root.xpath('/html/body/h1'), not_(empty()))
        assert_that(self.root.xpath('/html/body/p'),  is_(empty()))

        # Check variant F, which should be missing its 'h1' element:
        for_('testdoc_variant_f')
        assert_that(self.root.xpath('/html/body/h1'), is_(empty()))
        assert_that(self.root.xpath('/html/body/p'),  not_(empty()))


    def test_tree_hooks(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading1

                Paragraph1

                # Heading2

                Paragraph2
                ''',
            build = r'''
                import lamarkdown as la
                import lxml.etree

                def for_each_h1(element):
                    element.text += " h1"

                def for_each_p(element):
                    element.text += " p"

                def add_sub_element(root):
                    lxml.etree.SubElement(root, "div", attrib={"id": "child"})

                def add_parent_element(root):
                    new_root = lxml.etree.Element("div", attrib={"id": "parent"})
                    new_root.extend(root)
                    return new_root

                la.with_selector("h1", for_each_h1)
                la.with_xpath("//p", for_each_p)
                la.with_tree(add_sub_element)
                la.with_tree(add_parent_element)
            ''',
            build_defaults = False
        )

        assert_that(
            self.root.xpath('//h1/text()'),
            contains_exactly('Heading1 h1', 'Heading2 h1'))

        assert_that(
            self.root.xpath('//p/text()'),
            contains_exactly('Paragraph1 p', 'Paragraph2 p'))

        assert_that(
            self.root.xpath('count(//div[@id="parent"]/div[@id="child"])'),
            is_(1))


    def test_html_hooks(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading

                Paragraph
                ''',
            build = r'''
                import lamarkdown as la
                la.with_html(lambda html: f'<div id="parent">{html}</div>')
            ''',
            build_defaults = False
        )

        assert_that(
            self.root.xpath('''count(/html/body/div[@id="parent"]
                                                   [h1="Heading"]
                                                   [p="Paragraph"])'''),
            is_(1))


    def test_extensions(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading {#testid}

                Paragraph PARA

                *[PARA]: description
                ''',
            build = r'''
                import lamarkdown as la
                la('abbr', 'attr_list')
            ''',
            build_defaults = False
        )

        # Check the document structure.
        assert_that(
            self.body_html,
            matches_regexp(
                r'''(?x)
                \s* <body>
                \s* <h1[ ]id="testid"> Heading </h1>
                \s* <p> Paragraph \s* <abbr[ ]title="description"> PARA </abbr> </p>
                \s* </body>
                \s*
                '''
            )
        )


    def test_extension_config(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading...

                "Paragraph" --- <<Text>>
                ''',
            build = r'''
                import lamarkdown as la
                cfg = la('smarty', smart_dashes = True, smart_quotes = False)
                cfg['smart_angled_quotes'] = True
                cfg['smart_ellipses'] = False
            ''',
            build_defaults = False
        )

        assert_that(
            self.body_html,
            matches_regexp(
                r'''(?x)
                \s* <body>
                \s* <h1> Heading... </h1>
                \s* <p> "Paragraph" [ ] (&mdash;|—) [ ] (&laquo;|«) Text (&raquo;|») </p>
                \s* </body>
                \s*
                '''
            )
        )


    def test_extension_object(self):
        self.run_md_compiler(
            markdown = r'''
                # Heading

                Paragraph
                ''',
            build = r'''
                import lamarkdown as la
                import markdown

                class TestPostprocessor(markdown.postprocessors.Postprocessor):
                    def run(self, text):
                        return text + '<div>Extension</div>'

                class TestExtension(markdown.Extension):
                    def extendMarkdown(self, md):
                        md.postprocessors.register(TestPostprocessor(), 'test-proc', 25)

                la(TestExtension())
            ''',
            build_defaults = False
        )

        assert_that(
            self.root.xpath('//div/text()')[0],
            is_('Extension'))


    def test_multiple_input_files(self):
        src_file_list    = [self.tmp_dir / 'testdoc1.md',
                            self.tmp_dir / 'testdoc2.md',
                            self.tmp_dir / 'testdoc3.md']
        target_file_list = [self.tmp_dir / 'testoutput1.html',
                            self.tmp_dir / 'testoutput2.html',
                            self.tmp_dir / 'testoutput3.html']
        build_file_list  = [[self.tmp_dir / 'testbuildA.py'],
                            [self.tmp_dir / 'testbuildB.py'],
                            [self.tmp_dir / 'testbuildC.py']]

        for src_file in src_file_list:
            src_file.write_text(f'Para 1 in {src_file.stem}')

        for build_files in build_file_list:
            build_files[0].write_text(dedent(f'''
                import lamarkdown as la
                la.with_html(lambda html: html + '<p>Para 2 inserted by {build_files[0].stem}</p>')
            '''))

        build_cache = MockCache()
        fetch_cache = MockCache()
        progress = MockProgress()
        direc = directives.Directives(progress)

        starting_build_params = [
            build_params.BuildParams(
                src_file            = src_file,
                target_file         = target_file,
                build_files         = build_files,
                build_dir           = self.tmp_dir / 'build',
                build_defaults      = True,
                build_cache         = build_cache,
                fetch_cache         = fetch_cache,
                progress            = progress,
                directives          = direc,
                is_live             = False,
                allow_exec_cmdline  = False
            )
            for (src_file, target_file, build_files) in zip(src_file_list,
                                                            target_file_list,
                                                            build_file_list)
        ]

        complete_build_params = md_compiler.compile_all(starting_build_params)

        assert_that(len(complete_build_params), is_(len(starting_build_params)))

        for (src_file, build_files, target_file, params) in zip(src_file_list,
                                                                build_file_list,
                                                                target_file_list,
                                                                complete_build_params):
            params_src_file = params[0].src_file
            params_build_files = params[0].build_files
            params_target_file = params[0].target_file

            assert_that(params_src_file, is_(src_file))
            assert_that(params_build_files, is_(build_files))
            assert_that(params_target_file, is_(target_file))

            html = params_target_file.read_text()
            assert_that(html,
                        contains_string(f'<p>Para 1 in {params_src_file.stem}</p>'))
            assert_that(html,
                        contains_string(f'<p>Para 2 inserted by {params_build_files[0].stem}</p>'))
