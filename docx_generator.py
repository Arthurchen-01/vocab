# -*- coding: utf-8 -*-
"""Standards-complete, font-safe Microsoft Word (.docx) exporter.

Zero third-party dependencies: built on ``zipfile`` + the ECMA-376 OpenXML
specification only.

--------------------------------------------------------------------------
WHY THIS FILE WAS REWRITTEN  (ticket ``D:\\vocab\\工单修复.docx``)
--------------------------------------------------------------------------
The first generation of this exporter produced a 5-part package
(``[Content_Types].xml``, ``_rels/.rels``, ``word/_rels/document.xml.rels``,
``word/styles.xml``, ``word/document.xml``) that declared
``w:ascii="Segoe UI" w:eastAsia="Microsoft YaHei"`` and looked fine in a
browser but broke in WPS Office:

1. ``word/fontTable.xml``, ``word/settings.xml``, ``word/theme/theme1.xml`` and
   ``docProps/*`` were missing -> WPS opened the file in
   「缺失字体兼容模式」 (missing-font compatibility mode).
2. Not a single ``w:lang`` was emitted, so WPS could not tell which characters
   belong to the Latin slot and which to the East-Asian slot; it fell back to
   drawing ASCII letters with the CJK font, which is exactly the garbled
   English seen in the ticket screenshots.
3. ``Segoe UI`` / ``Microsoft YaHei`` are not part of WPS's guaranteed font set,
   so the replacement font was picked by the reader instead of by us.
4. OOXML ``CT_PPr`` / ``CT_TblPrBase`` are *sequences*, not choices. The old
   output emitted ``w:jc`` before ``w:spacing`` and ``w:tblLayout`` before
   ``w:tblBorders``; strict readers treat that as damaged content.
5. ``w:szCs`` was never emitted next to ``w:sz``, so CJK text was laid out at
   the reader's default complex-script size.
6. No control-character sanitising: any ``\\x0b`` inside an ASR sentence makes
   the whole document unreadable.

--------------------------------------------------------------------------
INVARIANTS ENFORCED HERE (verified by tools/quality_pipeline/docx_conformance.py)
--------------------------------------------------------------------------
* Only fonts that ship with Chinese Windows and WPS are referenced:
  Latin -> ``Times New Roman``, CJK -> ``宋体`` (announced as ``SimSun``).
* Every referenced font is declared in ``word/fontTable.xml``.
* Every run carries explicit ``w:rFonts`` + ``w:lang``, and run text is split
  per script so no CJK font is ever asked to draw Latin letters (and no Latin
  font is asked to draw Han characters).
* ``w:szCs`` always accompanies ``w:sz``; ``w:bCs``/``w:iCs`` accompany
  ``w:b``/``w:i``.
* Child element order matches the ECMA-376 sequences for ``w:pPr``, ``w:rPr``,
  ``w:tblPr``, ``w:tcPr`` and ``w:sectPr``.
* The package carries content types + relationships for every part it writes.
"""

import datetime
import html
import io
import re
import zipfile

# --------------------------------------------------------------------------
# Font policy: only fonts guaranteed to exist on a Chinese Windows / WPS box.
# --------------------------------------------------------------------------
FONT_LATIN = "Times New Roman"
FONT_CJK = "宋体"
FONT_CJK_ALT = "SimSun"

COLOR_ACCENT = "A51C30"   # Harvard crimson
COLOR_INK = "1E293B"
COLOR_MUTED = "64748B"
COLOR_FAINT = "94A3B8"
COLOR_BODY = "334155"
COLOR_TABLE_ALT = "F8FAFC"

# Usable width of A4 (11906 dxa) minus 2 x 1080 dxa margins.
TABLE_WIDTH = 9746
COL_INDEX = 560
COL_WORD = 1900
COL_MEANING = 3100
COL_CONTEXT = TABLE_WIDTH - COL_INDEX - COL_WORD - COL_MEANING  # 4186

_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]")

# Han, CJK punctuation, kana, fullwidth forms.
_CJK_RANGES = (
    (0x2E80, 0x2EFF), (0x3000, 0x303F), (0x3040, 0x30FF), (0x3100, 0x312F),
    (0x31C0, 0x31EF), (0x3200, 0x32FF), (0x3300, 0x33FF), (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0xFE10, 0xFE4F), (0xFF00, 0xFFEF),
)


def _is_cjk(ch):
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def _sanitize(text):
    """Drop characters XML 1.0 forbids; they make the package unreadable."""
    return _ILLEGAL_XML.sub("", str(text if text is not None else ""))


def escape_xml(text):
    """Escape for XML *text* content (quotes may stay literal there)."""
    return html.escape(_sanitize(text), quote=False)


def _attr(text):
    return html.escape(_sanitize(text), quote=True)


def _segments(text):
    """Split text into (chunk, is_cjk) runs so each script gets its own font."""
    out = []
    for ch in _sanitize(text):
        cjk = _is_cjk(ch)
        if out and out[-1][1] == cjk:
            out[-1][0].append(ch)
        else:
            out.append(([ch], cjk))
    return [("".join(chars), cjk) for chars, cjk in out]


# --------------------------------------------------------------------------
# Run / paragraph builders.  Element order inside w:rPr and w:pPr follows the
# ECMA-376 sequence, otherwise strict readers flag the file as damaged.
# --------------------------------------------------------------------------
def _run(text, cjk, bold=False, italic=False, sz=20, color=COLOR_INK,
         underline=False):
    rpr = ['<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s"%s/>'
           % (FONT_LATIN, FONT_LATIN, FONT_CJK, FONT_LATIN,
              ' w:hint="eastAsia"' if cjk else '')]
    if bold:
        rpr.append("<w:b/><w:bCs/>")
    if italic:
        rpr.append("<w:i/><w:iCs/>")
    rpr.append('<w:color w:val="%s"/>' % color)
    rpr.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz))
    if underline:
        rpr.append('<w:u w:val="single"/>')
    rpr.append('<w:lang w:val="en-US" w:eastAsia="zh-CN" w:bidi="ar-SA"/>')
    return ('<w:r><w:rPr>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
            % ("".join(rpr), escape_xml(text)))


def runs(text, bold=False, italic=False, sz=20, color=COLOR_INK):
    """Script-aware runs. A newline becomes <w:br/>."""
    out = []
    for line_idx, line in enumerate(_sanitize(text).split("\n")):
        if line_idx:
            out.append("<w:r><w:br/></w:r>")
        for chunk, cjk in _segments(line):
            out.append(_run(chunk, cjk, bold=bold, italic=italic, sz=sz,
                            color=color))
    return "".join(out)


def _spacing(before=0, after=0, line=240):
    p = '<w:spacing w:line="%d" w:lineRule="auto"' % line
    if before:
        p += ' w:before="%d"' % before
    if after:
        p += ' w:after="%d"' % after
    return p + "/>"


def para(inner, jc=None, before=0, after=0, line=240):
    """w:pPr order: spacing -> ind -> jc (ECMA-376 CT_PPr sequence)."""
    ppr = [_spacing(before, after, line)]
    if jc:
        ppr.append('<w:jc w:val="%s"/>' % jc)
    return "<w:p><w:pPr>%s</w:pPr>%s</w:p>" % ("".join(ppr), inner)


def _cell(width, fill, inner, v_align="center"):
    """w:tcPr order: tcW -> shd -> tcMar -> vAlign.

    CT_TcMar / CT_TblCellMar are sequences: top, (start), left, bottom,
    (end), right -- emitting top/bottom/left/right is a schema violation.
    """
    tcpr = (
        '<w:tcW w:w="%d" w:type="dxa"/>'
        '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>'
        '<w:tcMar>'
        '<w:top w:w="80" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
        '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="90" w:type="dxa"/>'
        '</w:tcMar>'
        '<w:vAlign w:val="%s"/>' % (width, fill, v_align)
    )
    return "<w:tc><w:tcPr>%s</w:tcPr>%s</w:tc>" % (tcpr, inner)


# --------------------------------------------------------------------------
# Static package parts
# --------------------------------------------------------------------------
_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/webSettings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

_PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/webSettings" Target="webSettings.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
  <Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="{latin}" w:hAnsi="{latin}" w:eastAsia="{cjk}" w:cs="{latin}"/>
        <w:color w:val="{ink}"/>
        <w:sz w:val="20"/><w:szCs w:val="20"/>
        <w:lang w:val="en-US" w:eastAsia="zh-CN" w:bidi="ar-SA"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr>
        <w:spacing w:line="240" w:lineRule="auto" w:before="0" w:after="0"/>
        <w:jc w:val="both"/>
      </w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
  </w:style>
  <w:style w:type="table" w:default="1" w:styleId="TableNormal">
    <w:name w:val="Normal Table"/>
    <w:semiHidden/>
    <w:unhideWhenUsed/>
    <w:tblPr>
      <w:tblInd w:w="0" w:type="dxa"/>
      <w:tblCellMar>
        <w:top w:w="0" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>
        <w:bottom w:w="0" w:type="dxa"/><w:right w:w="80" w:type="dxa"/>
      </w:tblCellMar>
    </w:tblPr>
  </w:style>
  <w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont">
    <w:name w:val="Default Paragraph Font"/>
    <w:semiHidden/>
    <w:unhideWhenUsed/>
  </w:style>
</w:styles>""".format(latin=FONT_LATIN, cjk=FONT_CJK, ink=COLOR_INK)

_SETTINGS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="420"/>
  <w:characterSpacingControl w:val="compressPunctuation"/>
  <w:compat>
    <w:useFELayout/>
    <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
  </w:compat>
  <w:themeFontLang w:val="en-US" w:eastAsia="zh-CN" w:bidi="ar-SA"/>
  <w:decimalSymbol w:val="."/>
  <w:listSeparator w:val=","/>
</w:settings>"""

_WEB_SETTINGS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:webSettings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:optimizeForBrowser/>
  <w:allowPNG/>
</w:webSettings>"""

_FONT_TABLE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:font w:name="{latin}">
    <w:panose1 w:val="02020603050405020304"/>
    <w:charset w:val="00"/>
    <w:family w:val="roman"/>
    <w:pitch w:val="variable"/>
    <w:sig w:usb0="E0002EFF" w:usb1="C000785B" w:usb2="00000009" w:usb3="00000000" w:csb0="000001FF" w:csb1="00000000"/>
  </w:font>
  <w:font w:name="{cjk}">
    <w:altName w:val="{cjk_alt}"/>
    <w:panose1 w:val="02010600030101010101"/>
    <w:charset w:val="86"/>
    <w:family w:val="auto"/>
    <w:pitch w:val="variable"/>
  </w:font>
</w:fonts>""".format(latin=FONT_LATIN, cjk=FONT_CJK, cjk_alt=FONT_CJK_ALT)

_THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Justice Study Guide">
  <a:themeElements>
    <a:clrScheme name="Justice">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="{ink}"/></a:dk2>
      <a:lt2><a:srgbClr val="{alt}"/></a:lt2>
      <a:accent1><a:srgbClr val="{accent}"/></a:accent1>
      <a:accent2><a:srgbClr val="0F172A"/></a:accent2>
      <a:accent3><a:srgbClr val="475569"/></a:accent3>
      <a:accent4><a:srgbClr val="64748B"/></a:accent4>
      <a:accent5><a:srgbClr val="E2E8F0"/></a:accent5>
      <a:accent6><a:srgbClr val="94A3B8"/></a:accent6>
      <a:hlink><a:srgbClr val="{accent}"/></a:hlink>
      <a:folHlink><a:srgbClr val="7F1D1D"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Justice">
      <a:majorFont>
        <a:latin typeface="{latin}"/>
        <a:ea typeface="{cjk}"/>
        <a:cs typeface="{latin}"/>
      </a:majorFont>
      <a:minorFont>
        <a:latin typeface="{latin}"/>
        <a:ea typeface="{cjk}"/>
        <a:cs typeface="{latin}"/>
      </a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Justice">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:gradFill rotWithShape="1">
          <a:gsLst>
            <a:gs pos="0"><a:schemeClr val="phClr"><a:lumMod val="110000"/><a:satMod val="105000"/><a:tint val="67000"/></a:schemeClr></a:gs>
            <a:gs pos="50000"><a:schemeClr val="phClr"><a:lumMod val="105000"/><a:satMod val="103000"/><a:tint val="73000"/></a:schemeClr></a:gs>
            <a:gs pos="100000"><a:schemeClr val="phClr"><a:lumMod val="105000"/><a:satMod val="109000"/><a:tint val="81000"/></a:schemeClr></a:gs>
          </a:gsLst>
          <a:lin ang="5400000" scaled="0"/>
        </a:gradFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>
        <a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>
        <a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
  <a:objectDefaults/>
  <a:extraClrSchemeLst/>
</a:theme>""".format(latin=FONT_LATIN, cjk=FONT_CJK, ink=COLOR_INK,
                     alt=COLOR_TABLE_ALT, accent=COLOR_ACCENT)


_FOOTER_RPR = ('<w:rPr><w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s"/>'
               '<w:color w:val="%s"/><w:sz w:val="16"/><w:szCs w:val="16"/>'
               '<w:lang w:val="en-US" w:eastAsia="zh-CN" w:bidi="ar-SA"/></w:rPr>'
               % (FONT_LATIN, FONT_LATIN, FONT_CJK, FONT_LATIN, COLOR_FAINT))


def _fld(kind, instr=None, text=None):
    rpr = _FOOTER_RPR
    if kind == "instr":
        return ('<w:r>%s<w:instrText xml:space="preserve">%s</w:instrText></w:r>'
                % (rpr, instr))
    if kind == "text":
        return '<w:r>%s<w:t>%s</w:t></w:r>' % (rpr, escape_xml(text))
    return '<w:r>%s<w:fldChar w:fldCharType="%s"/></w:r>' % (rpr, kind)


def _field(instr):
    """Explicit begin/instr/separate/result/end - the most portable syntax."""
    return (_fld("begin") + _fld("instr", instr=instr) + _fld("separate")
            + _fld("text", text="1") + _fld("end"))


def _footer_xml(footer_text):
    """Page X of Y."""
    inner = (
        runs(footer_text + " 第 ", sz=16, color=COLOR_FAINT) + _field(" PAGE ")
        + runs(" 页 / 共 ", sz=16, color=COLOR_FAINT) + _field(" NUMPAGES ")
        + runs(" 页", sz=16, color=COLOR_FAINT)
    )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + para(inner, jc="center", before=60, after=60) + '</w:ftr>')


def _core_props(title, subtitle, words_count):
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>%s</dc:title>'
            '<dc:subject>%s</dc:subject>'
            '<dc:creator>Harvard Justice Vocabulary Studio</dc:creator>'
            '<cp:lastModifiedBy>Harvard Justice Vocabulary Studio</cp:lastModifiedBy>'
            '<cp:keywords>Justice, Michael Sandel, vocabulary, %d words</cp:keywords>'
            '<dc:description>%s · %d words</dc:description>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
            '<cp:category>Study Guide</cp:category>'
            '</cp:coreProperties>'
            % (_attr(title), _attr(subtitle), words_count, _attr(subtitle),
               words_count, now, now))


def _app_props(words_count):
    # shared-documentPropertiesExtended.xsd is a sequence, not a bag:
    # Template, Manager, Company, Pages, Words, ..., ScaleCrop, ..., LinksUpToDate,
    # CharactersWithSpaces, SharedDoc, HyperlinkBase, HLinks, HyperlinksChanged,
    # DigSig, Application, AppVersion, DocSecurity
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<Company>Harvard Justice Vocabulary Studio</Company>'
            '<Words>%d</Words>'
            '<ScaleCrop>false</ScaleCrop>'
            '<LinksUpToDate>false</LinksUpToDate>'
            '<SharedDoc>false</SharedDoc>'
            '<HyperlinksChanged>false</HyperlinksChanged>'
            '<Application>Microsoft Office Word</Application>'
            '<AppVersion>16.0000</AppVersion>'
            '<DocSecurity>0</DocSecurity>'
            '</Properties>' % words_count)


# --------------------------------------------------------------------------
# Document body
# --------------------------------------------------------------------------
def _contexts_of(item):
    contexts = item.get("contexts") or []
    if not contexts and (item.get("sentence") or item.get("trans")):
        contexts = [{"sentence": item.get("sentence", ""),
                     "trans": item.get("trans", ""),
                     "source_title": ""}]
    return [c for c in contexts if (c.get("sentence") or c.get("trans"))]


def _context_cell(item, fill):
    contexts = _contexts_of(item)
    paras = []
    for i, c in enumerate(contexts, 1):
        src = (c.get("source_title") or "").strip()
        tag = "【%s】 " % src if src else ("【语境 %d】 " % i if len(contexts) > 1 else "")
        head = runs(tag, bold=True, sz=17, color=COLOR_ACCENT) if tag else ""
        body = runs('"%s"' % (c.get("sentence") or "").strip(), italic=True,
                    sz=18, color="0F172A")
        trans = c.get("trans") or ""
        tail = ("<w:r><w:br/></w:r>" + runs("译：" + trans, sz=17, color=COLOR_MUTED)
                if trans else "")
        paras.append(para(head + body + tail, after=20, before=20))
    if not paras:
        paras.append(para(runs("（该词条暂无例句）", sz=17, color=COLOR_FAINT),
                          before=20, after=20))
    return _cell(COL_CONTEXT, fill, "".join(paras), v_align="top")


def _meaning_cell(item, fill):
    pos = (item.get("pos") or "").strip()
    def_cn = (item.get("def_cn") or "").strip()
    def_en = (item.get("def_en") or "").strip()
    # Imported decks (SAT, phrase lists) carry no part of speech; printing "[]"
    # would look like a defect.
    label = runs("[%s] " % pos, bold=True, sz=19, color=COLOR_ACCENT) if pos else ""
    paras = [para(label + runs(def_cn, sz=19, color=COLOR_INK), before=20, after=20)]
    if def_en:
        paras.append(para(runs("EN ", bold=True, sz=16, color=COLOR_ACCENT)
                          + runs(def_en, sz=18, color=COLOR_BODY),
                          before=10, after=20))
    return _cell(COL_MEANING, fill, "".join(paras), v_align="top")


def _word_cell(item, fill):
    inner = (para(runs(item.get("word", ""), bold=True, sz=21, color="0F172A"),
                  before=20, after=0)
             + para(runs(item.get("phonetic", "") or "", sz=17, color=COLOR_MUTED),
                    before=0, after=20))
    return _cell(COL_WORD, fill, inner, v_align="center")


def _header_row():
    headers = [("序号", COL_INDEX, "center"), ("单词 & 音标", COL_WORD, "left"),
               ("词性与中英释义", COL_MEANING, "left"),
               ("课堂原声例句及中译", COL_CONTEXT, "left")]
    cells = []
    for text, width, align in headers:
        inner = para(runs(text, bold=True, sz=20, color="FFFFFF"), jc=align,
                     before=40, after=40)
        cells.append(_cell(width, COLOR_ACCENT, inner, v_align="center"))
    return ('<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>%s</w:tr>'
            % "".join(cells))


def _data_row(idx, item):
    fill = COLOR_TABLE_ALT if idx % 2 == 0 else "FFFFFF"
    index_cell = _cell(COL_INDEX, fill,
                       para(runs(str(idx), sz=18, color=COLOR_MUTED), jc="center",
                            before=20, after=20))
    return ('<w:tr><w:trPr><w:cantSplit/></w:trPr>%s</w:tr>'
            % (index_cell + _word_cell(item, fill) + _meaning_cell(item, fill)
               + _context_cell(item, fill)))


def build_docx_bytes(title, subtitle, words, meta_line=None, footer_text=None):
    """Build a complete, WPS-safe .docx package for the given word list.

    ``words`` items may carry: word, phonetic, pos, def_cn, def_en, sentence,
    trans and/or contexts[{sentence, trans, source_title}].
    """
    words = list(words or [])
    with_en = sum(1 for w in words if (w.get("def_en") or "").strip())
    exported_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if meta_line is None:
        meta_line = ("共收录 %d 个学术词汇 · 英文释义 %d 条 · 导出于 %s"
                     % (len(words), with_en, exported_at))
    if footer_text is None:
        footer_text = "哈佛大学公开课 Justice · 听说精读研学助教系统"

    body = [
        para(runs(title, bold=True, sz=36, color=COLOR_ACCENT), jc="center",
             before=120, after=60),
        para(runs(subtitle, sz=20, color="475569"), jc="center", after=60),
        para(runs("Harvard University · Prof. Michael J. Sandel · "
                  "听说精读四维对标学术词表", sz=17, color=COLOR_FAINT),
             jc="center", after=60),
        para(runs(meta_line, sz=17, color=COLOR_FAINT), jc="center", after=160),
    ]

    if words:
        rows = [_header_row()] + [_data_row(i, w) for i, w in enumerate(words, 1)]
        # w:tblPr order: tblW -> jc -> tblBorders -> tblLayout -> tblCellMar
        body.append(
            '<w:tbl><w:tblPr>'
            '<w:tblW w:w="%d" w:type="dxa"/>'
            '<w:jc w:val="center"/>'
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="8" w:space="0" w:color="%s"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="%s"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
            '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '</w:tblBorders>'
            '<w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar>'
            '<w:top w:w="80" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
            '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="90" w:type="dxa"/>'
            '</w:tblCellMar>'
            '</w:tblPr>'
            '<w:tblGrid>'
            '<w:gridCol w:w="%d"/><w:gridCol w:w="%d"/>'
            '<w:gridCol w:w="%d"/><w:gridCol w:w="%d"/>'
            '</w:tblGrid>%s</w:tbl>'
            % (TABLE_WIDTH, COLOR_ACCENT, COLOR_ACCENT, COL_INDEX, COL_WORD,
               COL_MEANING, COL_CONTEXT, "".join(rows))
        )
    else:
        body.append(para(runs("（当前词表为空，未生成表格）", sz=20, color=COLOR_MUTED),
                         jc="center", before=200, after=200))

    body.append(para(runs(footer_text, sz=16, color=COLOR_FAINT), jc="right",
                     before=200, after=100))

    # w:sectPr order: footerReference -> pgSz -> pgMar -> cols -> docGrid
    body.append(
        '<w:sectPr>'
        '<w:footerReference w:type="default" r:id="rId6"/>'
        '<w:pgSz w:w="11906" w:h="16838" w:orient="portrait"/>'
        '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        '<w:cols w:space="720"/>'
        '<w:docGrid w:type="lines" w:linePitch="312"/>'
        '</w:sectPr>'
    )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<w:body>' + "".join(body) + '</w:body></w:document>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _PACKAGE_RELS)
        z.writestr("docProps/core.xml", _core_props(title, subtitle, len(words)))
        z.writestr("docProps/app.xml", _app_props(len(words)))
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/settings.xml", _SETTINGS)
        z.writestr("word/webSettings.xml", _WEB_SETTINGS)
        z.writestr("word/fontTable.xml", _FONT_TABLE)
        z.writestr("word/theme/theme1.xml", _THEME)
        z.writestr("word/footer1.xml", _footer_xml(footer_text))
    return buf.getvalue()


if __name__ == "__main__":
    sample = [
        {"word": "utilitarianism", "phonetic": "/ˌjuːtɪlɪˈteriənɪzəm/", "pos": "n.",
         "def_cn": "功利主义，功利论（以多数人的最大利益和幸福为衡量正义的标准）",
         "def_en": "the ethical theory that the right action is the one that "
                   "produces the greatest happiness for the greatest number",
         "sentence": "Bentham's utilitarianism claims that the highest principle "
                     "of morality is to maximize the general welfare.",
         "trans": "边沁的功利主义认为，最高的道德原则就是实现普遍福利的最大化。"},
        {"word": "coercion", "phonetic": "/koʊˈɜːrʃn/", "pos": "n.",
         "def_cn": "强制，胁迫",
         "def_en": "the practice of persuading someone to do something by using "
                   "force or threats",
         "sentence": "And the state has no business coercing us to wear seat belts.",
         "trans": "而国家无权强制我们系安全带。"},
    ]
    data = build_docx_bytes("哈佛大学《公正课》词汇手册",
                            "Sample · Michael Sandel 教授公开课", sample)
    with open("test.docx", "wb") as f:
        f.write(data)
    print("Generated test.docx, %d bytes, %d words" % (len(data), len(sample)))
