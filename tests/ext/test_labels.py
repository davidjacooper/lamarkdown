from ..util.markdown_ext import entry_point_cls
import lamarkdown.ext

import unittest
from unittest.mock import patch
from hamcrest import assert_that, instance_of, is_, same_instance

import markdown

import io
import sys
from textwrap import dedent

sys.modules['la'] = sys.modules['lamarkdown.ext']


class LabelsTestCase(unittest.TestCase):

    def run_markdown(self,
                     markdown_text,
                     more_extensions = [],
                     expect_error = False,
                     **kwargs):

        md = markdown.Markdown(
            extensions = ['la.labels', *more_extensions],
            extension_configs = {'la.labels': kwargs}
        )
        return md.convert(dedent(markdown_text).strip())


    HEADING_TESTDATA = r'''
        # Section 1
        ## Section 1.1
        ## Section 1.2
        ## Section 1.3
        # _Section_ 2
        ## **Section** 2.1
        ### Section 2.1.1
        #### Section 2.1.1.1
        ##### Section 2.1.1.1.1
        ###### Section 2.1.1.1.1.1
        ## Section 2.2
    '''

    def test_default_headings(self):

        html = self.run_markdown(self.HEADING_TESTDATA)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1>Section[ ]1</h1>
            \s* <h2>Section[ ]1.1</h2>
            \s* <h2>Section[ ]1.2</h2>
            \s* <h2>Section[ ]1.3</h2>
            \s* <h1><em>Section</em>[ ]2</h1>
            \s* <h2><strong>Section</strong>[ ]2.1</h2>
            \s* <h3>Section[ ]2.1.1</h3>
            \s* <h4>Section[ ]2.1.1.1</h4>
            \s* <h5>Section[ ]2.1.1.1.1</h5>
            \s* <h6>Section[ ]2.1.1.1.1.1</h6>
            \s* <h2>Section[ ]2.2</h2>
            \s*
            '''
        )


    def test_headings_at_h1(self):

        html = self.run_markdown(self.HEADING_TESTDATA, h_labels = "H.1 ,*")

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1><span[ ]class="la-label">1[ ]</span>Section[ ]1</h1>
            \s* <h2><span[ ]class="la-label">1.1[ ]</span>Section[ ]1.1</h2>
            \s* <h2><span[ ]class="la-label">1.2[ ]</span>Section[ ]1.2</h2>
            \s* <h2><span[ ]class="la-label">1.3[ ]</span>Section[ ]1.3</h2>
            \s* <h1><span[ ]class="la-label">2[ ]</span><em>Section</em>[ ]2</h1>
            \s* <h2><span[ ]class="la-label">2.1[ ]</span><strong>Section</strong>[ ]2.1</h2>
            \s* <h3><span[ ]class="la-label">2.1.1[ ]</span>Section[ ]2.1.1</h3>
            \s* <h4><span[ ]class="la-label">2.1.1.1[ ]</span>Section[ ]2.1.1.1</h4>
            \s* <h5><span[ ]class="la-label">2.1.1.1.1[ ]</span>Section[ ]2.1.1.1.1</h5>
            \s* <h6><span[ ]class="la-label">2.1.1.1.1.1[ ]</span>Section[ ]2.1.1.1.1.1</h6>
            \s* <h2><span[ ]class="la-label">2.2[ ]</span>Section[ ]2.2</h2>
            \s*
            '''
        )

    def test_headings_at_h2(self):

        html = self.run_markdown(self.HEADING_TESTDATA, h_labels = "H.1 ,*", h_level = 2)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1>Section[ ]1</h1>
            \s* <h2><span[ ]class="la-label">1[ ]</span>Section[ ]1.1</h2>
            \s* <h2><span[ ]class="la-label">2[ ]</span>Section[ ]1.2</h2>
            \s* <h2><span[ ]class="la-label">3[ ]</span>Section[ ]1.3</h2>
            \s* <h1><em>Section</em>[ ]2</h1>
            \s* <h2><span[ ]class="la-label">1[ ]</span><strong>Section</strong>[ ]2.1</h2>
            \s* <h3><span[ ]class="la-label">1.1[ ]</span>Section[ ]2.1.1</h3>
            \s* <h4><span[ ]class="la-label">1.1.1[ ]</span>Section[ ]2.1.1.1</h4>
            \s* <h5><span[ ]class="la-label">1.1.1.1[ ]</span>Section[ ]2.1.1.1.1</h5>
            \s* <h6><span[ ]class="la-label">1.1.1.1.1[ ]</span>Section[ ]2.1.1.1.1.1</h6>
            \s* <h2><span[ ]class="la-label">2[ ]</span>Section[ ]2.2</h2>
            \s*
            '''
        )


    HEADING_DIRECTIVE_TESTDATA = r'''
        # Section 1
        ## Section 1.1
        ## Section 1.2 {::label="1."}
        ## Section 1.3
        # _Section_ 2
        ## **Section** 2.1
        ### Section 2.1.1 {::label="a.,H.i.,A.,H.I."}
        #### Section 2.1.1.1
        ##### Section 2.1.1.1.1
        ###### Section 2.1.1.1.1.1
        ## Section 2.2
    '''

    def test_headings_directive(self):

        html = self.run_markdown(
            self.HEADING_DIRECTIVE_TESTDATA,
            more_extensions = ["attr_list"]
        )

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1>Section[ ]1</h1>
            \s* <h2>Section[ ]1.1</h2>
            \s* <h2><span[ ]class="la-label">1.</span>Section[ ]1.2</h2>
            \s* <h2><span[ ]class="la-label">2.</span>Section[ ]1.3</h2>
            \s* <h1><em>Section</em>[ ]2</h1>
            \s* <h2><strong>Section</strong>[ ]2.1</h2>
            \s* <h3><span[ ]class="la-label">a.</span>Section[ ]2.1.1</h3>
            \s* <h4><span[ ]class="la-label">a.i.</span>Section[ ]2.1.1.1</h4>
            \s* <h5><span[ ]class="la-label">A.</span>Section[ ]2.1.1.1.1</h5>
            \s* <h6><span[ ]class="la-label">A.I.</span>Section[ ]2.1.1.1.1.1</h6>
            \s* <h2>Section[ ]2.2</h2>
            \s*
            '''
        )


    ORDERED_LIST_TESTDATA = r'''
        1. ItemA
            1. ItemAA
            2. ItemAB
                1. ItemABA
        2. ItemB
            1. ItemBA
                1. ItemBAA
            2. ItemBB
        3. ItemC
        4. ItemD
    '''


    def test_default_ordered_lists(self):
        html = self.run_markdown(self.ORDERED_LIST_TESTDATA)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <ol>
            \s*   <li>ItemA
            \s*       <ol>
            \s*           <li>ItemAA</li>
            \s*           <li>ItemAB
            \s*               <ol>
            \s*                   <li>ItemABA</li>
            \s*               </ol>
            \s*           </li>
            \s*       </ol>
            \s*   </li>
            \s*   <li>ItemB
            \s*       <ol>
            \s*           <li>ItemBA
            \s*               <ol>
            \s*                   <li>ItemBAA</li>
            \s*               </ol>
            \s*           </li>
            \s*           <li>ItemBB</li>
            \s*       </ol>
            \s*   </li>
            \s*   <li>ItemC</li>
            \s*   <li>ItemD</li>
            \s* </ol>
            \s*
            '''
        )


    def test_ordered_lists(self):
        html = self.run_markdown(self.ORDERED_LIST_TESTDATA, ol_labels = 'L.1 ,*')

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <ol[ ]class="la-labelled">
            \s* <li><span[ ]class="la-label">1[ ]</span>ItemA
            \s*     <ol[ ]class="la-labelled">
            \s*         <li><span[ ]class="la-label">1.1[ ]</span>ItemAA</li>
            \s*         <li><span[ ]class="la-label">1.2[ ]</span>ItemAB
            \s*             <ol[ ]class="la-labelled">
            \s*                 <li><span[ ]class="la-label">1.2.1[ ]</span>ItemABA</li>
            \s*             </ol>
            \s*         </li>
            \s*     </ol>
            \s* </li>
            \s* <li><span[ ]class="la-label">2[ ]</span>ItemB
            \s*     <ol[ ]class="la-labelled">
            \s*         <li><span[ ]class="la-label">2.1[ ]</span>ItemBA
            \s*             <ol[ ]class="la-labelled">
            \s*                 <li><span[ ]class="la-label">2.1.1[ ]</span>ItemBAA</li>
            \s*             </ol>
            \s*         </li>
            \s*         <li><span[ ]class="la-label">2.2[ ]</span>ItemBB</li>
            \s*     </ol>
            \s* </li>
            \s* <li><span[ ]class="la-label">3[ ]</span>ItemC</li>
            \s* <li><span[ ]class="la-label">4[ ]</span>ItemD</li>
            \s* </ol>
            \s*
            ''')


    def test_ordered_lists_directive(self):

        for (description, testdata, expected_regex) in [
            (
                'Basic <ol> labelling (no inheritance)',
                r'''
                {::label="-a-"}
                1. ItemA

                    1. ItemAA
                    2. ItemAB

                2. ItemB
                ''',
                r'''(?xs)
                \s* <ol[ ]class="la-labelled">
                \s*   <li><span[ ]class="la-label">-a-</span>
                \s*     <p>ItemA</p>
                \s*     <ol>
                \s*       <li>ItemAA</li>
                \s*       <li>ItemAB</li>
                \s*     </ol>
                \s*   </li>
                \s*   <li><span[ ]class="la-label">-b-</span>
                \s*     <p>ItemB</p>
                \s*   </li>
                \s* </ol>
                \s*
                '''
            ),
            (
                'Child template inheritance.',
                r'''
                {::label="-a-,-1-,-i-"}
                1. ItemA

                    1. ItemB

                        1. ItemC

                            1. ItemD
                ''',
                r'''(?xs)
                \s* <ol[ ]class="la-labelled">
                \s*   <li><span[ ]class="la-label">-a-</span>
                \s*     <p>ItemA</p>
                \s*     <ol[ ]class="la-labelled">
                \s*       <li><span[ ]class="la-label">-1-</span>
                \s*         <p>ItemB</p>
                \s*         <ol[ ]class="la-labelled">
                \s*           <li><span[ ]class="la-label">-i-</span>
                \s*             <p>ItemC</p>
                \s*             <ol>
                \s*               <li>ItemD</li>
                \s*             </ol>
                \s*           </li>
                \s*         </ol>
                \s*       </li>
                \s*     </ol>
                \s*   </li>
                \s* </ol>
                \s*
                '''
            ),
            (
                'Child template wildcard inheritance.',
                r'''
                {::label="-a-,*"}
                1. ItemA

                    1. ItemB

                        1. ItemC

                            1. ItemD
                ''',
                r'''(?xs)
                \s* <ol[ ]class="la-labelled">
                \s*   <li><span[ ]class="la-label">-a-</span>
                \s*     <p>ItemA</p>
                \s*     <ol[ ]class="la-labelled">
                \s*       <li><span[ ]class="la-label">-a-</span>
                \s*         <p>ItemB</p>
                \s*         <ol[ ]class="la-labelled">
                \s*           <li><span[ ]class="la-label">-a-</span>
                \s*             <p>ItemC</p>
                \s*             <ol[ ]class="la-labelled">
                \s*               <li><span[ ]class="la-label">-a-</span>ItemD</li>
                \s*             </ol>
                \s*           </li>
                \s*         </ol>
                \s*       </li>
                \s*     </ol>
                \s*   </li>
                \s* </ol>
                \s*
                '''
            ),
            (
                'Overridden inheritance.',
                r'''
                {::label="-a-,-1-,-i-,-a-"}
                1. ItemA

                    {::label=".A.,.I."}
                    1. ItemB

                        1. ItemC

                            1. ItemD
                ''',
                r'''(?xs)
                \s* <ol[ ]class="la-labelled">
                \s*   <li><span[ ]class="la-label">-a-</span>
                \s*     <p>ItemA</p>
                \s*     <ol[ ]class="la-labelled">
                \s*       <li><span[ ]class="la-label">.A.</span>
                \s*         <p>ItemB</p>
                \s*         <ol[ ]class="la-labelled">
                \s*           <li><span[ ]class="la-label">.I.</span>
                \s*             <p>ItemC</p>
                \s*             <ol>
                \s*               <li>ItemD</li>
                \s*             </ol>
                \s*           </li>
                \s*         </ol>
                \s*       </li>
                \s*     </ol>
                \s*   </li>
                \s* </ol>
                \s*
                '''
            ),
            (
                'Numbering resets',
                r'''
                {::label="-a-"}
                1. ItemA
                2. ItemB
                    {::label="-1-"}
                3. ItemC

                Paragraph

                1. ItemD
                ''',
                r'''(?xs)
                \s* <ol[ ]class="la-labelled">
                \s*   <li><span[ ]class="la-label">-a-</span>ItemA</li>
                \s*   <li><span[ ]class="la-label">-1-</span>ItemB</li>
                \s*   <li><span[ ]class="la-label">-2-</span>ItemC</li>
                \s* </ol>
                \s* <p>Paragraph</p>
                \s* <ol>
                \s*   <li>ItemD</li>
                \s* </ol>
                \s*
                '''
            ),
        ]:

            html = self.run_markdown(
                testdata,
                ['lamarkdown.ext.attr_prefix']
            )

            self.assertRegex(html, expected_regex, msg = description)



    MIXED_TESTDATA = r'''
        # Section1

        1. ItemA
        2. ItemB

            ## Section2

            1. ItemC

                1. ItemD

                    ### Section3

                2. ItemE

                    ### Section4
                    #### Section5
    '''

    def test_default_mixed(self):
        '''Interspersed headings and ordered lists, without any labels.'''

        html = self.run_markdown(self.MIXED_TESTDATA)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1>Section1</h1>
            \s* <ol>
            \s*   <li>ItemA</li>
            \s*   <li>
            \s*     <p>ItemB</p>
            \s*     <h2>Section2</h2>
            \s*     <ol>
            \s*       <li>
            \s*         <p>ItemC</p>
            \s*         <ol>
            \s*           <li>
            \s*             <p>ItemD</p>
            \s*             <h3>Section3</h3>
            \s*           </li>
            \s*           <li>
            \s*             <p>ItemE</p>
            \s*             <h3>Section4</h3>
            \s*             <h4>Section5</h4>
            \s*           </li>
            \s*         </ol>
            \s*       </li>
            \s*     </ol>
            \s*   </li>
            \s* </ol>
            \s*
            '''
        )


    def test_mixed(self):
        '''Interspersed headings and ordered lists, with interacting labels.'''

        html = self.run_markdown(self.MIXED_TESTDATA,
                                 h_labels = "X.A,*",
                                 h_level = 2,
                                 ol_labels = "X.1,*")

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1>Section1</h1>
            \s* <ol[ ]class="la-labelled">
            \s*   <li><span[ ]class="la-label">1</span>ItemA</li>
            \s*   <li><span[ ]class="la-label">2</span>
            \s*     <p>ItemB</p>
            \s*     <h2><span[ ]class="la-label">2.A</span>Section2</h2>
            \s*     <ol[ ]class="la-labelled">
            \s*       <li><span[ ]class="la-label">2.A.1</span>
            \s*         <p>ItemC</p>
            \s*         <ol[ ]class="la-labelled">
            \s*           <li><span[ ]class="la-label">2.A.1.1</span>
            \s*             <p>ItemD</p>
            \s*             <h3><span[ ]class="la-label">2.A.1.1.A</span>Section3</h3>
            \s*           </li>
            \s*           <li><span[ ]class="la-label">2.A.1.2</span>
            \s*             <p>ItemE</p>
            \s*             <h3><span[ ]class="la-label">2.A.1.2.A</span>Section4</h3>
            \s*             <h4><span[ ]class="la-label">2.A.1.2.A.A</span>Section5</h4>
            \s*           </li>
            \s*         </ol>
            \s*       </li>
            \s*     </ol>
            \s*   </li>
            \s* </ol>
            \s*
            '''
        )


    def test_ordered_lists_css(self):

        css = io.StringIO()
        html = self.run_markdown(self.ORDERED_LIST_TESTDATA,
                                 ol_labels = 'L.1 ,*',
                                 css_fn = css.write)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <ol[ ]class="la-labelled[ ]la-label0">
            \s* <li>ItemA
            \s*     <ol[ ]class="la-labelled[ ]la-label1">
            \s*         <li>ItemAA</li>
            \s*         <li>ItemAB
            \s*             <ol[ ]class="la-labelled[ ]la-label2">
            \s*                 <li>ItemABA</li>
            \s*             </ol>
            \s*         </li>
            \s*     </ol>
            \s* </li>
            \s* <li>ItemB
            \s*     <ol[ ]class="la-labelled[ ]la-label1">
            \s*         <li>ItemBA
            \s*             <ol[ ]class="la-labelled[ ]la-label2">
            \s*                 <li>ItemBAA</li>
            \s*             </ol>
            \s*         </li>
            \s*         <li>ItemBB</li>
            \s*     </ol>
            \s* </li>
            \s* <li>ItemC</li>
            \s* <li>ItemD</li>
            \s* </ol>
            \s*
            ''')

        # self.assertRegex(
        #     css.getvalue(),
        #     r'''(?xs)
        #     \s* \.la-labelled>li\{      list-style-type:none;                           \}
        #     \s* .la-label0\{            counter-reset:la-label0;                        \}
        #     \s* .la-label0>li:not\(\.la-no-label\)\{         counter-increment:la-label0;                    \}
        #     \s* .la-label0>li:not\(\.la-no-label\)::before\{ content:counter\(la-label0,decimal\)[ ]"[ ]";   \}
        #     \s* .la-label1\{            counter-reset:la-label1;                        \}
        #     \s* .la-label1>li:not\(\.la-no-label\)\{         counter-increment:la-label1;                    \}
        #     \s* .la-label1>li:not\(\.la-no-label\)::before\{ content:counter\(la-label0,decimal\)[ ]"."[ ]
        #                                         counter\(la-label1,decimal\)[ ]"[ ]";   \}
        #     \s* .la-label2\{            counter-reset:la-label2;                        \}
        #     \s* .la-label2>li:not\(\.la-no-label\)\{         counter-increment:la-label2;                    \}
        #     \s* .la-label2>li:not\(\.la-no-label\)::before\{ content:counter\(la-label0,decimal\)[ ]"."[ ]
        #                                         counter\(la-label1,decimal\)[ ]"."[ ]
        #                                         counter\(la-label2,decimal\)[ ]"[ ]";   \}
        #     '''
        # )

        li = r'li:not\(\.la-no-label\)'
        self.assertRegex(
            css.getvalue(),
            fr'''(?xs)
            \s* \.la-labelled>li\{{         list-style-type:none;                           \}}
            \s* \.la-label0\{{              counter-reset:la-label0;                        \}}
            \s* \.la-label0>{li}\{{         counter-increment:la-label0;                    \}}
            \s* \.la-label0>{li}::before\{{ content:counter\(la-label0,decimal\)[ ]"[ ]";   \}}
            \s* \.la-label1\{{              counter-reset:la-label1;                        \}}
            \s* \.la-label1>{li}\{{         counter-increment:la-label1;                    \}}
            \s* \.la-label1>{li}::before\{{ content:counter\(la-label0,decimal\)[ ]"."[ ]
                                                    counter\(la-label1,decimal\)[ ]"[ ]";   \}}
            \s* \.la-label2\{{              counter-reset:la-label2;                        \}}
            \s* \.la-label2>{li}\{{         counter-increment:la-label2;                    \}}
            \s* \.la-label2>{li}::before\{{ content:counter\(la-label0,decimal\)[ ]"."[ ]
                                                    counter\(la-label1,decimal\)[ ]"."[ ]
                                                    counter\(la-label2,decimal\)[ ]"[ ]";   \}}
            '''
        )


    def test_mixed_css(self):
        '''
        Interspersed headings and ordered lists, where lists are rendered in CSS, but where
        heading and list labels interact.
        '''

        css = io.StringIO()
        html = self.run_markdown(self.MIXED_TESTDATA,
                                 h_labels = "X.A,*",
                                 h_level = 2,
                                 ol_labels = "X.1,*",
                                 css_fn = css.write)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1>Section1</h1>
            \s* <ol[ ]class="la-labelled[ ]la-label0">
            \s*   <li>ItemA</li>
            \s*   <li>
            \s*     <p>ItemB</p>
            \s*     <h2><span[ ]class="la-label">2.A</span>Section2</h2>
            \s*     <ol[ ]class="la-labelled[ ]la-label1">
            \s*       <li>
            \s*         <p>ItemC</p>
            \s*         <ol[ ]class="la-labelled[ ]la-label2">
            \s*           <li>
            \s*             <p>ItemD</p>
            \s*             <h3><span[ ]class="la-label">2.A.1.1.A</span>Section3</h3>
            \s*           </li>
            \s*           <li>
            \s*             <p>ItemE</p>
            \s*             <h3><span[ ]class="la-label">2.A.1.2.A</span>Section4</h3>
            \s*             <h4><span[ ]class="la-label">2.A.1.2.A.A</span>Section5</h4>
            \s*           </li>
            \s*         </ol>
            \s*       </li>
            \s*     </ol>
            \s*   </li>
            \s* </ol>
            \s*
            '''
        )

        # self.assertRegex(
        #     css.getvalue(),
        #     r'''(?xs)
        #     \s* \.la-labelled>li\{
        #         list-style-type:none; \}
        #     \s* \.la-label0\{
        #         counter-reset:la-label0; \}
        #     \s* \.la-label0>li:not\(\.la-no-label\)\{
        #         counter-increment:la-label0; \}
        #     \s* \.la-label0>li:not\(\.la-no-label\)::before\{
        #         content:counter\(la-label0,decimal\); \}
        #     \s* \.la-label1\{
        #         counter-reset:la-label1; \}
        #     \s* \.la-label1>li:not\(\.la-no-label\)\{
        #         counter-increment:la-label1; \}
        #     \s* \.la-label1>li:not\(\.la-no-label\)::before\{
        #         content:"2\.A"[ ]"\."[ ]counter\(la-label1,decimal\); \}
        #     \s* \.la-label2\{
        #         counter-reset:la-label2; \}
        #     \s* \.la-label2>li:not\(\.la-no-label\)\{
        #         counter-increment:la-label2; \}
        #     \s* \.la-label2>li:not\(\.la-no-label\)::before\{
        #         content:"2\.A"[ ]"\."[ ]counter\(la-label1,decimal\)[ ]"\."[ ]
        #                                 counter\(la-label2, decimal\); \}
        #     '''
        # )

        li = r'li:not\(\.la-no-label\)'
        self.assertRegex(
            css.getvalue(),
            fr'''(?xs)
            \s* \.la-labelled>li\{{         list-style-type:none;                   \}}
            \s* \.la-label0\{{              counter-reset:la-label0;                \}}
            \s* \.la-label0>{li}\{{         counter-increment:la-label0;            \}}
            \s* \.la-label0>{li}::before\{{ content:counter\(la-label0,decimal\);   \}}
            \s* \.la-label1\{{              counter-reset:la-label1;                \}}
            \s* \.la-label1>{li}\{{         counter-increment:la-label1;            \}}
            \s* \.la-label1>{li}::before\{{ content:"2\.A"[ ]"\."[ ]
                                            counter\(la-label1,decimal\);           \}}
            \s* \.la-label2\{{              counter-reset:la-label2;                \}}
            \s* \.la-label2>{li}\{{         counter-increment:la-label2;            \}}
            \s* \.la-label2>{li}::before\{{ content:"2\.A"[ ]"\."[ ]
                                            counter\(la-label1,decimal\)[ ]"\."[ ]
                                            counter\(la-label2, decimal\);          \}}
            '''
        )


    UNORDERED_LIST_TESTDATA = r'''
        * ItemA
            * ItemAA
            * ItemAB
                * ItemABA
        * ItemB
            * ItemBA
                * ItemBAA
            * ItemBB
        * ItemC
        * ItemD
    '''


    def test_unordered_list_default(self):

        html = self.run_markdown(self.UNORDERED_LIST_TESTDATA)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <ul>
            \s*   <li>ItemA
            \s*       <ul>
            \s*           <li>ItemAA</li>
            \s*           <li>ItemAB
            \s*               <ul>
            \s*                   <li>ItemABA</li>
            \s*               </ul>
            \s*           </li>
            \s*       </ul>
            \s*   </li>
            \s*   <li>ItemB
            \s*       <ul>
            \s*           <li>ItemBA
            \s*               <ul>
            \s*                   <li>ItemBAA</li>
            \s*               </ul>
            \s*           </li>
            \s*           <li>ItemBB</li>
            \s*       </ul>
            \s*   </li>
            \s*   <li>ItemC</li>
            \s*   <li>ItemD</li>
            \s* </ul>
            \s*
            '''
        )

    def test_unordered_list(self):

        html = self.run_markdown(self.UNORDERED_LIST_TESTDATA,
                                 ul_labels = '@@,:::')

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <ul[ ]class="la-labelled">
            \s*   <li><span[ ]class="la-label">@@</span>ItemA
            \s*       <ul[ ]class="la-labelled">
            \s*           <li><span[ ]class="la-label">:::</span>ItemAA</li>
            \s*           <li><span[ ]class="la-label">:::</span>ItemAB
            \s*               <ul>
            \s*                   <li>ItemABA</li>
            \s*               </ul>
            \s*           </li>
            \s*       </ul>
            \s*   </li>
            \s*   <li><span[ ]class="la-label">@@</span>ItemB
            \s*       <ul[ ]class="la-labelled">
            \s*           <li><span[ ]class="la-label">:::</span>ItemBA
            \s*               <ul>
            \s*                   <li>ItemBAA</li>
            \s*               </ul>
            \s*           </li>
            \s*           <li><span[ ]class="la-label">:::</span>ItemBB</li>
            \s*       </ul>
            \s*   </li>
            \s*   <li><span[ ]class="la-label">@@</span>ItemC</li>
            \s*   <li><span[ ]class="la-label">@@</span>ItemD</li>
            \s* </ul>
            \s*
            '''
        )


    def test_unordered_list_css(self):

        css = io.StringIO()
        html = self.run_markdown(self.UNORDERED_LIST_TESTDATA,
                                 ul_labels = '@@,:::',
                                 css_fn = css.write)

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <ul[ ]class="la-labelled[ ]la-label0">
            \s*   <li>ItemA
            \s*       <ul[ ]class="la-labelled[ ]la-label1">
            \s*           <li>ItemAA</li>
            \s*           <li>ItemAB
            \s*               <ul>
            \s*                   <li>ItemABA</li>
            \s*               </ul>
            \s*           </li>
            \s*       </ul>
            \s*   </li>
            \s*   <li>ItemB
            \s*       <ul[ ]class="la-labelled[ ]la-label1">
            \s*           <li>ItemBA
            \s*               <ul>
            \s*                   <li>ItemBAA</li>
            \s*               </ul>
            \s*           </li>
            \s*           <li>ItemBB</li>
            \s*       </ul>
            \s*   </li>
            \s*   <li>ItemC</li>
            \s*   <li>ItemD</li>
            \s* </ul>
            \s*
            '''
        )

        self.assertRegex(
            css.getvalue(),
            r'''(?xs)
            \s* \.la-labelled>li\{list-style-type:none;\}
            \s* \.la-label0>li:not\(\.la-no-label\)::before\{content:"@@";\}
            \s* \.la-label1>li:not\(\.la-no-label\)::before\{content:":::";\}
            '''
        )


    def test_no_label_headings(self):
        html = self.run_markdown(
            r'''
            # HeadingA {::label="1.,*"}
            # HeadingB
            # HeadingC {::no-label}
            # HeadingD
            # HeadingE {::no-label}
            # HeadingF {::no-label}
            # HeadingG
            # HeadingH {::label="I."}
            # HeadingI {::no-label}
            # HeadingJ
            ''',
            more_extensions = ["attr_list"]
        )

        self.assertRegex(
            html,
            r'''(?xs)
            \s* <h1><span[ ]class="la-label">1.</span>HeadingA</h1>
            \s* <h1><span[ ]class="la-label">2.</span>HeadingB</h1>
            \s* <h1>HeadingC</h1>
            \s* <h1><span[ ]class="la-label">3.</span>HeadingD</h1>
            \s* <h1>HeadingE</h1>
            \s* <h1>HeadingF</h1>
            \s* <h1><span[ ]class="la-label">4.</span>HeadingG</h1>
            \s* <h1><span[ ]class="la-label">I.</span>HeadingH</h1>
            \s* <h1>HeadingI</h1>
            \s* <h1><span[ ]class="la-label">II.</span>HeadingJ</h1>
            ''')


    def test_extension_setup(self):
        assert_that(
            entry_point_cls('la.labels'),
            same_instance(lamarkdown.ext.labels.LabelsExtension))

        instance = lamarkdown.ext.labels.makeExtension(h_labels = 'mock_label_template')

        assert_that(
            instance,
            instance_of(lamarkdown.ext.labels.LabelsExtension))

        assert_that(
            instance.getConfig('h_labels'),
            is_('mock_label_template'))

        class MockBuildParams:
            def __getattr__(self, name):
                raise ModuleNotFoundError

        with patch('lamarkdown.lib.build_params.BuildParams', MockBuildParams()):
            instance = lamarkdown.ext.labels.makeExtension()
