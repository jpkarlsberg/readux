# methods for generating annotated tei
from eulxml.xmlmap import load_xmlobject_from_string, teimap
import logging
from lxml import etree
import mistune
from readux.books.models import TeiZone, TeiNote, TeiAnchor


logger = logging.getLogger(__name__)


def annotated_tei(tei, annotations):
    # iterate throuth the annotations associated with this volume
    # and insert them into the tei based on the content they reference

    # perhaps some sanity-checking: compare annotation total vs
    # number actually added as we go page-by-page?

    # create an annotation div for annotation content
    tei.create_body()
    annotation_div = teimap.TeiDiv(type='annotations')
    tei.body.div.append(annotation_div)

    for page in tei.page_list:
        page_annotations = annotations.filter(extra_data__contains=page.id)
        if page_annotations.exists():
            for note in page_annotations:
                insert_note(annotation_div, page, note)

    return tei


def annotation_to_tei(annotation):
    'Generate a tei note from an annotation'
    # needs to handle formatting, tags, etc

    # TODO: tags
    # should we include annotation created/edited dates?

    # sample note provided by Alice
    # <note resp="JPK" xml:id="oshnp50n1" n="1"><p>This is an example note.</p></note>

    # convert markdown-formatted text content to tei
    note_content = markdown_to_tei(annotation.text)
    # markdown results could be a list of paragraphs, and not a proper
    # xml tree; also, pags do not include namespace
    # wrap in a note element and set the default namespace as tei
    teinote = load_xmlobject_from_string('<note xmlns="%s">%s</note>' % \
        (teimap.TEI_NAMESPACE, note_content),
        TeiNote)

    # what id do we want? annotation uuid? url?
    teinote.id = 'annotation-%s' % annotation.id  # can't start with numeric
    teinote.type = 'annotation'

    # if the annotation has an associated user, mark the author
    # as responsible for the note
    if annotation.user:
        teinote.resp = annotation.user.username

    return teinote

def html_xpath_to_tei(xpath):
    # convert xpaths generated on the readux site to the
    # equivalent xpaths for the corresponding tei content
    return xpath.replace('div', 'tei:zone') \
                .replace('span', 'tei:w') \
                .replace('@id', '@xml:id')

def insert_note(annotation_div, teipage, annotation):

    info = annotation.info()
    # convert html xpaths to tei
    if info['ranges']:
        # NOTE: assuming a single range selection for now
        # the annotator model supports multiple, but UI does not currently
        # support it.
        selection_range = info['ranges'][0]
        # convert html xpaths from readux website to equivalent tei xpaths
        # for selection within the facsimile document
        start_xpath = html_xpath_to_tei(selection_range['start'])
        end_xpath = html_xpath_to_tei(selection_range['end'])
        # insert references using start and end xpaths & offsets
        start = teipage.node.xpath(start_xpath, namespaces=TeiZone.ROOT_NAMESPACES)
        end = teipage.node.xpath(end_xpath, namespaces=TeiZone.ROOT_NAMESPACES)
        if not start or not end:
            logger.warn('Could not find start or end xpath for annotation %s' % annotation.id)
            return
        else:
            # xpath returns a list of matches; we only want the first one
            start = start[0]
            end = end[0]

        start_anchor = TeiAnchor(type='text-annotation-highlight-start',
            id='highlight-start-%s' % annotation.id)
        end_anchor = TeiAnchor(type='text-annotation-highlight-end',
            id='highlight-end-%s' % annotation.id)

        # insert the end *first* in case start and end are in the
        # same element; otherwise, the offsets get mixed up
        insert_anchor(end, end_anchor.node, selection_range['endOffset'])
        insert_anchor(start, start_anchor.node, selection_range['startOffset'])

        # generate range target for the note element
        target = '#range(#%s, #%s)' % (start_anchor.id, end_anchor.id)

    elif 'image_selection' in info:
        # for readux, image annotation can *only* be the page image
        # so not checking image uri
        page_width = teipage.lrx - teipage.ulx
        page_height = teipage.lry - teipage.uly

        # create a new zone for the image highlight
        image_highlight = TeiZone(type="image-annotation-highlight")
        # image selection in annotation stored as percentages
        # convert ##% into a float that can be multiplied by page dimensions
        selection = {
            'x': float(info['image_selection']['x'].rstrip('%')) / 100,
            'y': float(info['image_selection']['y'].rstrip('%')) / 100,
            'w': float(info['image_selection']['w'].rstrip('%')) / 100,
            'h': float(info['image_selection']['h'].rstrip('%')) / 100
        }

        # convert percentages into upper left and lower right coordinates
        # relative to the page
        image_highlight.ulx = selection['x'] * float(page_width)
        image_highlight.uly = selection['y'] * float(page_height)
        image_highlight.lrx = image_highlight.ulx + (selection['w'] * page_width)
        image_highlight.lry = image_highlight.uly + (selection['h'] * page_height)

        image_highlight.id = 'highlight-%s' % annotation.id
        target = '#%s' % image_highlight.id

        teipage.node.append(image_highlight.node)

    # call annotation_to_tei and insert the resulting note into
    # the appropriate part of the document
    teinote = annotation_to_tei(annotation)
    teinote.target = target
    # actual annotation should be added to the text, outside facsimile
    annotation_div.node.append(teinote.node)


def insert_anchor(el, anchor, offset):
    # insert an anchor into an element at a given offset
    if offset == 0:
        # offset zero - insert directly before this element
        el.addprevious(anchor)
    elif offset >= len(el.text):
        # offset at end of this element - insert directly after
        el.addnext(anchor)
    else:
        # offset somewhere inside the text of this element
        # insert the element after the text and then break up
        # the lxml text and "tail" so that text after the offset
        # comes after the inserted anchor
        el_text = el.text
        el.insert(0, anchor)
        el.text = el_text[:offset]
        anchor.tail = el_text[offset:]


def markdown_to_tei(text):
    'Render markdown text as simple TEI'
    # does not include namespace or wrapping elment
    mkdown = mistune.Markdown(renderer=TeiMarkdownRenderer())
    return mkdown(text)


class TeiMarkdownRenderer(mistune.Renderer):

    def __init__(self, **kwargs):
        self.options = kwargs

    # def placeholder(self):
    #     """Returns the default, empty output value for the renderer.
    #     All renderer methods use the '+=' operator to append to this value.
    #     Default is a string so rendering HTML can build up a result string with
    #     the rendered Markdown.
    #     Can be overridden by Renderer subclasses to be types like an empty
    #     list, allowing the renderer to create a tree-like structure to
    #     represent the document (which can then be reprocessed later into a
    #     separate format like docx or pdf).
    #     """
    #     return "<?xml:namespace ns='%s' ?>" % TeiNote.ROOT_NS

    def block_code(self, code, lang=None):
        """Rendering block level code. ``pre > code``.
        :param code: text content of the code block.
        :param lang: language of the given code.
        """
        # TODO
        # - is there any equivalent in tei?
        code = code.rstrip('\n')
        if not lang:
            code = mistune.escape(code, smart_amp=False)
            return '<pre><code>%s\n</code></pre>\n' % code
        code = mistune.escape(code, quote=True, smart_amp=False)
        return '<pre><code class="lang-%s">%s\n</code></pre>\n' % (lang, code)

    def block_quote(self, text):
        """Rendering <quote> with the given text.
        :param text: text content of the blockquote.
        """
        return '<quote>%s</quote>' % text.rstrip('\n')

    def block_html(self, html):
        """Rendering block level pure html content.
        :param html: text content of the html snippet.
        """
        # TODO
        if self.options.get('skip_style') and \
           html.lower().startswith('<style'):
            return ''
        if self.options.get('escape'):
            return mistune.escape(html)
        return html

    def header(self, text, level, raw=None):
        """Rendering header/heading tags like ``<h1>`` ``<h2>``.
        :param text: rendered text content for the header.
        :param level: a number for the header level, for example: 1.
        :param raw: raw text content of the header.
        """
        # TODO
        return '<h%d>%s</h%d>\n' % (level, text, level)

    def hrule(self):
        """Rendering method for ``<hr>`` tag."""
        # TODO
        if self.options.get('use_xhtml'):
            return '<hr />\n'
        return '<hr>\n'

    def list(self, body, ordered=True):
        """Rendering list tags.
        :param body: body contents of the list.
        :param ordered: whether this list is ordered or not.
        """
        attr = ''
        if ordered:
            attr = ' rend="numbered"'
        return '<list%s>%s</list>' % (attr, body)

    def list_item(self, text):
        """Rendering list item."""
        return '<item>%s</item>' % text

    def paragraph(self, text):
        """Rendering paragraph tags. Like ``<p>``."""
        return '<p>%s</p>' % text.strip(' ')

    def table(self, header, body):
        """Rendering table element. Wrap header and body in it.
        :param header: header part of the table.
        :param body: body part of the table.
        """
        # TODO
        return (
            '<table>\n<thead>%s</thead>\n'
            '<tbody>\n%s</tbody>\n</table>\n'
        ) % (header, body)

    def table_row(self, content):
        """Rendering a table row. Like ``<tr>``.
        :param content: content of current table row.
        """
        # TODO
        return '<tr>\n%s</tr>\n' % content

    def table_cell(self, content, **flags):
        """Rendering a table cell. Like ``<th>`` ``<td>``.
        :param content: content of current table cell.
        :param header: whether this is header or not.
        :param align: align of current table cell.
        """
        # TODO
        if flags['header']:
            tag = 'th'
        else:
            tag = 'td'
        align = flags['align']
        if not align:
            return '<%s>%s</%s>\n' % (tag, content, tag)
        return '<%s style="text-align:%s">%s</%s>\n' % (
            tag, align, content, tag
        )

    def double_emphasis(self, text):
        """Rendering **strong** text.
        :param text: text content for emphasis.
        """
        return '<emph rend="bold">%s</emph>' % text

    def emphasis(self, text):
        """Rendering *emphasis* text.
        :param text: text content for emphasis.
        """
        return '<emph rend="italic">%s</emph>' % text

    def codespan(self, text):
        """Rendering inline `code` text.
        :param text: text content for inline code.
        """
        # TODO
        text = mistune.escape(text.rstrip(), smart_amp=False)
        return '<code>%s</code>' % text

    def linebreak(self):
        """Rendering line break like ``<br>``."""
        # TODO
        if self.options.get('use_xhtml'):
            return '<br />\n'
        return '<br>\n'

    def strikethrough(self, text):
        """Rendering ~~strikethrough~~ text.
        :param text: text content for strikethrough.
        """
        return '<del>%s</del>' % text

    def text(self, text):
        """Rendering unformatted text.
        :param text: text content.
        """
        # TODO
        return mistune.escape(text)

    def autolink(self, link, is_email=False):
        """Rendering a given link or email address.
        :param link: link content or email address.
        :param is_email: whether this is an email or not.
        """
        link = mistune.escape(link)
        if is_email:
            tag = 'email'
            attr = ''
        else:
            tag = 'link'
            attr = ' target="%s"' % link
        return '<%(tag)s%(attr)>%(text)s</%(tag)s>' % {
            'tag':tag, 'text': link, 'attr': attr}

    def link(self, link, title, text):
        """Rendering a given link with content and title.
        :param link: href link for ``<a>`` tag.
        :param title: title content for `title` attribute.
        :param text: text content for description.
        """
        # TODO
        if link.startswith('javascript:'):
            link = ''
        if not title:
            return '<a href="%s">%s</a>' % (link, text)
        title = mistune.escape(title, quote=True)
        return '<a href="%s" title="%s">%s</a>' % (link, title, text)

    def image(self, src, title, text):
        """Rendering a image with title and text.
        :param src: source link of the image.
        :param title: title text of the image.
        :param text: alt text of the image.
        """
        if src.startswith('javascript:'):
            src = ''
        text = mistune.escape(text, quote=True)
        # markdown doesn't necessarily include mimetype;
        # is this required in tei?
        # attempt to infer from image url
        mimetype = 'image/%s' % (src.rsplit('.', 1)[-1])
        tag = '<media mimetype="%s" url="%s">' % (mimetype, src)
        if title or text:
            desc_parts = ['<desc>']
            if title:
                desc_parts.append('<head>%s</head>' % title)
            if text:
                desc_parts.append('<p>%s</p>' % text)
            desc_parts.append('</desc>')
            tag += ''.join(desc_parts)
        tag += '</media>'
        return tag


    def inline_html(self, html):
        """Rendering span level pure html content.
        :param html: text content of the html snippet.
        """
        # TODO
        if self.options.get('escape'):
            return mistune.escape(html)
        return html

    def newline(self):
        """Rendering newline element."""
        # TODO
        return ''

    def footnote_ref(self, key, index):
        """Rendering the ref anchor of a footnote.
        :param key: identity key for the footnote.
        :param index: the index count of current footnote.
        """
        return '<ref target="#fn%s" type="noteAnchor">%s</ref>' % \
            (key, index)

    def footnote_item(self, key, text):
        """Rendering a footnote item.
        :param key: identity key for the footnote.
        :param text: text content of the footnote.
        """
        return '<note xml:id="fn%s" type="footnote">%s</note>' % (key, text)

    def footnotes(self, text):
        """Wrapper for all footnotes.
        :param text: contents of all footnotes.
        """
        return '<div type="footnotes">%s</div>' % text


