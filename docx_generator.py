# -*- coding: utf-8 -*-
"""
Pure Python Microsoft Word (.docx) Exporter for Harvard Justice Study Guide
Zero dependencies: built entirely on zipfile and standard OpenXML specification.
Generates fully valid, styled Word documents (.docx) with:
- Harvard Crimson title and headers
- Professional table with borders, cell shading, and proper padding
- Full bilingual word lists, phonetics, and contextual sentences
"""

import zipfile
import io
import html

def escape_xml(text):
    if not text:
        return ""
    return html.escape(str(text))

def build_docx_bytes(title, subtitle, words):
    """
    Builds a complete, styled Microsoft Word (.docx) document as bytes.
    """
    buf = io.BytesIO()
    
    # 1. Content Types XML
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

    # 2. Package Relationships XML
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    # 3. Document Relationships XML
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    # 4. Styles XML (Harvard crimson headings, table styles, font declarations)
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Segoe UI" w:eastAsia="Microsoft YaHei" w:hAnsi="Segoe UI" w:cs="Segoe UI"/>
        <w:sz w:val="22"/>
        <w:color w:val="1E293B"/>
      </w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
</w:styles>"""

    # 5. Build Document Body XML
    rows_xml = []
    
    # Table Header Row
    headers = [
        ("序号", 800),
        ("单词 & 音标", 2400),
        ("词性与哲学释义", 3200),
        ("课堂原声例句及中译", 4600)
    ]
    
    th_xml = ['<w:tr><w:trPr><w:tblHeader/></w:trPr>']
    for text, width in headers:
        th_xml.append(f"""<w:tc>
          <w:tcPr>
            <w:tcW w:w="{width}" w:type="dxa"/>
            <w:shd w:val="clear" w:color="auto" w:fill="A51C30"/>
            <w:tcMar><w:top w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar>
          </w:tcPr>
          <w:p>
            <w:pPr><w:jc w:val="center"/></w:pPr>
            <w:r><w:rPr><w:b/><w:color w:val="FFFFFF"/></w:rPr><w:t>{escape_xml(text)}</w:t></w:r>
          </w:p>
        </w:tc>""")
    th_xml.append('</w:tr>')
    rows_xml.append("".join(th_xml))

    # Data Rows
    for idx, item in enumerate(words, 1):
        bg_color = "F8FAFC" if idx % 2 == 0 else "FFFFFF"
        w_text = escape_xml(item.get("word", ""))
        ph_text = escape_xml(item.get("phonetic", ""))
        pos_text = escape_xml(item.get("pos", ""))
        def_text = escape_xml(item.get("def_cn", ""))
        contexts = item.get("contexts", [])
        if not contexts and (item.get("sentence") or item.get("trans")):
            contexts = [{"sentence": item.get("sentence", ""), "trans": item.get("trans", ""), "source_title": ""}]

        context_paragraphs = []
        for c_idx, c in enumerate(contexts, 1):
            s_text = escape_xml(c.get("sentence", ""))
            t_text = escape_xml(c.get("trans", ""))
            src_tag = escape_xml(c.get("source_title", ""))
            prefix = f"【语境 {c_idx}】" if len(contexts) > 1 else ""
            if src_tag:
                prefix = f"【{src_tag}】 "
            
            context_paragraphs.append(f"""<w:p>
              <w:r><w:rPr><w:b/><w:sz w:val="18"/><w:color w:val="A51C30"/></w:rPr><w:t>{prefix}</w:t></w:r>
              <w:r><w:rPr><w:i/><w:color w:val="1E293B"/></w:rPr><w:t>"{s_text}"</w:t></w:r>
            </w:p>
            <w:p>
              <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t>译：{t_text}</w:t></w:r>
            </w:p>""")
        
        ctx_xml = "".join(context_paragraphs)

        row_xml = f"""<w:tr>
          <w:tc>
            <w:tcPr>
              <w:tcW w:w="800" w:type="dxa"/>
              <w:shd w:val="clear" w:color="auto" w:fill="{bg_color}"/>
              <w:tcMar><w:top w:w="100" w:type="dxa"/><w:bottom w:w="100" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>
            </w:tcPr>
            <w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:color w:val="64748B"/></w:rPr><w:t>{idx}</w:t></w:r></w:p>
          </w:tc>
          <w:tc>
            <w:tcPr>
              <w:tcW w:w="2400" w:type="dxa"/>
              <w:shd w:val="clear" w:color="auto" w:fill="{bg_color}"/>
              <w:tcMar><w:top w:w="100" w:type="dxa"/><w:bottom w:w="100" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>
            </w:tcPr>
            <w:p><w:r><w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="0F172A"/></w:rPr><w:t>{w_text}</w:t></w:r></w:p>
            <w:p><w:r><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t>{ph_text}</w:t></w:r></w:p>
          </w:tc>
          <w:tc>
            <w:tcPr>
              <w:tcW w:w="3200" w:type="dxa"/>
              <w:shd w:val="clear" w:color="auto" w:fill="{bg_color}"/>
              <w:tcMar><w:top w:w="100" w:type="dxa"/><w:bottom w:w="100" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>
            </w:tcPr>
            <w:p><w:r><w:rPr><w:b/><w:color w:val="A51C30"/></w:rPr><w:t>[{pos_text}] </w:t></w:r><w:r><w:rPr><w:color w:val="1E293B"/></w:rPr><w:t>{def_text}</w:t></w:r></w:p>
          </w:tc>
          <w:tc>
            <w:tcPr>
              <w:tcW w:w="4600" w:type="dxa"/>
              <w:shd w:val="clear" w:color="auto" w:fill="{bg_color}"/>
              <w:tcMar><w:top w:w="100" w:type="dxa"/><w:bottom w:w="100" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>
            </w:tcPr>
            {ctx_xml}
          </w:tc>
        </w:tr>"""
        rows_xml.append(row_xml)

    table_content = "".join(rows_xml)

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <!-- Document Title -->
    <w:p>
      <w:pPr>
        <w:jc w:val="center"/>
        <w:spacing w:before="240" w:after="120"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:b/>
          <w:sz w:val="40"/>
          <w:color w:val="A51C30"/>
        </w:rPr>
        <w:t>{escape_xml(title)}</w:t>
      </w:r>
    </w:p>
    
    <!-- Subtitle -->
    <w:p>
      <w:pPr>
        <w:jc w:val="center"/>
        <w:spacing w:after="240"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:sz w:val="22"/>
          <w:color w:val="64748B"/>
        </w:rPr>
        <w:t>{escape_xml(subtitle)}</w:t>
      </w:r>
    </w:p>

    <!-- Vocabulary Table -->
    <w:tbl>
      <w:tblPr>
        <w:tblW w:w="11000" w:type="dxa"/>
        <w:tblBorders>
          <w:top w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>
          <w:bottom w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>
          <w:left w:val="none"/>
          <w:right w:val="none"/>
          <w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>
          <w:insideV w:val="none"/>
        </w:tblBorders>
      </w:tblPr>
      {table_content}
    </w:tbl>
    
    <!-- Footer Note -->
    <w:p>
      <w:pPr><w:spacing w:before="300"/><w:jc w:val="right"/></w:pPr>
      <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="94A3B8"/></w:rPr><w:t>哈佛大学公开课 Justice 听说精读研学助教系统 · 自动生成</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/_rels/document.xml.rels', doc_rels)
        z.writestr('word/styles.xml', styles)
        z.writestr('word/document.xml', document_xml)

    return buf.getvalue()

if __name__ == "__main__":
    sample_words = [
        {
            "word": "utilitarianism",
            "phonetic": "/ˌjuːtɪlɪˈteriənɪzəm/",
            "pos": "n.",
            "def_cn": "功利主义，功利论",
            "sentence": "Bentham's utilitarianism claims that the highest principle of morality is to maximize utility.",
            "trans": "边沁的功利主义认为，最高的道德原则就是实现效用最大化。"
        }
    ]
    data = build_docx_bytes("哈佛公正课第一集词汇手册", "Michael Sandel 教授公开课", sample_words)
    with open("test.docx", "wb") as f:
        f.write(data)
    print("Generated test.docx successfully, size:", len(data))
