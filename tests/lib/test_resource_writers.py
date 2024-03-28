from ..util.mock_progress import MockProgress
from lamarkdown.lib import resources, resource_writers

import unittest
from unittest.mock import patch, Mock, PropertyMock, ANY
from hamcrest import (assert_that, contains_exactly, contains_inanyorder, empty,
                      equal_to_ignoring_whitespace)

import base64
import os
from pathlib import Path
import tempfile
from xml.etree import ElementTree


# TODO:
# - handling of cycles in nested stylesheets


class ResourceWritersTestCase(unittest.TestCase):

    def setUp(self):
        self.orig_dir = Path.cwd()

    def tearDown(self):
        os.chdir(self.orig_dir)


    @patch('lamarkdown.lib.resources.read_url')
    def test_make_data_url(self, mock_read_url):

        b64_orig = 'bW9ja19jb250ZW50'  # base64 encoding of "mock_content"
        b64_converted = 'bW9ja19jb250ZW50X2NvbnZlcnRlZA=='  # b64 of "mock_content_converted"

        mock_build_params = Mock()
        converter = Mock()
        converter.return_value = (b'mock_content_converted', 'tx/CONV')

        for mime_arg,   mime_auto,  conv,      expected_data_url in [
            (None,      None,       None,      f'data:;base64,{b64_orig}'),
            (None,      None,       converter, f'data:tx/CONV;base64,{b64_converted}'),
            ('tx/Orig', None,       None,      f'data:tx/Orig;base64,{b64_orig}'),
            ('tx/Orig', None,       converter, f'data:tx/CONV;base64,{b64_converted}'),
            (None,      'tx/_auto', None,      f'data:tx/_auto;base64,{b64_orig}'),
            (None,      'tx/_auto', converter, f'data:tx/CONV;base64,{b64_converted}'),
            ('tx/Orig', 'tx/_auto', None,      f'data:tx/Orig;base64,{b64_orig}'),
            ('tx/Orig', 'tx/_auto', converter, f'data:tx/CONV;base64,{b64_converted}')
        ]:
            mock_read_url.return_value = (False, b'mock_content', mime_auto)
            actual_data_url = resource_writers.make_data_url('http://example.com/mock',
                                                             mime_arg,
                                                             mock_build_params,
                                                             *([] if conv is None else [conv]))
            self.assertEqual(expected_data_url, actual_data_url)


    @patch('lamarkdown.lib.resource_writers.make_data_url')
    def test_stylesheet_embed(self, mock_make_data_url):

        url = 'http://example.com/image.jpg'
        data_url = 'data:mock'

        mock_build_params = Mock()

        mock_make_data_url.return_value = data_url

        for input_css,                 base_url, embed,  exp_urls, expected_css in [
            ('',                       '',       [],     [],       ''),

            ('/* comment */',          '',       [],     [],       ''),
            (f'"url({url})"',          '',       [url],  [],       f'"url({url})"'),
            (f"'url({url})'",          '',       [url],  [],       f"'url({url})'"),
            # TODO: also test for whitespace removal/compaction.

            (f'url({url})',            '',       [url],  [url],    f'url("{data_url}")'),
            (f'url("{url}")',          '',       [url],  [url],    f'url("{data_url}")'),
            (f'src("{url}")',          '',       [url],  [url],    f'url("{data_url}")'),
            (f'url(  "{url}"   )',     '',       [url],  [url],    f'url("{data_url}")'),
            (f'@import"{url}";',       '',       [url],  [url],    f'@import "{data_url}";'),
            (f'@import   "{url}"  ;',  '',       [url],  [url],    f'@import "{data_url}"  ;'),
            (f'@import url("{url}");', '',       [url],  [url],    f'@import url("{data_url}");'),

            (f'url({url})',            '',       [],     [],       f'url("{url}")'),
            (f'@import"{url}";',       '',       [],     [],       f'@import "{url}";'),

            (f'url({url})',            'a/b/c/', [],     [],       f'url("{url}")'),
            (f'@import"{url}";',       'a/b/c',  [],     [],       f'@import "{url}";'),

            (f'url({url})',            'a/b/c/', [url],  [url],    f'url("{data_url}")'),
            (f'@import"{url}";',       'a/b/c',  [url],  [url],    f'@import "{data_url}";'),

            ('url(dir/file)',          'a/b/c/', [],     [],       'url("a/b/c/dir/file")'),
            ('@import"dir/file";',     'a/b/c',  [],     [],       '@import "a/b/dir/file";'),

            (
                r'''p{ x: "url(abc)"; /* url(def) */ y: url("ghi"); z: "url(jkl)"} /*url(mno) */''',
                '',
                ['ghi'],
                ['ghi'],
                rf'''p{{ x: "url(abc)"; y: url("{data_url}"); z: "url(jkl)"}}'''
            ),

            (
                r'''p{ x: url(abc) url(def); /*y: "url(ghi)";*/ z: url(jkl)}''',
                '',
                ['abc', 'def', 'jkl'],
                ['abc', 'def', 'jkl'],
                rf'''p{{ x: url("{data_url}") url("{data_url}"); z: url("{data_url}")}}'''
            ),

            (
                rf'''p{{ x: url(abc) url(def) url({url}) url({url}2) }}''',
                'a/b/c',
                ['a/b/def', url],
                ['a/b/def', url],
                rf'''p{{ x: url("a/b/abc") url("{data_url}") url("{data_url}") url("{url}2") }}'''
            ),

            # Special characters
            ('''url(\\\\\\x\\y\\z\\\\)''',
             '', ['\\xyz\\'], ['\\xyz\\'], fr'url("{data_url}")'),

            ('''url(\\69 \\06d\\0061\t\\00067\\000065 )''',
             '', ['image'], ['image'], fr'url("{data_url}")'),

            ('''url("\\"\\69 \\06d\\0061\t\\00067\\000065 \\"")''',
             '', ['"image"'], ['"image"'], fr'url("{data_url}")'),

            ('''url('\\'\\69 \\06d\\0061\t\\00067\\000065 \\'')''',
             '', ["'image'"], ["'image'"], fr'url("{data_url}")'),
        ]:
            def embed_rule(url, **k):
                return url in embed

            type(mock_build_params).embed_rule = PropertyMock(return_value = embed_rule)

            sw = resource_writers.StylesheetWriter(mock_build_params)
            output_css = sw._embed(base_url, input_css)

            msg = repr(dict(input_css=input_css, base_url=base_url,
                            embed=embed, expected_css=expected_css))

            # Ensure that make_data_url() is called correctly.
            self.assertEqual(len(exp_urls), mock_make_data_url.call_count, msg = msg)
            for url in exp_urls:
                mock_make_data_url.assert_any_call(url, ANY, mock_build_params, ANY)
            mock_make_data_url.reset_mock()

            self.assertEqual(expected_css, output_css, msg = msg)


    def test_stylesheet_writer(self):
        mock_build_params = Mock()
        type(mock_build_params).embed_rule = PropertyMock(return_value = lambda **k: False)
        type(mock_build_params).progress = PropertyMock(return_value = MockProgress())

        content1 = resources.ContentResource('p { color: blue }')
        content2 = resources.ContentResource('div { margin: 0 }')
        url1 = resources.UrlResource('dir/style.css', to_embed = False)
        url2 = resources.UrlResource('http://example.com/style.css', to_embed = False)

        sw = resource_writers.StylesheetWriter(mock_build_params)

        exp_content1 = f'<style>\n{content1.content}\n</style>'
        exp_content12 = f'<style>\n{content1.content}\n{content2.content}\n</style>'
        exp_url1 = f'<link rel="stylesheet" href="{url1.url}" />'
        exp_url2 = f'<link rel="stylesheet" href="{url2.url}" />'

        # Note: <link>s are supposed to come before <style> in the output

        for resource_list, expected in [
            ([content1],                       exp_content1),
            ([url1],                           exp_url1),
            ([content1, content2],             exp_content12),
            ([url1, url2],                     exp_url1 + exp_url2),
            ([url1, content1],                 exp_url1 + exp_content1),
            ([content1, url1],                 exp_url1 + exp_content1),
            ([content1, url1, content2, url2], exp_url1 + exp_url2 + exp_content12),
            ([url1, content1, content2, url2], exp_url1 + exp_url2 + exp_content12),
        ]:
            assert_that(
                sw.format(resource_list),
                equal_to_ignoring_whitespace(expected))


    def test_script_writer(self):
        mock_build_params = Mock()
        type(mock_build_params).embed_rule = PropertyMock(return_value = lambda **k: False)
        type(mock_build_params).progress = PropertyMock(return_value = MockProgress())

        content1 = resources.ContentResource('console.log("hello")')
        content2 = resources.ContentResource('console.log("world")')
        url1 = resources.UrlResource('dir/script.js', to_embed = False)
        url2 = resources.UrlResource('http://example.com/script.js', to_embed = False)

        sw = resource_writers.ScriptWriter(mock_build_params)

        exp_content1 = f'<script>\n{content1.content}\n</script>'
        exp_content2 = f'<script>\n{content2.content}\n</script>'
        exp_content12 = f'<script>\n{content1.content}\n{content2.content}\n</script>'
        exp_url1 = f'<script src="{url1.url}"></script>'
        exp_url2 = f'<script src="{url2.url}"></script>'

        # Note: <link>s are supposed to come before <style> in the output

        for resource_list, expected in [
            ([content1],                       exp_content1),
            ([url1],                           exp_url1),
            ([content1, content2],             exp_content12),
            ([url1, url2],                     exp_url1 + exp_url2),
            ([url1, content1],                 exp_url1 + exp_content1),
            ([content1, url1],                 exp_content1 + exp_url1),
            ([content1, url1, content2, url2], exp_content1 + exp_url1 + exp_content2 + exp_url2),
            ([url1, content1, content2, url2], exp_url1 + exp_content12 + exp_url2),
        ]:
            assert_that(
                sw.format(resource_list),
                equal_to_ignoring_whitespace(expected))


    def test_nested_stylesheets(self):
        """
        More expansive/holistic test of resources.py and resource_writers.py, as they relate to
        the embedding of stylesheets.
        """

        with tempfile.TemporaryDirectory() as _dir:

            dir = Path(_dir)
            os.chdir(_dir)
            (dir / 'dir1' / 'dir2' / 'dir3').mkdir(parents = True)
            (dir / 'dir4' / 'dir5' / 'dir6').mkdir(parents = True)

            # Test file structure:
            # |
            # +-- dir1/ [resource_base_url]
            # |   |
            # |   \-- dir2/
            # |       |
            # |       +-- fileA.css
            # |       \-- dir3
            # |           |
            # |           +-- fileB.css
            # |           \-- fileB.txt
            # |
            # \-- dir4/
            #     |
            #     +-- fileC.css
            #     +-- fileC.txt
            #     \-- dir5/
            #         |
            #         \-- dir6/
            #             |
            #             +-- fileD.css
            #             \-- fileD.txt

            # fileA.css will refer to fileB.*, fileB.css to fileC.*, and fileC.css to fileD.*.
            # The .css files will be embedded using data URLs; the .txt files will not, but their
            # URLs (initially expressed relative to the previous file), must be relativized against
            # the base directory.

            # NOTE: this test is sensitive to the exact spacing choices made by the production code.
            # Since there are multiple levels of base64 encoding, more/less whitespace results in
            # different _non-whitespace_ characters too. So care is needed!

            def nospace(s):
                return s.replace(' ', '').replace('\n', '').replace('[_]', ' ')

            orig_contentA = nospace('''
                @import[_]"dir3/fileB.css";
                @import[_]"dir3/fileB.txt";
            ''')

            orig_contentB = nospace('''
                @import[_]"../../../dir4/fileC.css";
                @import[_]"../../../dir4/fileC.txt";
            ''')

            orig_contentC = nospace('''
                @import[_]"dir5/dir6/fileD.txt";
                @import[_]"dir5/dir6/fileD.css";
            ''')

            orig_contentD = nospace('''
                p { color: blue }
            ''')

            (dir / 'dir1' / 'dir2' / 'fileA.css').write_text(orig_contentA)
            (dir / 'dir1' / 'dir2' / 'dir3' / 'fileB.css').write_text(orig_contentB)
            (dir / 'dir1' / 'dir2' / 'dir3' / 'fileB.txt').write_text(orig_contentB)
            (dir / 'dir4' / 'fileC.css').write_text(orig_contentC)
            (dir / 'dir4' / 'fileC.txt').write_text(orig_contentC)
            (dir / 'dir4' / 'dir5' / 'dir6' / 'fileD.css').write_text(orig_contentD)
            (dir / 'dir4' / 'dir5' / 'dir6' / 'fileD.txt').write_text(orig_contentD)

            # Work out the expected result programmatically. It would be too fragile to hard-code
            # a manual calculation here.

            b64_contentD = base64.b64encode(orig_contentD.encode()).decode()
            conv_contentC = nospace(f'''
                @import[_]"dir4/dir5/dir6/fileD.txt";
                @import[_]"data:text/css;base64,{b64_contentD}";
            ''')
            b64_contentC = base64.b64encode(conv_contentC.encode()).decode()
            conv_contentB = nospace(f'''
                @import[_]"data:text/css;base64,{b64_contentC}";
                @import[_]"dir4/fileC.txt";
            ''')
            b64_contentB = base64.b64encode(conv_contentB.encode()).decode()
            conv_contentA = nospace(f'''
                @import[_]"data:text/css;base64,{b64_contentB}";
                @import[_]"dir1/dir2/dir3/fileB.txt";
            ''')


            mock_build_params = Mock()
            type(mock_build_params).progress = PropertyMock(return_value = MockProgress())
            # Embed only .css files, not .txt files.
            type(mock_build_params).embed_rule = PropertyMock(return_value =
                                                              lambda url, **k: url.endswith('css'))

            expected = f'<style>\n{conv_contentA}\n</style>'

            for base_url, resource_spec in [
                (
                    'dir1/dir2/',
                    resources.ContentResourceSpec(
                        xpaths_required = [],
                        content_factory = lambda *a: orig_contentA),
                ),
                (
                    # With URL-based stylesheets, we can test an extra level of indirection. i.e.,
                    # the resources in dir1/dir2/fileA.css are relative to the file's location,
                    # 'dir2', not directly to the base path 'dir1'.
                    'dir1/',
                    resources.UrlResourceSpec(
                        xpaths_required = [],
                        url_factory     = lambda *a: 'dir2/fileA.css',
                        base_url        = 'dir1/',
                        cache           = Mock(),
                        embed_fn        = lambda *a: True,
                        hash_type_fn    = None,
                        # mime_type       = 'text/css'
                    )
                )
            ]:
                type(mock_build_params).resource_base_url = PropertyMock(return_value = base_url)
                resource = resource_spec.make_resource(set(), Mock())
                output = resource_writers.StylesheetWriter(mock_build_params).format([resource])
                self.assertEqual(expected, output)


    def test_embed_cycle(self):
        with tempfile.TemporaryDirectory() as dir:
            os.chdir(dir)

            # Two cycles: A->A, and B->[C->D->E->C]
            for file, to in [
                ('A', 'A'),
                ('B', 'C'),
                ('C', 'D'),
                ('D', 'E'),
                ('E', 'C'),
            ]:
                Path(f'file{file}.css').write_text(f'@import "file{to}.css";')

            mock_build_params = Mock()
            mock_progress = Mock()
            type(mock_build_params).progress = PropertyMock(return_value = mock_progress)
            type(mock_build_params).embed_rule = PropertyMock(return_value = lambda **k: True)
            type(mock_build_params).resource_base_url = PropertyMock(return_value = '')

            sw = resource_writers.StylesheetWriter(mock_build_params)

            for url in ['fileA.css', 'fileB.css']:
                resource = resources.UrlResource(url, to_embed = True)
                sw.format([resource])

                mock_progress.error.assert_called_once()
                mock_progress.reset_mock()


    @patch('lamarkdown.lib.resource_writers.make_data_url')
    def test_embed_media(self, mock_make_data_url):
        mock_make_data_url.return_value = 'data:mock'

        root = ElementTree.Element('div')
        p = ElementTree.SubElement(root, 'p')

        mock_build_params = Mock()

        # Mock embedding rule that embeds everything, except elements having a special mime
        # type.
        type(mock_build_params).embed_rule = PropertyMock(
            return_value = lambda mime, **k: mime != 'no/embed')

        live_update_deps = set()
        type(mock_build_params).live_update_deps = PropertyMock(return_value = live_update_deps)


        # We should be able to embed src= URLs in all the following cases.
        # (<embed> and <source> also have type=... attributes for specifying the mime type.
        # <input> has a type= attribute for a different purpose.)
        remote_data = [
            ('audio',  'mp3',  'audio/mpeg',             {}),
            ('audio',  'mp3',  'audio/mpeg',             {'type': 'mock/type'}),
            ('embed',  'jpg',  'image/jpeg',             {}),
            ('embed',  'jpg',  'mock/type',              {'type': 'mock/type'}),  # type attr
            ('iframe', 'html', 'text/html',              {}),
            ('iframe', 'html', 'text/html',              {'type': 'mock/type'}),
            ('input',  'jpg',  'image/jpeg',             {}),
            ('input',  'jpg',  'image/jpeg',             {'type': 'image'}),
            ('input',  'jpg',  'image/jpeg',             {'type': 'mock/type'}),
            ('img',    'jpg',  'image/jpeg',             {}),
            ('img',    'jpg',  'image/jpeg',             {'type': 'mock/type'}),
            ('script', 'js',   'application/javascript', {}),
            ('script', 'js',   'application/javascript', {'type': 'mock/type'}),
            ('source', 'jpg',  'image/jpeg',             {}),
            ('source', 'jpg',  'mock/type',              {'type': 'mock/type'}),  # type attr
            ('track',  'vtt',  'text/vtt',               {}),
            ('track',  'vtt',  'text/vtt',               {'type': 'mock/type'}),
            ('video',  'mp4',  'video/mp4',              {}),
            ('video',  'mp4',  'video/mp4',              {'type': 'mock/type'}),
        ]

        for tag, ext, mime_type, attr in remote_data:
            ElementTree.SubElement(p, tag, src = f'http://example.com/file.{ext}', **attr)

        # We should _avoid_ doing anything to these kinds of tags/URL combinations:
        local_data = [
            ('audio',  'data:audio/mpeg,abc',         {}),
            ('embed',  'http://example.com/file.jpg', {'type': 'no/embed'}),
            ('img',    'data:image/jpeg;base64,abc',  {}),
            ('script', 'data:;base64,def',            {}),
            ('source', 'http://example.com/file.jpg', {'type': 'no/embed'}),
            ('video',  'data:,def',                   {}),
            ('track',  '#fragment',                   {}),
            ('div',    'http://example.com/div',      {}),
            ('span',   'http://example.com/span',     {}),
        ]

        non_modified_elements = [
            (ElementTree.SubElement(p, tag, src = src, **attr), src)
            for tag, src, attr in local_data
        ]

        # Production code
        resource_writers.embed_media(root, '', mock_build_params)

        # Verify that embeddable things have been embedded
        for tag, ext, mime_type, attr in remote_data:
            mock_make_data_url.assert_any_call(
                f'http://example.com/file.{ext}',
                'mock/type' if mime_type == 'mock_type' else None,
                mock_build_params)

        # Since they're all remote, they shouldn't be candidates for live update dependencies
        assert_that(live_update_deps, empty())

        self.assertEqual(len(remote_data), mock_make_data_url.call_count)

        # Verify non-embeddable things have not been embedded
        for element, src in non_modified_elements:
            self.assertEqual(src, element.get('src'))


    @patch('lamarkdown.lib.resources.read_url')
    def test_dependency_recognition(self, mock_read_url):
        mock_read_url.return_value = (False, b'mock_content', 'mock/type')

        mock_build_params = Mock()
        live_update_deps = set()
        type(mock_build_params).live_update_deps = PropertyMock(return_value = live_update_deps)
        type(mock_build_params).embed_rule = PropertyMock(return_value = lambda **k: True)

        for tag in ['audio', 'embed', 'iframe', 'img', 'script', 'source', 'track', 'video']:

            filename = f'{tag}.ext'
            element = ElementTree.Element(tag, src = filename)

            resource_writers.embed_media(element, '', mock_build_params)
            assert_that(live_update_deps, contains_exactly(Path(filename).absolute()))

            live_update_deps.clear()


        for WriterCls in [resource_writers.StylesheetWriter, resource_writers.ScriptWriter]:
            _ = WriterCls(mock_build_params).format([
                resources.UrlResource(url = 'file1', to_embed = True),
                resources.UrlResource(url = 'file2', to_embed = False),
                resources.UrlResource(url = 'file3', to_embed = True),
            ])

            assert_that(
                live_update_deps,
                contains_inanyorder(Path('file1').absolute(), Path('file3').absolute()))

            live_update_deps.clear()
