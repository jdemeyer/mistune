import re
from .util import keyify

inline_tags = [
    'a', 'em', 'strong', 'small', 's', 'cite', 'q', 'dfn', 'abbr', 'data',
    'time', 'code', 'var', 'samp', 'kbd', 'sub', 'sup', 'i', 'b', 'u', 'mark',
    'ruby', 'rt', 'rp', 'bdi', 'bdo', 'span', 'br', 'wbr', 'ins', 'del',
    'img', 'font',
]
_tag_end = r'(?!:/|[^\w\s@]*@)\b'
_tag_attr = r'''\s*[a-zA-Z\-](?:\=(?:"[^"]*"|'[^']*'|[^\s'">]+))?'''
_block_tag = r'(?!(?:%s)\b)\w+%s' % ('|'.join(inline_tags), _tag_end)

_block_quote_leading_pattern = re.compile(r'^ *> ?', flags=re.M)
_block_code_leading_pattern = re.compile(r'^ {4}', re.M)


class BlockGrammar(object):
    """Grammars for block level tokens."""

    def_links = (
        r' *\[(?P<def_links_key>[^^\]]+)\]: *'  # [key]:
        r'<?(?P<def_links_link>[^\s>]+)>?'  # <link> or link
        r'(?: +["(](?P<def_links_title>[^\n]+)[")])? *(?:\n+|$)'
    )
    def_footnotes = (
        r'\[\^(?P<def_footnotes_key>[^\]]+)\]: *'  # [^key]:
        r'(?P<def_footnotes_text>'
        r'[^\n]*(?:\n+|$)'
        r'(?: {1,}[^\n]*(?:\n+|$))*'
        r')'
    )

    newline = r'\n+'
    block_code = r'( {4}[^\n]+\n*)+'
    fences = (
        r' *(?P<fences_symbols>`{3,}|~{3,}) *(?P<fences_lang>\S+)? *\n'
        r'(?P<fences_text>[\s\S]+?)\s*'
        r'(?P=fences_symbols) *(?:\n+|$)'  # ```
    )
    hrule = r' {0,3}[-*_](?: *[-*_]){2,} *(?:\n+|$)'
    heading = (
        r' *(?P<heading_level>#{1,6})'
        r' *(?P<heading_text>[^\n]+?) *#* *(?:\n+|$)'
    )
    lheading = (
        r'(?P<lheading_text>[^\n]+)\n'
        r' *(?P<lheading_symbol>=|-)+ *(?:\n+|$)'
    )
    block_quote = r'( *>[^\n]+(\n[^\n]+)*\n*)+'
    list_ul_block = (
        r' {0,3}(?P<list_ul_bullet>[*+-]) .+'
        r'(?:'
        r'\n+ {2,}.+'
        r'|\n+(?P=list_ul_bullet) .+'
        r')'
    )
    list_ol_block = (
        r' {0,3}(?P<list_ol_bullet>\d+\.) .+'
        r'(?:'
        r'\n+ {2,}.+'
        r'|\n+(?P=list_ol_bullet) .+'
        r')'
    )
    list_block = ''
    list_item = re.compile(
        r'^(( *)(?:[*+-]|\d+\.) [^\n]*'
        r'(?:\n(?!\2(?:[*+-]|\d+\.) )[^\n]*)*)',
        flags=re.M
    )
    list_bullet = re.compile(r'^ *(?:[*+-]|\d+\.) +')
    paragraph = (
        r'((?:[^\n]+\n?(?!'
        r'%s|%s|%s|%s|%s|%s|%s|%s|%s'
        r'))+)\n*' % (
            fences,
            list_block,
            hrule,
            heading,
            lheading,
            block_quote,
            def_links,
            def_footnotes,
            '<' + _block_tag,
        )
    )
    block_html = r' *(?:%s|%s|%s) *(?:\n{2,}|\s*$)' % (
        r'<!--[\s\S]*?-->',
        r'<(?P<tag_name>%s)((?:%s)*?)>([\s\S]*?)<\/(?P=tag_name)>' % (
            _block_tag, _tag_attr),
        r'<%s(?:%s)*?\s*\/?>' % (_block_tag, _tag_attr),
    )
    table = r' *\|(.+)\n *\|( *[-:]+[-| :]*)\n((?: *\|.*(?:\n|$))*)\n*'
    nptable = r' *(\S.*\|.*)\n *([-:]+ *\|[-| :]*)\n((?:.*\|.*(?:\n|$))*)\n*'
    text = r'[^\n]+'


class BlockLexer(object):
    """Block level lexer for block grammars."""
    grammar_class = BlockGrammar

    default_rules = [
        'newline', 'hrule', 'block_code', 'fences', 'heading',
        'nptable', 'lheading', 'block_quote',
        'list_block', 'block_html', 'def_links',
        'def_footnotes', 'table', 'paragraph', 'text'
    ]

    list_rules = (
        'newline', 'block_code', 'fences', 'lheading', 'hrule',
        'block_quote', 'list_block', 'block_html', 'text',
    )

    footnote_rules = (
        'newline', 'block_code', 'fences', 'heading',
        'nptable', 'lheading', 'hrule', 'block_quote',
        'list_block', 'block_html', 'table', 'paragraph', 'text'
    )

    def __init__(self, rules=None, **kwargs):
        self.tokens = []
        self.def_links = {}
        self.def_footnotes = {}

        if not rules:
            rules = self.grammar_class()

        self.rules = rules
        self._max_recursive_depth = kwargs.get('max_recursive_depth', 6)

        self._group_rules_pattern = {}
        self._list_depth = 0
        self._blockquote_depth = 0

    def __call__(self, text, rules=None):
        return self.parse(text, rules)

    def parse(self, text, rules=None):
        text = text.rstrip('\n')

        if not rules:
            rules = self.default_rules

            rules = [
                'newline', 'hrule', 'block_code', 'fences', 'heading',
                'lheading', 'block_quote', 'list_block'
            ]

        cache_key = tuple(rules)
        if cache_key not in self._group_rules_pattern:
            rules_pattern = re.compile(r'|'.join(
                r'(?P<%s>(?:%s))' %
                (k, getattr(self.rules, k)) for k in rules
            ))
            self._group_rules_pattern[cache_key] = rules_pattern
        else:
            rules_pattern = self._group_rules_pattern[cache_key]

        for m in rules_pattern.finditer(text):
            getattr(self, 'parse_%s' % m.lastgroup)(m)
        return self.tokens

    def parse_newline(self, m):
        length = len(m.group('newline'))
        if length > 1:
            self.tokens.append({'type': 'newline'})

    def parse_block_code(self, m):
        # clean leading whitespace
        code = _block_code_leading_pattern.sub('', m.group(0))
        self.tokens.append({
            'type': 'code',
            'lang': None,
            'text': code,
        })

    def parse_fences(self, m):
        self.tokens.append({
            'type': 'code',
            'lang': m.group('fences_lang'),
            'text': m.group('fences_text'),
        })

    def parse_heading(self, m):
        self.tokens.append({
            'type': 'heading',
            'level': len(m.group('heading_level')),
            'text': m.group('heading_text'),
        })

    def parse_lheading(self, m):
        """Parse setext heading."""
        self.tokens.append({
            'type': 'heading',
            'level': 1 if m.group('lheading_symbol') == '=' else 2,
            'text': m.group('lheading_text'),
        })

    def parse_hrule(self, m):
        self.tokens.append({'type': 'hrule'})

    def parse_list_block(self, m):
        bull = m.group('list_block_bullet')
        self.tokens.append({
            'type': 'list_start',
            'ordered': '.' in bull,
        })
        self._list_depth += 1
        if self._list_depth > self._max_recursive_depth:
            self.parse_text(m)
        else:
            cap = m.group(0)
            self._process_list_item(cap, bull)
        self.tokens.append({'type': 'list_end'})
        self._list_depth -= 1

    def _process_list_item(self, cap, bull):
        cap = self.rules.list_item.findall(cap)

        _next = False
        length = len(cap)

        for i in range(length):
            item = cap[i][0]

            # remove the bullet
            space = len(item)
            item = self.rules.list_bullet.sub('', item)

            # outdent
            if '\n ' in item:
                space = space - len(item)
                pattern = re.compile(r'^ {1,%d}' % space, flags=re.M)
                item = pattern.sub('', item)

            # determine whether item is loose or not
            loose = _next
            if not loose and re.search(r'\n\n(?!\s*$)', item):
                loose = True

            rest = len(item)
            if i != length - 1 and rest:
                _next = item[rest-1] == '\n'
                if not loose:
                    loose = _next

            if loose:
                t = 'loose_item_start'
            else:
                t = 'list_item_start'

            self.tokens.append({'type': t})
            # recurse
            self.parse(item, self.list_rules)
            self.tokens.append({'type': 'list_item_end'})

    def parse_block_quote(self, m):
        self.tokens.append({'type': 'block_quote_start'})
        self._blockquote_depth += 1
        if self._blockquote_depth > self._max_recursive_depth:
            # TODO self.parse_text(m)
            pass
        else:
            # clean leading >
            cap = _block_quote_leading_pattern.sub('', m.group(0))
            self.parse(cap)
        self.tokens.append({'type': 'block_quote_end'})
        self._blockquote_depth -= 1

    def parse_def_links(self, m):
        key = keyify(m.group('def_links_key'))
        self.def_links[key] = {
            'link': m.group('def_links_link'),
            'title': m.group('def_links_title'),
        }

    def parse_def_footnotes(self, m):
        key = keyify(m.group('def_footnotes_key'))
        if key in self.def_footnotes:
            # footnote is already defined
            return

        self.def_footnotes[key] = 0

        self.tokens.append({
            'type': 'footnote_start',
            'key': key,
        })

        text = m.group('def_footnotes_text')

        if '\n' in text:
            lines = text.split('\n')
            whitespace = None
            for line in lines[1:]:
                space = len(line) - len(line.lstrip())
                if space and (not whitespace or space < whitespace):
                    whitespace = space
            newlines = [lines[0]]
            for line in lines[1:]:
                newlines.append(line[whitespace:])
            text = '\n'.join(newlines)

        self.parse(text, self.footnote_rules)

        self.tokens.append({
            'type': 'footnote_end',
            'key': key,
        })

    def parse_table(self, m):
        item = self._process_table(m)

        cells = re.sub(r'(?: *\| *)?\n$', '', m.group(3))
        cells = cells.split('\n')
        for i, v in enumerate(cells):
            v = re.sub(r'^ *\| *| *\| *$', '', v)
            cells[i] = re.split(r' *\| *', v)

        item['cells'] = cells
        self.tokens.append(item)

    def parse_nptable(self, m):
        item = self._process_table(m)

        cells = re.sub(r'\n$', '', m.group(3))
        cells = cells.split('\n')
        for i, v in enumerate(cells):
            cells[i] = re.split(r' *\| *', v)

        item['cells'] = cells
        self.tokens.append(item)

    def _process_table(self, m):
        header = re.sub(r'^ *| *\| *$', '', m.group(1))
        header = re.split(r' *\| *', header)
        align = re.sub(r' *|\| *$', '', m.group(2))
        align = re.split(r' *\| *', align)

        for i, v in enumerate(align):
            if re.search(r'^ *-+: *$', v):
                align[i] = 'right'
            elif re.search(r'^ *:-+: *$', v):
                align[i] = 'center'
            elif re.search(r'^ *:-+ *$', v):
                align[i] = 'left'
            else:
                align[i] = None

        item = {
            'type': 'table',
            'header': header,
            'align': align,
        }
        return item

    def parse_block_html(self, m):
        tag = m.group(1)
        if not tag:
            text = m.group(0)
            self.tokens.append({
                'type': 'close_html',
                'text': text
            })
        else:
            attr = m.group(2)
            text = m.group(3)
            self.tokens.append({
                'type': 'open_html',
                'tag': tag,
                'extra': attr,
                'text': text
            })

    def parse_paragraph(self, m):
        text = m.group(1).rstrip('\n')
        self.tokens.append({'type': 'paragraph', 'text': text})

    def parse_text(self, m):
        text = m.group(0)
        self.tokens.append({'type': 'text', 'text': text})
