'''
# Latex Extension

The 'la.latex' extension lets you write Latex code inside a .md file. This works in two ways:

(1) Inclusion of an entire Latex document or environment (e.g., to create a PGF/Tikz image).

    Such code will be compiled with an external Latex command, converted to SVG, and embedded in
    the output HTML. The Latex code must start on a new line, and can either:

    (a) Be a complete Latex document, which must begin with '\\documentclass' and end with
        '\\end{document}';

    (b) Be a cut-down form, which must:

        * Begin with '\\usepackage', '\\usetikzlibrary' or '\\begin{<name>}';
        * Contain '\\begin{<name>}' (if it didn't start with it); and
        * End with '\\end{<name>}'.

        The extension prepends an implied '\\documentclass'. If <name> is not 'document', then the
        extension also adds in '\\begin{document}...\\end{document}'.

    There are various configuration options, allowing a choice of Latex compiler, PDF-to-SVG
    converter, method of embedding SVG, optional common Latex code to be inserted after
    '\\documentclass', etc.


(2) Using $...$ and $$...$$ for Latex math code, at any point within a paragraph (except inside
    `...`).

    By default (or if math="mathml"), latex2mathml is used to produce MathML code, which is
    included directly in the output document.

    If math="latex", then math code will instead be compiled and converted the same way as in (1),
    just in math mode.

    Processing of math code can also be turned off with math="ignore" (either to restore the
    literal meaning of '$', or to use an alternate math code processor like pymdownx.arithmatex).
'''

from __future__ import annotations
from lamarkdown.lib.progress import Progress
from . import util
from .util import replacement_patterns

import markdown

import latex2mathml.converter

import base64
import copy
import hashlib
import io
import os
import pathlib
import re
import subprocess
import threading
import time
from typing import Callable
from xml.etree import ElementTree

NAME = 'la.latex'  # For error messages

DATA_URI_EMBEDDING = 'data_uri'
SVG_ELEMENT_EMBEDDING = 'svg_element'

MATH_MATHML = 'mathml'
MATH_LATEX  = 'latex'
MATH_IGNORE = 'ignore'


class CommandException(Exception):
    def __init__(self, msg: str, output: str):
        super().__init__(msg)
        self.output = output


def check_run(command: str | list[str],
              expected_output_file: Path,
              timeout: float | None = None,
              **kwargs):
    start_time = time.time_ns()
    command_str = ' '.join(command) if isinstance(command, list) else command

    popen = subprocess.Popen(command,
                             shell = isinstance(command, str),
                             stdin = subprocess.DEVNULL,  # Supposed to be non-interactive!
                             stdout = subprocess.PIPE,
                             stderr = subprocess.STDOUT,
                             encoding = 'utf-8',
                             bufsize = 1,  # line-buffered
                             **kwargs)

    new_output = threading.Event()
    output_buf = io.StringIO()
    output_lock = threading.Lock()

    if (stdout := popen.stdout) is not None:
        def read_stdout():
            # Reads stdout from the process in a separate thread, so the blocking doesn't interfere
            # with our timeout monitoring.
            try:
                for line in iter(stdout.readline, ''):
                    new_output.set()
                    with output_lock:
                        output_buf.write(line)
            finally:
                stdout.close()

        threading.Thread(target = read_stdout).start()

    if timeout is None:
        popen.wait()

    else:
        # Monitor the running process, so we can cause it to timeout, but _only after_ it stops
        # producing output.
        last_output_time = time.time()
        while True:
            try:
                new_output.clear()
                popen.wait(timeout = 0.1)
                # Process finished.
                break

            except subprocess.TimeoutExpired:
                # Still going.
                if new_output.is_set():
                    # Output was seen; reset the timer.
                    last_output_time = time.time()

                elif (time.time() - last_output_time) >= timeout:
                    # Timeout.
                    if popen.stdout is not None:
                        popen.stdout.close()
                    popen.terminate()
                    with output_lock:
                        raise CommandException(
                            f'"{command_str}" timed out, after {timeout} secs of no output',
                            output_buf.getvalue())

    assert popen.returncode is not None  # The process should be stopped by now.

    if popen.returncode != 0:
        with output_lock:
            raise CommandException(
                f'"{command_str}" returned error code {popen.returncode}',
                output_buf.getvalue())

    try:
        file_time = expected_output_file.stat().st_mtime_ns
    except OSError:
        file_time = 0

    if file_time < start_time:
        with output_lock:
            raise CommandException(
                f'"{command_str}" did not create expected file "{expected_output_file}"',
                output_buf.getvalue())


STX = '\u0002'
ETX = '\u0003'
LATEX_PLACEHOLDER_PREFIX = f'{STX}la.latex-uoqwpkayei:'
LATEX_PLACEHOLDER_RE     = re.compile(f'{LATEX_PLACEHOLDER_PREFIX}(?P<id>[0-9]+){ETX}')

HTML_COMMENT_RE = re.compile(r'<!--.*?(-->|$)', flags = re.DOTALL)


ERROR_LINE_NUMBER_RE = re.compile(r'(^|\n)l\.(?P<n>[0-9]+)')


def _pdf2svg_correction(svg: str) -> str:
    '''
    pdf2svg leaves off the units on width/height, and the default is technically 'px', but the
    numbers appear to be expressed in 'pt'. This just adds 'pt' to the SVG dimensions.
    '''
    return re.sub(
        '<svg[^>]*>',
        lambda m: re.sub(
            r'''((width|height)=['"][0-9]+(\.[0-9]+)?)(?=['"])''',
            r'\1pt',
            m.group()),
        svg)


class LatexCompiler:
    '''
    Compiles Latex code identified by the preprocessor/replacement processor, converts it to SVG,
    caches the result, and makes the result available (by the html property).
    '''

    CACHE_PREFIX = 'lamarkdown.latex'

    STD_TEX_CMDLINE = ['-halt-on-error', '-interaction', 'errorstopmode', '-recorder', 'job']
    TEX_CMDLINES = {
        'pdflatex': ['pdflatex', *STD_TEX_CMDLINE],
        'xelatex':  ['xelatex', *STD_TEX_CMDLINE],
    }

    CONVERTER_CMDLINES = {
        'dvisvgm': ['dvisvgm', '--pdf', 'job.pdf'],
        'pdf2svg': ['pdf2svg', 'job.pdf', 'job.svg'],
        'inkscape': ['inkscape', '--pdf-poppler', 'job.pdf', '-o', 'job.svg'],
    }

    CONVERTER_CORRECTIONS: dict[str, Callable[[str], str]] = {
        'pdf2svg': _pdf2svg_correction
    }

    def __init__(self, md, cache_factors: tuple, build_dir: Path, cache, progress: Progress,
                 live_update_deps: set[str], tex: str, pdf_svg_converter: str, embedding: str,
                 strip_html_comments: bool, timeout: int, verbose_errors: bool):

        self._md = md
        self._cache_factors = cache_factors

        self._html: dict[int, str] = {}
        self._instance = 0

        self.md = md
        self._build_dir = build_dir
        self.cache = cache
        self.progress = progress
        self.live_update_deps = live_update_deps

        self.tex_cmdline: str | list[str] = (
            self.TEX_CMDLINES.get(tex)
            or tex.replace('in.tex', 'job.tex').replace('out.pdf', 'job.pdf')
        )

        self.converter_cmdline: str | list[str] = (
            self.CONVERTER_CMDLINES.get(pdf_svg_converter)
            or pdf_svg_converter.replace('in.pdf', 'job.pdf').replace('out.svg', 'job.svg')
        )

        self.converter_correction = (
            self.CONVERTER_CORRECTIONS.get(pdf_svg_converter)
            or (lambda svg: svg)
        )

        self.embedding = embedding
        self.strip_html_comments = strip_html_comments
        self.timeout = timeout
        self.verbose_errors = verbose_errors


    def _generate_html(self, latex: str, attr: dict[str, str]) -> str:
        # Run Python Markdown's postprocessors.

        # This is important, because Markdown's _pre_processors replace certain constructs,
        # particularly HTML snippets, with special placeholders, which are again replaced by
        # postprocessors once all the block processing and tree manipulation is done.
        #
        # This is exactly what LatexPreprocessor and LatexPostprocessor do themselves, but now
        # we must invoke the _other_ postprocessors too.
        for post_proc in self._md.postprocessors:
            if not isinstance(post_proc, LatexPostprocessor):
                latex = post_proc.run(latex)

        # Having done this, we now (again) need to strip out HTML comments, because these (in
        # certain circumstances) are given the preprocessor-postprocessor treatment by Python
        # Markdown, and so might not have been removed by _our_ preprocessor.
        if self.strip_html_comments:
            latex = HTML_COMMENT_RE.sub('', latex)

        # Build a representation of all the input information sources.
        cache_key = (self.CACHE_PREFIX, latex, self._cache_factors)

        # If not in cache, compile it.
        run_latex = True
        if cache_key in self.cache:
            element, dependencies = self.cache.get(cache_key)
            if self.are_deps_unchanged(dependencies):
                self.live_update_deps.update(dependencies)
                # We make a copy of the cached element, because different instances of it could
                # conceivably be assigned different attributes below.
                element = copy.copy(element)
                run_latex = False
            else:
                self.progress.cache_hit(NAME)

        if run_latex:
            hasher = hashlib.sha1()
            hasher.update(latex.encode('utf-8'))
            file_build_dir = self._build_dir / f'latex-{hasher.hexdigest()}'

            try:
                file_build_dir.mkdir(exist_ok = True)

                tex_file = file_build_dir / 'job.tex'
                fls_file = file_build_dir / 'job.fls'
                pdf_file = file_build_dir / 'job.pdf'
                svg_file = file_build_dir / 'job.svg'

                with open(tex_file, 'w') as f:
                    f.write(latex)

            except OSError as e:
                return self.progress.error(NAME, exception = e).as_html_str()

            try:
                self.progress.progress(
                    NAME, msg = f'Invoking "{self.tex_cmdline[0]}" to compile .tex to .pdf...')
                check_run(
                    self.tex_cmdline,
                    pdf_file,
                    cwd = str(file_build_dir),
                    env = {**os.environ, 'TEXINPUTS': f'.:{os.getcwd()}:'},
                    timeout = self.timeout
                )
            except CommandException as e:
                msg = str(e)
                output = e.output

                # Try to detect the start of a Latex error message (beginning with '!'), so we can
                # report that message directly.
                lines = output.splitlines()
                first_error_line = next(
                    (i for i, line in enumerate(lines) if line.startswith('!')),
                    None)
                if first_error_line:
                    msg = lines[first_error_line][2:]
                    if not self.verbose_errors:
                        # Generally, output prior to the error message can be ignored.
                        output = '\n'.join(lines[first_error_line:])

                ln_match = ERROR_LINE_NUMBER_RE.search(output)
                if ln_match:
                    line = int(ln_match.group('n'))
                    highlight_lines = {line, line - 1}
                else:
                    highlight_lines = None

                return self.progress.error(NAME,
                                           msg = msg,
                                           output = output,
                                           code = latex,
                                           highlight_lines = highlight_lines).as_html_str()

            if fls_file.exists():
                dependencies = self.find_live_update_deps(fls_file)
                self.live_update_deps.update(dependencies.keys())
            else:
                dependencies = {}
                self.progress.warning(NAME, msg = 'Tex command did not create an .fls file')

            try:
                self.progress.progress(
                    NAME,
                    msg = f'Invoking "{self.converter_cmdline[0]}" to convert .pdf to .svg...')
                check_run(
                    self.converter_cmdline,
                    svg_file,
                    cwd = str(file_build_dir)
                )

                with open(svg_file) as reader:
                    svg_content = self.converter_correction(reader.read())
                    element = ElementTree.fromstring(svg_content)
                    util.strip_namespaces(element)
                    util.opaque_tree(element)

                    if element.get('viewBox') in [None, '0 0 0 0']:
                        return self.progress.error(
                            NAME,
                            msg = (f'Resulting SVG code is empty -- either {self.tex_cmdline[0]} '
                                   f'or {self.converter_cmdline[0]} failed'),
                            output = svg_content).as_html_str()

                if self.embedding == DATA_URI_EMBEDDING:
                    data = base64.b64encode(svg_content.strip().encode()).decode()
                    # data_uri = f'data:image/svg+xml;base64,{data}'
                    # element = ElementTree.fromstring(f'<img src="{data_uri}" />')
                    element = ElementTree.fromstring(
                        f'<img src="data:image/svg+xml;base64,{data}" />')

                self.cache[cache_key] = (copy.copy(element), dependencies)

            except CommandException as e:
                return self.progress.error(NAME,
                                           exception = e,
                                           show_traceback = False,
                                           output = e.output,
                                           code = latex,
                                           context_lines = None).as_html_str()

        util.set_attributes(element, attr)
        return ElementTree.tostring(element, encoding = 'unicode')


    def find_live_update_deps(self, fls_file: Path):
        home = Path.home()
        cwd = Path.cwd()
        with open(fls_file) as log:
            input_files = {Path(line[6:-1] if line.endswith('\n') else line[6:]).absolute()
                           for line in log
                           if line.startswith('INPUT ')}

            return {
                f: f.stat().st_mtime if f.exists() else None
                for f in input_files
                if f.parts[:len(home)] == home or f.parts[:len(cwd)] == cwd
            }

    def are_deps_unchanged(self, dependencies):
        for f, old_mtime in dependencies.items():
            if old_mtime != (f.stat().st_mtime if f.exists() else None):
                return False  # Changed
        return True  # Unchanged


    def compile(self, full_doc: str, attr: dict[str, str]):
        self._instance += 1
        self._html[self._instance] = self._generate_html(full_doc, attr)
        return f'{LATEX_PLACEHOLDER_PREFIX}{self._instance}{ETX}'

    @property
    def html(self):
        return self._html



class LatexPreprocessor(markdown.preprocessors.Preprocessor):
    '''
    The preprocessor identifies and parses Latex block snippets found in the document. Each one is
    passed to LatexCompiler, and marked in the document with a temporary placeholder, awaiting the
    postprocessor.

    (Previously, in commit 18fc579db4b4793a50ed077e369aa14e276ee189 and earlier, lamarkdown used a
    one-stage process, where a BlockProcessor would identify, parse, compile and embed each Latex
    snippet. This approach encountered some minor but unfortunate limitations; e.g., when placed
    inside a markdown list, the Latex code was prohibited from containing blank lines, because the
    block processor only saw one block at a time.)
    '''


    TEX_END_UNCOMMENTED = r'''
        (                       # Our snippet of tex code must be:
            [^%\n]*?            # (a) a single line with no comments, OR
            | .*? \n [^%\n]*?   # (b) anything, but ending with a non-commented newline.
        )                       # (Match non-greedily, or else we won't know where to end.)
    '''

    TEX_RE = re.compile(
        fr'''
        ^ (?P<indent> [ \t]* )          # Start on a new line; preserve indent
        (
            (?P<doc>                    # Full document syntax
                (?P<docclass>
                    \\documentclass
                    \{{ [^}}]+ \}}
                )
                {TEX_END_UNCOMMENTED}
                \\end\{{document}}
            )
            |
            (?P<preamble>               # OR, short-cut syntax, starting with optional preamble...
                \\
                (
                    usepackage          # Preamble begins with one of these
                    | usetikzlibrary
                )
                {TEX_END_UNCOMMENTED}
            )?
            (?P<main>
                \\begin\{{              # Start of the main environment
                    (?P<env>[^}}]+)      # Capture the environment name
                \}}
                {TEX_END_UNCOMMENTED}
                \\end\{{                # End of main environment
                    (?P=env)            # Match previous name
                \}}
            )
        )
        [ \t]* (%[^\n]*)?   # Ends with whitespace, then an optional comment
        (
            \n[ \t]*        # Start attributes (if any) on a new line
            {util.ATTR}
        )?
        ''',
        re.VERBOSE | re.DOTALL | re.MULTILINE)


    def __init__(self,
                 compiler: LatexCompiler,
                 prepend: str,
                 doc_class: str,
                 doc_class_options: str,
                 strip_html_comments: bool):
        self.compiler = compiler
        self.prepend = prepend
        self.doc_class = doc_class
        self.doc_class_options = doc_class_options
        self.strip_html_comments = strip_html_comments


    def _format_latex(self, match_obj: re.Match) -> str:
        full_doc = match_obj.group('doc')
        if full_doc:
            if self.prepend:
                split = match_obj.end('docclass') - match_obj.start()
                full_doc = f'{full_doc[:split]}\n{self.prepend}{full_doc[split:]}'
            else:
                pass

        else:
            main_part = match_obj.group('main')
            if match_obj.group('env') != 'document':
                main_part = fr'\begin{{document}}{main_part}\end{{document}}'

            full_doc = (
                f'\\documentclass[{self.doc_class_options}]{{{self.doc_class}}}\n'
                + '\\usepackage{tikz}\n'
                + (self.prepend or "")
                + (match_obj.group('preamble') or "")
                + (main_part)
            )

        return self.compiler.compile(full_doc, match_obj.group('attr'))


    def run(self, lines: list[str]) -> list[str]:
        raw_text = '\n'.join(lines)
        search_text = raw_text
        if self.strip_html_comments:
            # Blank-out HTML comments.
            search_text = HTML_COMMENT_RE.sub(
                lambda match: ' ' * len(match.group(0)),
                search_text)
            assert len(raw_text) == len(search_text)

        # Here we do a bit of a dance, where we're *searching* one set of text, normally with HTML
        # comments stripped, but we're making string substitutions (replacing the Latex code with
        # placeholders) on the *original* text.
        #
        # The Latex code itself is now stripped of HTML comments (if that option is set), but the
        # rest of the original text will retain them, and any commented-out Latex code will also be
        # retained verbatim.
        #
        # (If the user wants to strip HTML comments *in general* from the document, this is left as
        # an exercise for another component.)
        return_text = []
        last_match_end = 0
        for match in self.TEX_RE.finditer(search_text):
            match_start = match.start()

            if last_match_end < match_start:
                # Some intervening, non-Latex text. Accumulate it in return_text.
                return_text.append(raw_text[last_match_end:match_start])

            # Accumulate the placeholder text in return_text.
            return_text.append(match['indent'])
            return_text.append(self._format_latex(match))
            last_match_end = match.end()

        # Add any trailing non-Latex text.
        return_text.append(raw_text[last_match_end:])

        # Join all the fragments together, and then split them back into lines, as required by
        # contract.
        return ''.join(return_text).split('\n')


MATH_TEX_RE = rf'''(?xs)
    (
        \$\$
        (?P<latex_block>
            [^$]+
        )
        \$\$
        |
        \$
        (?P<latex_inline>
            [^\s$]
            (
                [^$]*
                [^\s$]
            )?
        )
        \$
    )
    ({util.ATTR})?
'''


class LatexReplacementProcessor(replacement_patterns.ReplacementPattern):
    '''
    This replacement processor identifies and parses Latex math snippets. Each one is passed to
    LatexCompiler, and marked in the document with a temporary placeholder, awaiting the
    postprocessor.
    '''

    def __init__(self,
                 compiler: LatexCompiler,
                 prepend: str,
                 doc_class: str,
                 doc_class_options: str):
        super().__init__(MATH_TEX_RE)
        self.compiler = compiler
        self.prepend = prepend
        self.doc_class = doc_class
        self.doc_class_options = doc_class_options


    def handle_match(self, match):
        latex_inline = match.group('latex_inline')
        latex_block = match.group('latex_block')

        display_cmd = r'\displaystyle{}' if latex_block else ''
        full_doc = rf'''
            \documentclass[{self.doc_class_options}]{{{self.doc_class}}}
            \usepackage{{tikz}}
            \usepackage{{amsmath}}
            {self.prepend or ''}
            \begin{{document}}
                ${display_cmd}{latex_inline or latex_block}$
            \end{{document}}
        '''

        element = ElementTree.Element('span', attrib = {'class': 'la-math'})
        element.text = self.compiler.compile(full_doc, match.group('attr'))

        return element


class LatexMathMLReplacementProcessor(replacement_patterns.ReplacementPattern):
    '''
    This replacement processor also identifies and parses Latex math snippets. For each one, we
    invoke latex2mathml to produce a <math>...</math> element representing the Latex math code.
    '''

    def __init__(self):
        super().__init__(MATH_TEX_RE)

    def handle_match(self, match):

        latex_inline = match.group('latex_inline')
        latex_block = match.group('latex_block')

        display_attr = 'block' if latex_block else 'inline'

        mathml_code = latex2mathml.converter.convert(latex_inline or latex_block,
                                                     display = display_attr)
        element = ElementTree.fromstring(mathml_code)
        util.strip_namespaces(element)
        util.opaque_tree(element)
        util.set_attributes(element, match)

        return element



class LatexPostprocessor(markdown.postprocessors.Postprocessor):
    '''
    Searches for the placeholder strings inserted by the preprocessor/replacement processor to
    determine where to substitute the compiled HTML.
    '''

    def __init__(self, compiler: LatexCompiler):
        self.compiler = compiler

    def run(self, text):
        return LATEX_PLACEHOLDER_RE.sub(
            lambda match: self.compiler.html[int(match.group('id'))],
            text)


class LatexExtension(markdown.Extension):
    def __init__(self, **kwargs):
        # Try to get some objects from the current build parameters:
        # (1) the build dir -- the location where we'll execute latex, and where all its
        #     temporary files will accumulate;
        # (2) the global cache -- allowing us to avoid re-compiling when the Latex code hasn't
        #     changed.
        #
        # This will only work if this extension is being used within the context of lamarkdown.
        # But we do have a fallback on the off-chance that someone wants to use it elsewhere.
        p = None
        try:
            from lamarkdown.lib.build_params import BuildParams
            p = BuildParams.current
        except ModuleNotFoundError:
            pass  # Use default defaults

        self.config = {
            'build_dir': [
                p.build_dir if p else 'build',
                'Location to write temporary files'
            ],
            'cache': [
                p.build_cache if p else {},
                'A dictionary-like cache object to help avoid unnecessary rebuilds.'
            ],
            'progress': [
                p.progress if p else Progress(),
                'An object accepting progress messages.'
            ],
            'live_update_deps': [
                p.live_update_deps if p else set(),
                'A set into which the extension will record the names of any local, external '
                'files that the given Tex code depends on (not including the Tex installation '
                'itself).'
            ],
            'tex': [
                'xelatex',
                'Program used to compile .tex files to PDF files. Generally, this should be a '
                'complete command-line containing the strings "in.tex" and "out.pdf" (which will '
                'be replaced with the real names as needed). However, it can also be simply '
                '"pdflatex" or "xelatex", in which case pre-defined command-lines for those '
                'commands will be used.'
            ],
            'pdf_svg_converter': [
                'dvisvgm',
                'Program used to convert PDF files (produced by Tex) to SVG files to be embedded '
                'in the HTML output. Generally, this should be a complete command-line containing '
                'the strings "in.pdf" and "out.svg" (which will be replaced with the real names '
                'as needed). However, it can also be simply  "dvisvgm", "pdf2svg" or "inkscape", '
                'in which case pre-defined command-lines for those commands will be used.'
            ],
            'embedding': [
                DATA_URI_EMBEDDING,
                f'Either "{DATA_URI_EMBEDDING}" or "{SVG_ELEMENT_EMBEDDING}", specifying how the '
                'SVG data will be attached to the HTML document.'
            ],
            'prepend': [
                '',
                'Extra Tex code to be added to the front of each Tex snippet.'
            ],
            'doc_class': [
                'standalone',
                'The Latex document class to use, when not explicitly given.'
            ],
            'doc_class_options': [
                '',
                'Options provided to the Latex document class, as a single string.'
            ],
            'strip_html_comments': [
                True,
                'Considers "<!--...-->" to be a comment, and removes them before compiling with '
                'Latex. Latex would (in most cases) interpret these sequences as ordinary '
                'characters, whereas in markdown they would normally be (effectively) ignored. If '
                'you need to write a literal "<!--", you can do so by inserting "{}" between the '
                'characters. (This option does not affect normal Tex "%" comments.)'
            ],
            'timeout': [
                3,
                'Time (secs) before the tex command will be terminated, once it stops outputting '
                'messages.'
            ],
            'verbose_errors': [
                False,
                'If True, then everything the Tex command writes to stdout will be included in any '
                'error messages. If False (the default), the extension will try to detect the '
                'start of any actual Tex error message, and only output that.'
            ],
            'math': [
                MATH_MATHML,
                'How to handle $...$ and $$...$$ sequences, which are assumed to contain Latex '
                f'math code. The options are "{MATH_IGNORE}", "{MATH_LATEX}" or "{MATH_MATHML}" '
                f'(the default). For "{MATH_IGNORE}", math code is left untouched by this '
                'extension. Use this to avoid conflicts if, for instance, you\'re using another '
                f'extension (like pymdownx.arithmatex) to handle them. For "{MATH_LATEX}", math '
                r'code is compiled in essentially the same way as \begin{}...\end{} blocks (but '
                f'in math mode). For "{MATH_MATHML}", math code is converted to MathML <math> '
                'elements, to be rendered by the browser.'
            ],
        }
        super().__init__(**kwargs)

        progress = self.getConfig('progress')

        embedding = self.getConfig('embedding')
        if embedding not in [DATA_URI_EMBEDDING, SVG_ELEMENT_EMBEDDING]:
            progress.error(NAME, msg = f'Invalid value "{embedding}" for config option "embedding"')
            self.setConfig('embedding', DATA_URI_EMBEDDING)

        math = self.getConfig('math')
        if math not in [MATH_IGNORE, MATH_LATEX, MATH_MATHML]:
            progress.error(NAME, msg = f'Invalid value "{math}" for config option "math"')
            self.setConfig('math', MATH_MATHML)


    def extendMarkdown(self, md):
        md.registerExtension(self)

        tex                 = self.getConfig('tex')
        pdf_svg_converter   = self.getConfig('pdf_svg_converter')
        prepend             = self.getConfig('prepend')
        doc_class           = self.getConfig('doc_class')
        doc_class_options   = self.getConfig('doc_class_options')
        strip_html_comments = self.getConfig('strip_html_comments')
        timeout             = self.getConfig('timeout')
        verbose_errors      = self.getConfig('verbose_errors')
        math                = self.getConfig('math')

        compiler = LatexCompiler(
            md,
            cache_factors       = (tex, pdf_svg_converter, prepend, doc_class, doc_class_options,
                                   strip_html_comments, timeout, verbose_errors, math),
            build_dir           = self.getConfig('build_dir'),
            cache               = self.getConfig('cache'),
            progress            = self.getConfig('progress'),
            live_update_deps    = self.getConfig('live_update_deps'),
            tex                 = tex,
            pdf_svg_converter   = pdf_svg_converter,
            embedding           = self.getConfig('embedding'),
            strip_html_comments = strip_html_comments,
            timeout             = timeout,
            verbose_errors      = verbose_errors,
        )

        md.preprocessors.register(
            LatexPreprocessor(
                compiler,
                prepend             = prepend,
                doc_class           = doc_class,
                doc_class_options   = doc_class_options,
                strip_html_comments = strip_html_comments,
            ),
            'la-latex-pre', 15)

        md.postprocessors.register(
            LatexPostprocessor(compiler),
            'la-latex-post', 25)

        replacementProcessor: replacement_patterns.ReplacementPattern | None = None
        if math == 'mathml':
            replacementProcessor = LatexMathMLReplacementProcessor()

        elif math == 'latex':
            replacementProcessor = LatexReplacementProcessor(
                compiler,
                prepend           = prepend,
                doc_class         = doc_class,
                doc_class_options = doc_class_options,
            )

        if replacementProcessor:
            util.replacement_patterns.init(md)
            md.replacement_patterns.register(replacementProcessor, 'la-latex-replacement', 20)
            md.ESCAPED_CHARS.append('$')



def makeExtension(**kwargs):
    return LatexExtension(**kwargs)
