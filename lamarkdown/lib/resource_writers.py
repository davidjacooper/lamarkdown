from __future__ import annotations
from .build_params import BuildParams
from .resources import UrlResource, ContentResource
from . import resources

import fontTools.ttLib   # type: ignore
import fontTools.subset  # type: ignore

from base64 import b64encode
import html
import io
import mimetypes
from pathlib import Path
import re
from typing import Callable, Iterable
import urllib.parse
import urllib.request

NAME = 'resource linking'  # For progress/error messages


def make_data_url(url: str,
                  mime_type: str | None,
                  build_params: BuildParams,
                  converter: Callable[[str, bytes, str], tuple[bytes, str]] | None = None) -> str:

    try:
        _, content_bytes, auto_mime_type = resources.read_url(url,
                                                              build_params.fetch_cache,
                                                              build_params.progress)
    except Exception as e:
        build_params.progress.error(NAME, msg = url, exception = e)
        return 'data:;base64,'

    else:
        mime_type = mime_type or auto_mime_type
        if converter is not None and content_bytes is not None:
            content_bytes, mime_type = converter(url, content_bytes, mime_type or '')

        return f'data:{mime_type or ""};base64,{b64encode(content_bytes or b"").decode()}'


def add_local_dependency(url: str, build_params: BuildParams):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme in ['file', '']:
        # build_params.live_update_deps.add(
        #     os.path.abspath(urllib.request.url2pathname(parsed_url.path)))
        build_params.live_update_deps.add(
            Path(urllib.request.url2pathname(parsed_url.path)).absolute())


class ResourceWriter:
    def __init__(self, build_params: BuildParams):
        self.build_params = build_params

    def format(self, resource_list: list[UrlResource | ContentResource]):
        buffer = io.StringIO()
        try:
            self.write(buffer, resource_list)
        except Exception as e:
            err = self.build_params.progress.error(NAME,
                                                   msg = self.__class__.__name__,
                                                   exception = e)
            buffer.write(err.as_comment())
        return buffer.getvalue()

    def write(self, buffer, resource_list: list[UrlResource | ContentResource]):
        raise NotImplementedError


    def _write_in_order(self, buffer, resource_list: list[UrlResource | ContentResource]):
        content_list: list[ContentResource] = []

        for res in resource_list:
            if isinstance(res, UrlResource):
                if len(content_list) > 0:
                    self._write_content(buffer, content_list)
                    content_list.clear()

                self._write_url(buffer, res)

            elif isinstance(res, ContentResource):
                content_list.append(res)

            else:
                raise AssertionError

        if len(content_list) > 0:
            self._write_content(buffer, content_list)

    def _write_urls_first(self, buffer, resource_list: list[UrlResource | ContentResource]):
        if len(resource_list) == 0:
            return ''

        content_resource_list = []
        for res in resource_list:
            if isinstance(res, UrlResource):
                self._write_url(buffer, res)
            elif isinstance(res, ContentResource):
                content_resource_list.append(res)
            else:
                raise AssertionError(f'Resource is {res.__class__} ({res})')

        if len(content_resource_list) > 0:
            self._write_content(buffer, content_resource_list)

    def _write_content(self, buffer, resource_sublist: Iterable[ContentResource]):
        raise NotImplementedError

    def _write_url(self, buffer, resource: UrlResource):
        raise NotImplementedError



class StylesheetWriter(ResourceWriter):

    CSS_COMMENT_REGEX = re.compile(r'(?s)\s*/\*.*?\*/')
    CSS_NEWLINE_REGEX = re.compile(r'(\s*\n)+\s*')

    CSS_STRING_REGEX_BASE = r'''
        (?P<quote>['"])
        (?P<str>
            (
                (?!(?P=quote)) [^\\\n] # Not the operative quote symbol, and not \ or \n
                | \\\\
                | \\.
            )*
        )
        (?P=quote)
    '''
    # FYI: the syntax (?!(?P=quote)) is a negative lookahead backreference. That is, the next
    # character must not be the <quote> character. Then [^\\\n] consumes that character, whatever
    # it is.

    CSS_STRING_REGEX = re.compile(fr'(?xs){CSS_STRING_REGEX_BASE}')
    CSS_URL_REGEX = re.compile(fr'''(?xs)
        \b(url|src)
        \(\s*
        (
            (?P<url>
                (
                    [^"'()\\\x00-\x20]
                    | \\\\
                    | \\[0-9a-fA-F]{{1,6}} [ \t\n]?
                    | \\.
                )*
            )
            |
            {CSS_STRING_REGEX_BASE}
        )
        \s*\)

        # Find and discard trailing 'format()' declaration. (It's not useful for embedded data
        # URLs, and if we're changing font formats from ttf to woff2, it's not going to be correct
        # either.)
        (
            \s* format \( [^)]* \)
        )?
    ''')

    # CSS @import can be written either '@import "..."' or '@import url(...)'. We're only matching
    # the former here, because we can handle all 'url(...)' constructs via CSS_URL_REGEX.
    #
    # Also, we're only matching the _start_ of an @import rule, which can contain other notation
    # after the URL.
    CSS_IMPORT_REGEX = re.compile(fr'''(?xs)
        @import
        \s*
        {CSS_STRING_REGEX_BASE}
    ''')

    # Matches an escape sequence within a CSS string or url() token.
    CSS_STR_ESCAPE_REGEX = re.compile(r'''(?xs)
        \\
        (
            (?P<hex> [0-9a-fA-F]{1,6})
            [ \t\n]?
            |
            (?P<ch> .)
        )
    ''')

    def __init__(self, *args):
        super().__init__(*args)
        self.url_stack = []


    def write(self, buffer, resource_list: list[UrlResource | ContentResource]):
        self._write_urls_first(buffer, resource_list)


    def _write_content(self, buffer, resource_sublist: Iterable[ContentResource]):
        buffer.write('<style>')
        for res in resource_sublist:
            buffer.write('\n')
            buffer.write(self._embed(self.build_params.resource_base_url, res.content))
        buffer.write('\n</style>')


    def _push_url(self, url):
        if url in self.url_stack:
            self.build_params.progress.error(
                NAME, msg = f'Cycle in stylesheet "@import"s, involving "{url}".')
            return False

        self.url_stack.append(url)
        return True


    def _write_url(self, buffer, res: UrlResource):
        if res.to_embed:
            self.build_params.progress.progress(NAME, msg = f'embedding {res.url}')
            add_local_dependency(res.url, self.build_params)
            is_remote, content_bytes, _ = resources.read_url(res.url,
                                                             self.build_params.fetch_cache,
                                                             self.build_params.progress)

            content = (content_bytes or b'').decode()
            if self._push_url(res.url):
                content = self._embed(res.url, content)
                self.url_stack.pop()
            buffer.write(f'<style>\n{content}\n</style>')

        else:
            href = html.escape(res.url)
            integrity = res.integrity_attr()
            buffer.write(f'<link rel="stylesheet" href="{href}"{integrity} />')


    def _embed(self, base_url: str, css: str):
        # Note 1
        # ------
        # CSS '@import's will be dealt with by encoding the imported stylesheet as a data URL (just
        # as for other external resources). This is not great from a space-efficiency POV, because
        # it can lead to nested base64 encodings. Each layer of base64 encoding will increase the
        # size by 1/3.
        #
        # It's _tempting_ to take '@import's and embed their content directly in the current
        # stylesheet. Unfortunately, this is not _quite_ semantically identical to an @import, for
        # reasons to do with rule ordering and namespaces
        # (https://www.w3.org/TR/css-cascade-5/#at-import).
        #
        # (The CSS 4 draft contains src() (https://www.w3.org/TR/css-values-4/#funcdef-src), which
        # may provide another way to avoid nested base64 encoding. We could extract all the data
        # URLs, assign them to CSS variables, and refer back to them with src(--var) (which we
        # cannot do with url()). However, as of Jan 2023, CSS 4 remains a draft and presumably not
        # well supported.)

        # Note 2
        # ------
        # Using cssutils (https://pypi.org/project/cssutils/; https://cssutils.readthedocs.io)
        # seemed like a good idea at first, but its API is quite complex for the task we have, and
        # yet lacks any mechanism for finding URLs (i.e., we'd still need string searching). Regexes
        # are cruder, but simpler here, and there's nothing that ought to trip us up.

        # Note 3
        # ------
        # Under CSS 4, it seems possible to make a URL using a complex expression involving
        # variables, functions and string concatenation, by using src(). If so, we'll have to give
        # up on embedding such resources (using regexes, anyway).

        css = css.strip()
        with io.StringIO() as buf:
            while len(css) > 0:
                # Look for comments and strings (outside of a URL/import context). We need to
                # explicitly skip over them, since we don't want to go looking for URLs inside them.
                comment_match = self.CSS_COMMENT_REGEX.match(css)
                if comment_match:
                    css = css[comment_match.end():]
                    continue

                str_match = self.CSS_STRING_REGEX.match(css)
                if str_match:
                    buf.write(str_match.group())  # Retain the actual string in the output
                    css = css[str_match.end():]
                    continue

                # Normalise
                newline_match = self.CSS_NEWLINE_REGEX.match(css)
                if newline_match:
                    buf.write('\n')  # One newline only
                    css = css[newline_match.end():]
                    continue

                # Look for url(), src() and @import.
                match = self.CSS_URL_REGEX.match(css) or self.CSS_IMPORT_REGEX.match(css)
                if match:
                    g = match.groupdict()
                    url = g.get('url') or g.get('str')
                    assert url is not None
                    # CSS_URL_REGEX has 'url' and 'str' groups. CSS_IMPORT_REGEX has only 'str'.

                    # Translate escapes in original URL
                    def escape_repl(m):
                        ch = m.group("ch")
                        return ch if ch else chr(int(m.group('hex'), base=16))
                    url = self.CSS_STR_ESCAPE_REGEX.sub(escape_repl, url)

                    if url.startswith('data:') or url.startswith('#'):
                        # Data URLs are already embedded, and so are fragment URLs (implicitly).
                        buf.write(match.group())

                    else:
                        url = urllib.parse.urljoin(base_url, url)

                        if self.build_params.embed_rule(
                                url = url,
                                tag = 'style',
                                mime = mimetypes.guess_type(url)[0],  # maybe None
                                attr = None):

                            # Grab the URL content and make a Data URL (checking for cycles).
                            if self._push_url(url):
                                add_local_dependency(url, self.build_params)
                                url = make_data_url(url, None, self.build_params, self._convert)
                                self.url_stack.pop()

                        # Escape URL. Data URLs shouldn't need this, but no guarantees about
                        # non-data URLs.
                        url = (url.replace('\\', '\\\\')
                                  .replace('"', '\\"')
                                  .replace('\n', '\\\n'))

                        if match.group().startswith('@import'):
                            # Don't terminate with ';', because we haven't taken ';' from the input
                            # yet.
                            buf.write(f'@import "{url}"')
                        else:
                            buf.write(f'url("{url}")')

                    css = css[match.end():]
                    continue

                # Nothing else matched, so just skip over one character.
                buf.write(css[0])
                css = css[1:]

            return buf.getvalue()


    def _convert(self, base_url: str, content_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
        if mime_type == 'text/css':
            # If we're sure the URL points to a stylesheet, then it may have its own external
            # resources, and we must embed those too.
            content_bytes = self._embed(base_url, content_bytes.decode(errors = 'ignore')).encode()

        elif mime_type in ['font/ttf', 'font/otf']:
            # We'll take this opportunity to convert any embedded TTF resources into WOFF2 format,
            # and strip out unused glyphs (or at least ones that don't map to any code points in
            # our list).
            #
            # Both of these things should save us some space. (WOFF2 isn't supported by IE, but
            # that's a sacrifice I'm willing to make.)

            cache_key = ('ttf-to-woff2',
                         content_bytes,
                         frozenset(self.build_params.font_codepoints))
            if cache_key in self.build_params.build_cache:
                self.build_params.progress.cache_hit(NAME, resource = 'font conversion/subsetting')
                content_bytes = self.build_params.build_cache[cache_key]

            else:
                self.build_params.progress.progress(NAME, msg = 'Converting and subsetting font')
                subsetter = fontTools.subset.Subsetter()
                subsetter.populate(unicodes = self.build_params.font_codepoints)

                font = fontTools.ttLib.TTFont(io.BytesIO(content_bytes))
                font.flavor = 'woff2'
                subsetter.subset(font)

                buf = io.BytesIO()
                font.save(buf)
                content_bytes = buf.getvalue()
                self.build_params.build_cache[cache_key] = content_bytes

            mime_type = 'font/woff2'

        return (content_bytes, mime_type)




class ScriptWriter(ResourceWriter):

    def write(self, buffer, resource_list: list[UrlResource | ContentResource]):
        self._write_in_order(buffer, resource_list)

    def _write_content(self, buffer, resource_sublist: Iterable[ContentResource]):
        buffer.write('<script>\n')
        try:
            for resource in resource_sublist:
                assert isinstance(resource, ContentResource)
                buffer.write(self._embed(self.build_params.resource_base_url, resource.content))
                buffer.write('\n')
        finally:
            buffer.write('\n</script>')

    def _write_url(self, buffer, res: UrlResource):
        if res.to_embed:
            self.build_params.progress.progress(NAME, msg = f'embedding {res.url}')
            add_local_dependency(res.url, self.build_params)
            _, content_bytes, _ = resources.read_url(res.url,
                                                     self.build_params.fetch_cache,
                                                     self.build_params.progress)

            content = self._embed(self.build_params.resource_base_url,
                                  (content_bytes or b'').decode())
            buffer.write(f'<script>\n{content}\n</script>')

        else:
            src = html.escape(res.url)
            integrity = res.integrity_attr()
            buffer.write(f'<script src="{src}"{integrity}></script>')

    def _embed(self, base_url: str, js: str):
        # TODO: to the extent that we can, we should find all external resources (particularly
        # other .js files) mentioned in the script, and embed them somehow. We may need to defer to
        # webpack, possibly https://github.com/django-webpack/django-webpack-loader.
        return js


# The following is the set of HTML elements that (potentially) specify a remote URL with their
# src=... attribute.
#
# Notes:
# <embed> invokes external plugins, which are rare now, but it's part of the standard.
# <script> is unlikely to occur here, since we have a separate process for embedding scripts, but
#     it's still legal.
# <input>  can display a (remote) image using src=... (for type="image" controls)
# <frame>  is omitted, because it is formally obsolete as of HTML 5.
# <style>  is omitted, because it cannot take a src= attribute.
# <link>   is omitted, because it can only legally occur inside <head>.
#
URL_ELEMENTS = {'audio', 'embed', 'iframe', 'img', 'input', 'script', 'source', 'track', 'video'}


# The following is a subset of the above that specify the mime type with a type=... attribute.
#
# Notes:
# <img>, <audio> and <video> (maybe surprisingly) don't have a type attribute. You can embed a
#     <source> inside <picture>, <audio> or <video> to specify a mime type if needed.
# <script> has a type attribute, but might sometimes be a mime type, but also has special values
#     representing the script's role ('module', 'importmap', etc.). Given that a script is already
#     a highly-specialised resource, we're not going to worry about its mime type.
# <input> has a type attribute, but it specifies the class of UI control, not a mime type.
#
URL_MIMETYPE_ELEMENTS = {'embed', 'source'}


def embed_media(root_element, base_url: str, build_params: BuildParams):

    for element in root_element.iter():
        if element.tag in URL_ELEMENTS:
            src = element.get('src')
            if src is not None and not src.startswith('data:') and not src.startswith('#'):

                src = urllib.parse.urljoin(base_url, src)

                mime_type = None
                if element.tag in URL_MIMETYPE_ELEMENTS:
                    mime_type = element.get('type')

                if build_params.embed_rule(
                        url = src,
                        tag = element.tag,
                        mime = mime_type or mimetypes.guess_type(src)[0],  # maybe None
                        attr = element.attrib):

                    build_params.progress.progress(
                        NAME,
                        msg = f'embedding {base_url or element.get("src") or f"<{element.tag}>"}')
                    add_local_dependency(src, build_params)
                    element.set('src', make_data_url(src, mime_type, build_params))

                else:
                    element.set('src', src)
