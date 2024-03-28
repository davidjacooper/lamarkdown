from ..util.mock_progress import MockProgress
from lamarkdown.lib import md_compiler, build_params
from lamarkdown.lib.directives import Directives

import unittest
from unittest.mock import patch

from pathlib import Path
import tempfile
from textwrap import dedent


class BuildModTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp_dir_context = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp_dir_context.__enter__())
        self.html_file = self.tmp_dir / 'testdoc.html'

    def tearDown(self):
        self.tmp_dir_context.__exit__(None, None, None)

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

        progress = MockProgress()
        bp = build_params.BuildParams(
            src_file = doc_file,
            target_file = self.html_file,
            build_files = [build_file] if build else [],
            build_dir = build_dir,
            build_defaults = build_defaults,
            build_cache = {},
            fetch_cache = {},
            progress = progress,
            directives = Directives(progress),
            is_live = is_live,
            allow_exec_cmdline = False
        )

        md_compiler.compile(bp)

    @patch('lamarkdown.lib.resources.read_url')
    def test_non_exception(self, mock_read_url):

        mock_read_url.return_value = (False, b'', None)

        # Currently we're _only_ checking that the various modules don't actually throw exceptions
        # during loading.

        # TODO: For some modules, there is clearly more we could do (e.g., heading_numbers and
        # plots).

        for mod in ['code', 'doc', 'page_numbers', 'plots', 'teaching']:
            self.run_md_compiler(
                markdown='Text',
                build=fr'''
                    import lamarkdown as la
                    la.m.{mod}()
                '''
            )
