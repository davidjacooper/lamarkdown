import unittest

import markdown
from lamarkdown.ext import sections

import re
from textwrap import dedent


class PybtexTestCase(unittest.TestCase):
    
    REFERENCES = r'''
        @article{refA,
            author = "The Author A",
            title = "The Title A",
            journal = "The Journal A",
            year = "1990"
        }
        @article{refB,
            author = "The Author B",
            title = "The Title B",
            journal = "The Journal B",
            year = "1991"
        }
        @article{refC,
            author = "The Author C",
            title = "The Title C",
            journal = "The Journal C",
            year = "1992"
        }
        @article{refD,
            author = "The Author D",
            title = "The Title D",
            journal = "The Journal D",
            year = "1993"
        }
        @article{refE,
            author = "The Author E",
            title = "The Title E",
            journal = "The Journal E",
            year = "1994"
        }
    '''

    def run_markdown(self, markdown_text, **kwargs):
        md = markdown.Markdown(
            extensions = ['lamarkdown.ext.pybtex'],
            extension_configs = {'lamarkdown.ext.pybtex':
            {
                **kwargs
            }}
        )
        return md.convert(dedent(markdown_text).strip())
    
    
    def test_unused(self):
        html = self.run_markdown(
            r'''
            # Heading
            '''
        )
        
        self.assertRegex(
            html,
            r'''(?sx)
            \s* <h1>Heading</h1>
            '''
        )
        
        
    def test_not_mangling_other_things(self):
        # Check standard link and image syntax to make sure it still works. The Pymtex extension 
        # should avoid matching:
        # [user@refA.com]             - '@' must come after a non-word character.
        # [@refA](http://example.com) - [...] must not be followed by '('.
        # [@refA][1]                  - [...] must not be followed by '['.
        # ![@refA](image.jpg)         - [...] must not be preceeded by '!' (or followed by '(').
        #
        # It _should_ match [@refE]. That's there to ensure the extension is actually running.
        
        html = self.run_markdown(
            r'''
            [user@refA.com]
            [@refA](http://example.com)
            [@refA][1]
            ![@refA](image.jpg)
            [@refE]
            [1]: http://example.com
            ''',
            file = [],
            references = self.REFERENCES)
            
        self.assertRegex(
            html,
            r'''(?sx)
            \s* <p>\[user@refA\.com]
            \s* <a[ ]href="http://example.com">@refA</a>
            \s* <a[ ]href="http://example.com">@refA</a>
            \s* <img[ ]alt="@refA"[ ]src="image\.jpg"\s*/?>
            \s* <cite>.*</cite>
            \s* </p>
            .*
            ''')
        
        
    def test_non_matching_citations(self):
        
        # Here, @refX doesn't match anything in the reference database, and we want to retain the 
        # literal text instead.
        html = self.run_markdown(
            r'''
            # Heading

            Citation B [@refB], citation X [@refX].
            ''',
            file = [],
            references = self.REFERENCES,
            hyperlinks = 'none')
        
        self.assertRegex(
            html,
            r'''(?sx)
            \s* <h1>Heading</h1>
            \s* <p>Citation[ ]B[ ]<cite>\[<span[ ]id="pybtexcite:1-1">1</span>]</cite>,[ ]citation[ ]X[ ]\[@refX].</p>
            \s* <dl[ ]id="la-bibliography"> 
            \s* <dt[ ]id="pybtexref:1">1</dt> \s* <dd> .* \. </dd>
            \s* </dl>
            \s*
            '''
        )
        

    def test_links(self):
        linked_citations = r'''
            \s* <p>Citation[ ]B[ ]<cite>\[<a[ ]href="\#pybtexref:1"[ ]id="pybtexcite:1-1">1</a>,[ ]p\.[ ]5\]</cite>,[ ]
                   citation[ ]C[ ]<cite>\[<a[ ]href="\#pybtexref:2"[ ]id="pybtexcite:2-1">2</a>\]</cite>.</p>
            \s* <p>Citation[ ]D[ ]<cite>\[<a[ ]href="\#pybtexref:3"[ ]id="pybtexcite:3-1">3</a>[ ]maybe\]</cite>,[ ]
                   citation[ ]B[ ]<cite>\[<a[ ]href="\#pybtexref:1"[ ]id="pybtexcite:1-2">1</a>\]</cite>.</p>
        '''
        
        unlinked_citations = r'''
            \s* <p>Citation[ ]B[ ]<cite>\[<span[ ]id="pybtexcite:1-1">1</span>,[ ]p\.[ ]5\]</cite>,[ ]
                   citation[ ]C[ ]<cite>\[<span[ ]id="pybtexcite:2-1">2</span>\]</cite>.</p>
            \s* <p>Citation[ ]D[ ]<cite>\[<span[ ]id="pybtexcite:3-1">3</span>[ ]maybe\]</cite>,[ ]
                   citation[ ]B[ ]<cite>\[<span[ ]id="pybtexcite:1-2">1</span>\]</cite>.</p>
        '''
        
        linked_refs = r'''
            \s* <dt[ ]id="pybtexref:1">1</dt> \s* <dd> .* [ ]<span>↩[ ]<a[ ]href="\#pybtexcite:1-1">1</a>
                                                                    [ ]<a[ ]href="\#pybtexcite:1-2">2</a></span></dd>
            \s* <dt[ ]id="pybtexref:2">2</dt> \s* <dd> .* [ ]<a[ ]href="\#pybtexcite:2-1">↩</a></dd>
            \s* <dt[ ]id="pybtexref:3">3</dt> \s* <dd> .* [ ]<a[ ]href="\#pybtexcite:3-1">↩</a></dd>
        '''

        unlinked_refs = r'''
            \s* <dt[ ]id="pybtexref:1">1</dt> \s* <dd> .* \. </dd>
            \s* <dt[ ]id="pybtexref:2">2</dt> \s* <dd> .* \. </dd>
            \s* <dt[ ]id="pybtexref:3">3</dt> \s* <dd> .* \. </dd>
        '''
        
        data = [('both',    linked_citations,   linked_refs),
                ('forward', linked_citations,   unlinked_refs),
                ('back',    unlinked_citations, linked_refs),
                ('none',    unlinked_citations, unlinked_refs)]
        
        for hyperlinks, cite_regex, ref_regex in data:
            html = self.run_markdown(
                r'''
                # Heading

                Citation B [@refB, p. 5], citation C [@refC].
                
                Citation D [@refD maybe], citation B [@refB].
                ''',
                file = [],
                references = self.REFERENCES,
                hyperlinks = hyperlinks)
                
            self.assertRegex(
                html,
                fr'''(?sx)
                \s* <h1>Heading</h1>
                {cite_regex}
                \s* <dl[ ]id="la-bibliography"> 
                {ref_regex}
                \s* </dl>
                \s*
                '''
            )
            
            
    def test_placeholder(self):
        src_place_marker = r'///References Go Here///'
        src_citation_b = r'Citation B [@refB].'
        src_citation_c = r'Citation C [@refC].'
        
        regex_references = r'''
            \s* <dl[ ]id="la-bibliography">
            \s* <dt[ ]id="pybtexref:1">1</dt> \s* <dd> .* \. </dd>
            \s* <dt[ ]id="pybtexref:2">2</dt> \s* <dd> .* \. </dd>
            \s* </dl>
        '''
        
        regex_citation_b = r'\s* <p>Citation[ ]B[ ]<cite>\[<span[ ]id="pybtexcite:1-1">1</span>]</cite>.</p>'
        regex_citation_c = r'\s* <p>Citation[ ]C[ ]<cite>\[<span[ ]id="pybtexcite:2-1">2</span>]</cite>.</p>'
        
        # We're testing different placements of the 'place marker, which determines 
        data = [
            (
                # Marker at start
                src_place_marker + '\n\n' + src_citation_b + '\n\n' + src_citation_c,
                fr'''(?sx)
                    {regex_references}
                    {regex_citation_b}
                    {regex_citation_c}
                    \s*
                '''
            ),
            (
                # Marker in the middle
                src_citation_b + '\n\n' + src_place_marker + '\n\n' + src_citation_c,
                fr'''(?sx)
                    {regex_citation_b}
                    {regex_references}
                    {regex_citation_c}
                    \s*
                '''
            ),
            (
                # Marker at end
                src_citation_b + '\n\n' + src_citation_c + '\n\n' + src_place_marker,
                fr'''(?sx)
                    {regex_citation_b}
                    {regex_citation_c}
                    {regex_references}
                    \s*
                '''
            ),
            (
                # Marker missing -- should be the same as if it was at the end.
                src_citation_b + '\n\n' + src_citation_c,
                fr'''(?sx)
                    {regex_citation_b}
                    {regex_citation_c}
                    {regex_references}
                    \s*
                '''
            )
        ]
            
        for markdown, regex in data:        
            html = self.run_markdown(
                markdown,
                file = [],
                references = self.REFERENCES,
                hyperlinks = 'none')
            
            self.assertRegex(html, regex)
            
    
    def test_multipart_citations(self):
        html = self.run_markdown(
            r'''
            Citation B [see @refB, p. 5; @refC maybe; not @refX].
            ''',
            file = [],
            references = self.REFERENCES,
            hyperlinks = 'none')
        
        self.assertRegex(
            html, 
            r'''(?sx)
            \s* <p>Citation[ ]B[ ]<cite>\[see[ ]
                <span[ ]id="pybtexcite:1-1">1</span>,[ ]p\.[ ]5;[ ]
                <span[ ]id="pybtexcite:2-1">2</span>[ ]maybe;[ ]not[ ]@refX\]</cite>.</p>
            \s* <dl[ ]id="la-bibliography"> 
            \s* <dt[ ]id="pybtexref:1">1</dt> \s* <dd> .* \. </dd>
            \s* <dt[ ]id="pybtexref:2">2</dt> \s* <dd> .* \. </dd>
            \s* </dl>
            \s*
            ''')


    def test_citation_key_syntax(self):
        pass
