# -*- coding: utf-8 -*-
"""S5B - .docx conformance gate.

Deterministic, offline verification of every Microsoft Word package the app
hands to a user.  It exists because the ticket ``D:\\vocab\\工单修复.docx`` was
caused by structural defects that no screenshot can reveal:

* missing OOXML parts (fontTable / settings / theme / docProps) -> WPS opens in
  「缺失字体兼容模式」;
* fonts outside the guaranteed set (Segoe UI / Microsoft YaHei) and no
  ``w:lang`` anywhere -> the reader picks the font, and Latin letters get drawn
  with the East-Asian font: garbled English;
* child elements emitted in an order the ECMA-376 sequences do not allow
  (``w:jc`` before ``w:spacing``, ``w:tblLayout`` before ``w:tblBorders``,
  ``w:tcMar`` as top/bottom/left/right);
* ``w:sz`` without ``w:szCs``; control characters that make the file unreadable.

Usage
-----
    python docx_conformance.py <file.docx> [--words <deck.json>] [--stage NAME]

The optional ``--words`` JSON (a deck: ``{"words": [...]}`` or a bare list) turns
on the content round-trip gate: every word / def_cn / def_en must appear in the
extracted document text and the table must have exactly ``len(words)+1`` rows.
"""

import argparse
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Report  # noqa: E402

# --------------------------------------------------------------------------
# Font policy: keep in sync with docx_generator.FONT_*
# --------------------------------------------------------------------------
ALLOWED_FONTS = {"Times New Roman", "宋体", "SimSun"}

REQUIRED_PARTS = [
    "[Content_Types].xml",
    "_rels/.rels",
    "docProps/core.xml",
    "docProps/app.xml",
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
    "word/settings.xml",
    "word/webSettings.xml",
    "word/fontTable.xml",
    "word/theme/theme1.xml",
    "word/footer1.xml",
]

# Canonical child order (ECMA-376 transitional).  Only parents we emit are
# listed; anything else is skipped rather than guessed at.
SEQ = {
    "pPr": ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
            "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd",
            "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
            "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
            "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
            "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
            "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl",
            "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"],
    "rPr": ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps",
            "strike", "dstrike", "outline", "shadow", "emboss", "imprint",
            "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
            "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect",
            "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang",
            "eastAsianLayout", "specVanish", "oMath"],
    "tblPr": ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual",
              "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc",
              "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout",
              "tblCellMar", "tblLook", "tblCaption", "tblDescription"],
    "tcPr": ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders",
             "shd", "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign",
             "hideMark"],
    "trPr": ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore",
             "wAfter", "cantSplit", "trHeight", "tblHeader", "tblCellSpacing",
             "jc", "hidden"],
    "sectPr": ["headerReference", "footerReference", "footnotePr", "endnotePr",
               "type", "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType",
               "pgNumType", "cols", "formProt", "vAlign", "noEndnote",
               "titlePg", "textDirection", "bidi", "rtlGutter", "docGrid",
               "printerSettings"],
    "tblBorders": ["top", "start", "left", "bottom", "end", "right",
                   "insideH", "insideV"],
    "tcMar": ["top", "start", "left", "bottom", "end", "right"],
    "tblCellMar": ["top", "start", "left", "bottom", "end", "right"],
    "tblGrid": ["gridCol"],
    "styles": ["docDefaults", "latentStyles", "style"],
    "style": ["name", "aliases", "basedOn", "next", "link", "autoRedefine",
              "hidden", "uiPriority", "semiHidden", "unhideWhenUsed", "qFormat",
              "locked", "personal", "personalCompose", "personalReply", "rsid",
              "pPr", "rPr", "tblPr", "trPr", "tcPr", "tblStylePr"],
    "docDefaults": ["rPrDefault", "pPrDefault"],
    "rPrDefault": ["rPr"],
    "pPrDefault": ["pPr"],
    "webSettings": ["divs", "encoding", "optimizeForBrowser", "relyOnVML",
                    "allowPNG", "doNotRelyOnCSS", "doNotSaveAsSingleFile",
                    "doNotOrganizeInFolder", "doNotUseLongFileNames",
                    "pixelsPerInch", "targetScreenSz", "saveSmartTagsAsXml"],
    "font": ["altName", "panose1", "charset", "family", "notTrueType", "pitch",
             "sig", "embedRegular", "embedBold", "embedItalic",
             "embedBoldItalic"],
    "fonts": ["font"],
    "document": ["background", "body"],
    "settings": [
        "writeProtection", "view", "zoom", "removePersonalInformation",
        "removeDateAndTime", "doNotDisplayPageBoundaries",
        "displayBackgroundShape", "printPostScriptOverText",
        "printFractionalCharacterWidth", "printFormsData",
        "embedTrueTypeFonts", "embedSystemFonts", "saveSubsetFonts",
        "saveFormsData", "mirrorMargins", "alignBordersAndEdges",
        "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter",
        "gutterAtTop", "hideSpellingErrors", "hideGrammaticalErrors",
        "activeWritingStyle", "proofState", "formsDesign", "attachedTemplate",
        "linkStyles", "stylePaneFormatFilter", "stylePaneSortMethod",
        "documentType", "mailMerge", "revisionView", "trackChanges",
        "doNotTrackMoves", "doNotTrackFormatting", "documentProtection",
        "autoFormatOverride", "styleLockTheme", "styleLockQFSet",
        "defaultTabStop", "autoHyphenation", "consecutiveHyphenLimit",
        "hyphenationZone", "doNotHyphenateCaps", "showEnvelope",
        "summaryLength", "clickAndTypeStyle", "defaultTableStyle",
        "evenAndOddHeaders", "bookFoldRevPrinting", "bookFoldPrinting",
        "bookFoldPrintingSheets", "drawingGridHorizontalSpacing",
        "drawingGridVerticalSpacing", "displayHorizontalDrawingGridEvery",
        "displayVerticalDrawingGridEvery",
        "doNotUseMarginsForDrawingGridOrigin", "drawingGridHorizontalOrigin",
        "drawingGridVerticalOrigin", "doNotShadeFormData",
        "noPunctuationKerning", "characterSpacingControl", "printTwoOnOne",
        "strictFirstAndLastChars", "noLineBreaksAfter", "noLineBreaksBefore",
        "savePreviewPicture", "doNotValidateAgainstSchema", "saveInvalidXml",
        "ignoreMixedContent", "alwaysShowPlaceholderText",
        "doNotDemarcateInvalidXml", "saveXmlDataOnly", "useXSLTWhenSaving",
        "saveThroughXslt", "showXMLTags", "alwaysMergeEmptyNamespace",
        "updateFields", "hdrShapeDefaults", "footnotePr", "endnotePr", "compat",
        "docVars", "rsids", "mathPr", "uiCompat97To2003", "attachedSchema",
        "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats",
        "doNotAutoCompressPictures", "forceUpgrade", "captions",
        "readModeInkLockDown", "smartTagType", "schemaLibrary", "shapeDefaults",
        "doNotEmbedSmartTags", "decimalSymbol", "listSeparator"],
    "theme": ["themeElements", "objectDefaults", "extraClrSchemeLst"],
    "themeElements": ["clrScheme", "fontScheme", "fmtScheme"],
    "clrScheme": ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3",
                  "accent4", "accent5", "accent6", "hlink", "folHlink"],
    "fontScheme": ["majorFont", "minorFont"],
    "majorFont": ["latin", "ea", "cs", "font"],
    "minorFont": ["latin", "ea", "cs", "font"],
    "fmtScheme": ["fillStyleLst", "lnStyleLst", "effectStyleLst",
                  "bgFillStyleLst"],
    "app": ["Template", "Manager", "Company", "Pages", "Words", "Characters",
            "PresentationFormat", "Lines", "Paragraphs", "Slides", "Notes",
            "TotalTime", "HiddenSlides", "MMClips", "ScaleCrop",
            "HeadingPairs", "TitlesOfParts", "LinksUpToDate",
            "CharactersWithSpaces", "SharedDoc", "HyperlinkBase", "HLinks",
            "HyperlinksChanged", "DigSig", "Application", "AppVersion",
            "DocSecurity"],
}

ILLEGAL_XML_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
CJK_RE = re.compile("[\u2e80-\u9fff\uf900-\ufaff\ufe10-\ufe4f\uff00-\uffef]")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _load(path_or_bytes):
    if isinstance(path_or_bytes, (bytes, bytearray)):
        import io
        return zipfile.ZipFile(io.BytesIO(bytes(path_or_bytes)))
    return zipfile.ZipFile(path_or_bytes)


def _order_violations(root, limit=8):
    """Depth-first walk comparing children against the schema sequences."""
    bad = []
    for parent in root.iter():
        seq = SEQ.get(_local(parent.tag))
        if not seq:
            continue
        seen = -1
        for child in parent:
            name = _local(child.tag)
            if name not in seq:
                continue
            idx = seq.index(name)
            if idx < seen:
                bad.append("<w:%s> has <w:%s> out of order" % (_local(parent.tag), name))
                if len(bad) >= limit:
                    return bad
            seen = idx
    return bad


def check_package(path_or_bytes, expected_words=None, stage="s5b_docx",
                  keep_text=False):
    rep = Report(stage)
    try:
        z = _load(path_or_bytes)
    except Exception as exc:  # noqa: BLE001
        rep.check("package opens as a zip", False, repr(exc))
        return rep, ""

    names = z.namelist()
    rep.check("package opens as a zip", True, "%d parts" % len(names))
    missing = [p for p in REQUIRED_PARTS if p not in names]
    rep.check("all required OOXML parts present", not missing,
              "missing: %s" % missing if missing else "%d parts" % len(names))

    parts = {}
    parse_errors = []
    for n in names:
        if not n.endswith(".xml") and not n.endswith(".rels"):
            continue
        raw = z.read(n)
        if not raw.strip():
            parse_errors.append("%s is empty" % n)
            continue
        try:
            parts[n] = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            parse_errors.append("%s: %s" % (n, exc))
    rep.check("every XML part is well-formed", not parse_errors,
              "; ".join(parse_errors[:4]))

    control = [n for n in names if ILLEGAL_XML_RE.search(
        z.read(n).decode("utf-8", "replace"))]
    rep.check("no XML-illegal control characters", not control, str(control[:4]))

    # -- content types + relationships -------------------------------------
    ct = parts.get("[Content_Types].xml")
    if ct is not None:
        declared = {e.get("PartName") for e in ct.findall(CT + "Override")}
        undeclared = [("/" + p) for p in REQUIRED_PARTS
                      if not p.endswith(".rels")
                      and p != "[Content_Types].xml" and ("/" + p) not in declared]
        rep.check("[Content_Types].xml declares every part", not undeclared,
                  str(undeclared))
    else:
        rep.check("[Content_Types].xml declares every part", False, "part missing")

    dangling = []
    for rels_name in [n for n in names if n.endswith(".rels")]:
        base = os.path.dirname(os.path.dirname(rels_name))
        rels = parts.get(rels_name)
        if rels is None:
            continue
        for rel in rels.findall(PR + "Relationship"):
            if rel.get("TargetMode") == "External":
                continue
            target = os.path.normpath(os.path.join(base, rel.get("Target", "")))
            target = target.replace("\\", "/")
            if target not in names:
                dangling.append("%s -> %s" % (rels_name, rel.get("Target")))
    rep.check("every relationship target exists", not dangling, str(dangling[:5]))

    doc = parts.get("word/document.xml")
    if doc is None:
        rep.check("word/document.xml parses", False, "missing")
        return rep, ""
    rep.check("word/document.xml parses", True)

    rels = parts.get("word/_rels/document.xml.rels")
    rid_targets = {}
    if rels is not None:
        for rel in rels.findall(PR + "Relationship"):
            rid_targets[rel.get("Id")] = rel.get("Target")
    used_rids = {el.get(R + "id") for el in doc.iter() if el.get(R + "id")}
    unresolved = sorted(r for r in used_rids if r not in rid_targets)
    rep.check("every r:id used in document.xml resolves", not unresolved,
              str(unresolved))

    # -- schema order -------------------------------------------------------
    bad = _order_violations(doc)
    rep.check("document.xml child order matches ECMA-376 sequences", not bad,
              "; ".join(bad))
    for part in ("word/styles.xml", "word/settings.xml", "word/fontTable.xml",
                 "docProps/app.xml", "word/theme/theme1.xml"):
        if part in parts:
            part_bad = _order_violations(parts[part])
            rep.check("%s child order" % os.path.basename(part), not part_bad,
                      "; ".join(part_bad))

    # -- fonts --------------------------------------------------------------
    used_fonts, declared_fonts = set(), set()
    for part_name, root in parts.items():
        for el in root.iter():
            if _local(el.tag) in ("rFonts", "font"):
                for k, v in el.attrib.items():
                    if _local(k) in ("ascii", "hAnsi", "eastAsia", "cs",
                                     "name") and v:
                        (used_fonts if _local(el.tag) == "rFonts"
                         else declared_fonts).add(v)
    stray = sorted(f for f in used_fonts if f not in ALLOWED_FONTS)
    rep.check("only WPS/Windows-guaranteed fonts are referenced", not stray,
              "stray: %s" % stray if stray else "used: %s" % sorted(used_fonts))
    undeclared = sorted(used_fonts - declared_fonts)
    rep.check("every referenced font is declared in fontTable.xml",
              not undeclared, str(undeclared))

    # -- runs ---------------------------------------------------------------
    runs = [el for el in doc.iter(W + "r") if el.find(W + "t") is not None]
    no_fonts = no_lang = no_szcs = 0
    hint_mismatch = []
    for run in runs:
        rpr = run.find(W + "rPr")
        fonts = rpr.find(W + "rFonts") if rpr is not None else None
        text = "".join(t.text or "" for t in run.findall(W + "t"))
        if fonts is None or not all(fonts.get(W + k) for k in
                                    ("ascii", "hAnsi", "eastAsia", "cs")):
            no_fonts += 1
        elif bool(fonts.get(W + "hint") == "eastAsia") != bool(CJK_RE.search(text)):
            hint_mismatch.append(text[:24])
        if rpr is None or rpr.find(W + "lang") is None:
            no_lang += 1
        if rpr is None or rpr.find(W + "sz") is None or rpr.find(W + "szCs") is None:
            no_szcs += 1
    rep.check("every text run sets ascii/hAnsi/eastAsia/cs", no_fonts == 0,
              "%d of %d runs incomplete" % (no_fonts, len(runs)))
    rep.check("every text run sets w:lang", no_lang == 0, "%d runs" % no_lang)
    rep.check("every text run pairs w:sz with w:szCs", no_szcs == 0,
              "%d runs" % no_szcs)
    rep.check("hint=eastAsia exactly on runs containing CJK", not hint_mismatch,
              "%d mismatches e.g. %s" % (len(hint_mismatch), hint_mismatch[:3]))

    # -- table geometry -----------------------------------------------------
    tbls = list(doc.iter(W + "tbl"))
    if tbls:
        tbl = tbls[0]
        tbl_pr = tbl.find(W + "tblPr")
        grid_el = tbl.find(W + "tblGrid")
        if grid_el is None or tbl_pr is None or tbl_pr.find(W + "tblW") is None:
            # A package this incomplete is already flagged above; report it here
            # instead of raising, so the gate always produces a full verdict.
            rep.check("table grid width equals w:tblW", False,
                      "w:tblGrid or w:tblPr/w:tblW missing")
        else:
            grid = [int(g.get(W + "w") or 0) for g in grid_el.findall(W + "gridCol")]
            tblw = int(tbl_pr.find(W + "tblW").get(W + "w") or 0)
            rep.check("table grid width equals w:tblW", sum(grid) == tblw,
                      "grid=%s sum=%d tblW=%d" % (grid, sum(grid), tblw))
        rep.check("table uses fixed layout",
                  tbl_pr is not None and tbl_pr.find(W + "tblLayout") is not None, "")
        rows = tbl.findall(W + "tr")
        header = None
        if rows:
            tr_pr = rows[0].find(W + "trPr")
            header = tr_pr.find(W + "tblHeader") if tr_pr is not None else None
        rep.check("header row repeats across pages", header is not None, "")
        body = doc.find(W + "body")
        rep.check("w:sectPr is the last body element",
                  body is not None and len(body) > 0
                  and _local(body[-1].tag) == "sectPr", "")

    # -- text extraction ----------------------------------------------------
    text_parts = []
    for p in doc.iter(W + "p"):
        text_parts.append("".join(t.text or "" for t in p.iter(W + "t")))
    text = "\n".join(text_parts)
    rep.check("document carries extractable text", len(text) > 40,
              "%d chars" % len(text))

    if expected_words is not None:
        words = list(expected_words)
        missing_word = [w.get("word", "") for w in words
                        if (w.get("word") or "") not in text]
        rep.check("every word appears in the document", not missing_word,
                  "%d missing e.g. %s" % (len(missing_word), missing_word[:5]))
        missing_cn = [w.get("word", "") for w in words
                      if (w.get("def_cn") or "").strip()
                      and w["def_cn"].strip() not in text]
        rep.check("every def_cn appears in the document", not missing_cn,
                  "%d missing e.g. %s" % (len(missing_cn), missing_cn[:5]))
        with_en = [w for w in words if (w.get("def_en") or "").strip()]
        missing_en = [w.get("word", "") for w in with_en
                      if w["def_en"].strip() not in text]
        rep.check("every def_en appears in the document", not missing_en,
                  "%d/%d missing e.g. %s" % (len(missing_en), len(with_en),
                                             missing_en[:5]))
        if tbls:
            rows = tbls[0].findall(W + "tr")
            rep.check("table has one row per word plus a header",
                      len(rows) == len(words) + 1,
                      "%d rows for %d words" % (len(rows), len(words)))
        rep.check("declared word count matches the payload",
                  ("共收录 %d 个学术词汇" % len(words)) in text,
                  "meta line: %s" % next((l for l in text_parts if "共收录" in l),
                                         "")[:60])

    payload = rep.write()
    return rep, (text if keep_text else payload)


def load_words(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("words", []) if isinstance(data, dict) else data


def main():
    ap = argparse.ArgumentParser(description=".docx conformance gate")
    ap.add_argument("docx")
    ap.add_argument("--words", help="deck JSON for the content round-trip gate")
    ap.add_argument("--stage", default="s5b_docx")
    ap.add_argument("--dump-text", action="store_true")
    args = ap.parse_args()

    expected = load_words(args.words) if args.words else None
    rep, text = check_package(args.docx, expected, stage=args.stage,
                              keep_text=args.dump_text)
    if args.dump_text:
        print(text)
    print("\nRESULT: %s (%d passed / %d failed)"
          % ("PASS" if rep.ok else "FAIL",
             sum(1 for c in rep.checks if c["ok"]),
             sum(1 for c in rep.checks if not c["ok"])))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
