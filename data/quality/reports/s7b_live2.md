# Gate report - s7b_live2

- finished: 2026-09-21 17:03:19
- result: **PASS** (389 passed / 0 failed)

- [x] word sources reachable over HTTP — episode:ep01=117, episode:ep02=215, episode:ep03=44, episode:yale_ep01=32, collection:harvard_justice=381, collection:exam_vocabulary=6678, collection:yale_philosophy=32, collection:custom_imports=12, vocab-bank=3568
- [x] episode:ep01/docx: HTTP 200 — status=200
- [x] episode:ep01/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] episode:ep01/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep01_Study_Guide.docx"; filename*=UTF-8''ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Study
- [x] episode:ep01/docx: response headers are latin-1 safe
- [x] episode:ep01/docx: body is not empty — 28023 bytes
- [x] episode:ep01/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] episode:ep01/docx: Content-Length matches the body — 28023 vs 28023
- [x] episode:ep01/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] episode:ep01/study_guide_md: HTTP 200 — status=200
- [x] episode:ep01/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] episode:ep01/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep01_Study_Guide.md"; filename*=UTF-8''ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Study_G
- [x] episode:ep01/study_guide_md: response headers are latin-1 safe
- [x] episode:ep01/study_guide_md: body is not empty — 32120 bytes
- [x] episode:ep01/study_guide_md: body is valid UTF-8 text — 30101 chars
- [x] episode:ep01/study_guide_md: body is not an error message — # 🏛️ ep01_精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释义 | 课堂原声例句 | 中文翻译 |
| :--
- [x] episode:ep01/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] episode:ep01/study_guide_md: English definitions (117) present in study_guide_md — 0 missing e.g. []
- [x] episode:ep01/anki_csv: HTTP 200 — status=200
- [x] episode:ep01/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] episode:ep01/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep01_Anki.csv"; filename*=UTF-8''ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Anki.csv
- [x] episode:ep01/anki_csv: response headers are latin-1 safe
- [x] episode:ep01/anki_csv: body is not empty — 189095 bytes
- [x] episode:ep01/anki_csv: body is valid UTF-8 text — 183982 chars
- [x] episode:ep01/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
"<div style='font-family:sans-serif; text-ali
- [x] episode:ep01/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] episode:ep01/anki_csv: English definitions (117) present in anki_csv — 0 missing e.g. []
- [x] episode:ep01/eudic_quizlet: HTTP 200 — status=200
- [x] episode:ep01/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:ep01/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep01_Eudic_Quizlet.txt"; filename*=UTF-8''ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Eudi
- [x] episode:ep01/eudic_quizlet: response headers are latin-1 safe
- [x] episode:ep01/eudic_quizlet: body is not empty — 29263 bytes
- [x] episode:ep01/eudic_quizlet: body is valid UTF-8 text — 27350 chars
- [x] episode:ep01/eudic_quizlet: body is not an error message — trolley	/ˈtrɒli/ n. 有轨电车；手推车\nan electric vehicle running on rails that carries passengers along city streets	This is a 
- [x] episode:ep01/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] episode:ep01/eudic_quizlet: English definitions (117) present in eudic_quizlet — 0 missing e.g. []
- [x] episode:ep01/words_only: HTTP 200 — status=200
- [x] episode:ep01/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:ep01/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep01_Words_Only.txt"; filename*=UTF-8''ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Words_O
- [x] episode:ep01/words_only: response headers are latin-1 safe
- [x] episode:ep01/words_only: body is not empty — 1128 bytes
- [x] episode:ep01/words_only: body is valid UTF-8 text — 1128 chars
- [x] episode:ep01/words_only: body is not an error message — trolley
murder
genocide
justifies
sacrificing
onlooker
mentality
totalitarianism
circumstance
endorsed
reconciling
where
- [x] episode:ep01/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] episode:ep02/docx: HTTP 200 — status=200
- [x] episode:ep02/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] episode:ep02/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep02_Study_Guide.docx"; filename*=UTF-8''ep02_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Study
- [x] episode:ep02/docx: response headers are latin-1 safe
- [x] episode:ep02/docx: body is not empty — 45293 bytes
- [x] episode:ep02/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] episode:ep02/docx: Content-Length matches the body — 45293 vs 45293
- [x] episode:ep02/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] episode:ep02/study_guide_md: HTTP 200 — status=200
- [x] episode:ep02/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] episode:ep02/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep02_Study_Guide.md"; filename*=UTF-8''ep02_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Study_G
- [x] episode:ep02/study_guide_md: response headers are latin-1 safe
- [x] episode:ep02/study_guide_md: body is not empty — 63644 bytes
- [x] episode:ep02/study_guide_md: body is valid UTF-8 text — 58800 chars
- [x] episode:ep02/study_guide_md: body is not an error message — # 🏛️ ep02_精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释义 | 课堂原声例句 | 中文翻译 |
| :--
- [x] episode:ep02/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] episode:ep02/study_guide_md: English definitions (215) present in study_guide_md — 0 missing e.g. []
- [x] episode:ep02/anki_csv: HTTP 200 — status=200
- [x] episode:ep02/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] episode:ep02/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep02_Anki.csv"; filename*=UTF-8''ep02_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Anki.csv
- [x] episode:ep02/anki_csv: response headers are latin-1 safe
- [x] episode:ep02/anki_csv: body is not empty — 358637 bytes
- [x] episode:ep02/anki_csv: body is valid UTF-8 text — 346796 chars
- [x] episode:ep02/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
"<div style='font-family:sans-serif; text-ali
- [x] episode:ep02/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] episode:ep02/anki_csv: English definitions (215) present in anki_csv — 0 missing e.g. []
- [x] episode:ep02/eudic_quizlet: HTTP 200 — status=200
- [x] episode:ep02/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:ep02/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep02_Eudic_Quizlet.txt"; filename*=UTF-8''ep02_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Eudi
- [x] episode:ep02/eudic_quizlet: response headers are latin-1 safe
- [x] episode:ep02/eudic_quizlet: body is not empty — 58533 bytes
- [x] episode:ep02/eudic_quizlet: body is valid UTF-8 text — 53795 chars
- [x] episode:ep02/eudic_quizlet: body is not an error message — cannibalism	/ˈkænɪbəlɪzəm/ n. 食人；同类相食\nthe practice of eating the flesh of one's own species	Last time we argued about t
- [x] episode:ep02/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] episode:ep02/eudic_quizlet: English definitions (215) present in eudic_quizlet — 0 missing e.g. []
- [x] episode:ep02/words_only: HTTP 200 — status=200
- [x] episode:ep02/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:ep02/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep02_Words_Only.txt"; filename*=UTF-8''ep02_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Words_O
- [x] episode:ep02/words_only: response headers are latin-1 safe
- [x] episode:ep02/words_only: body is not empty — 2496 bytes
- [x] episode:ep02/words_only: body is valid UTF-8 text — 2496 chars
- [x] episode:ep02/words_only: body is not an error message — cannibalism
utilitarian
jurisprudence
moral philosophy
principle
maximize
general welfare
utility
sovereign
take account
- [x] episode:ep02/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] episode:ep03/docx: HTTP 200 — status=200
- [x] episode:ep03/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] episode:ep03/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep03_Study_Guide.docx"; filename*=UTF-8''ep03_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Study
- [x] episode:ep03/docx: response headers are latin-1 safe
- [x] episode:ep03/docx: body is not empty — 15395 bytes
- [x] episode:ep03/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] episode:ep03/docx: Content-Length matches the body — 15395 vs 15395
- [x] episode:ep03/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] episode:ep03/study_guide_md: HTTP 200 — status=200
- [x] episode:ep03/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] episode:ep03/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep03_Study_Guide.md"; filename*=UTF-8''ep03_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Study_G
- [x] episode:ep03/study_guide_md: response headers are latin-1 safe
- [x] episode:ep03/study_guide_md: body is not empty — 12265 bytes
- [x] episode:ep03/study_guide_md: body is valid UTF-8 text — 11458 chars
- [x] episode:ep03/study_guide_md: body is not an error message — # 🏛️ ep03_精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释义 | 课堂原声例句 | 中文翻译 |
| :--
- [x] episode:ep03/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] episode:ep03/study_guide_md: English definitions (44) present in study_guide_md — 0 missing e.g. []
- [x] episode:ep03/anki_csv: HTTP 200 — status=200
- [x] episode:ep03/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] episode:ep03/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep03_Anki.csv"; filename*=UTF-8''ep03_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Anki.csv
- [x] episode:ep03/anki_csv: response headers are latin-1 safe
- [x] episode:ep03/anki_csv: body is not empty — 71053 bytes
- [x] episode:ep03/anki_csv: body is valid UTF-8 text — 69167 chars
- [x] episode:ep03/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
<div style='font-family:sans-serif; text-alig
- [x] episode:ep03/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] episode:ep03/anki_csv: English definitions (44) present in anki_csv — 0 missing e.g. []
- [x] episode:ep03/eudic_quizlet: HTTP 200 — status=200
- [x] episode:ep03/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:ep03/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep03_Eudic_Quizlet.txt"; filename*=UTF-8''ep03_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Eudi
- [x] episode:ep03/eudic_quizlet: response headers are latin-1 safe
- [x] episode:ep03/eudic_quizlet: body is not empty — 11032 bytes
- [x] episode:ep03/eudic_quizlet: body is valid UTF-8 text — 10331 chars
- [x] episode:ep03/eudic_quizlet: body is not an error message — libertarian	/ˌlɪbərˈteəriən/ n./adj. 自由至上主义者；自由至上主义的\na person who believes that individual freedom should be protected 
- [x] episode:ep03/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] episode:ep03/eudic_quizlet: English definitions (44) present in eudic_quizlet — 0 missing e.g. []
- [x] episode:ep03/words_only: HTTP 200 — status=200
- [x] episode:ep03/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:ep03/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="ep03_Words_Only.txt"; filename*=UTF-8''ep03_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Words_O
- [x] episode:ep03/words_only: response headers are latin-1 safe
- [x] episode:ep03/words_only: body is not empty — 429 bytes
- [x] episode:ep03/words_only: body is valid UTF-8 text — 429 chars
- [x] episode:ep03/words_only: body is not an error message — libertarian
libertarianism
coercion
redistribution
paternalist
proprietors
acquisition
violation
legislation
taxation
th
- [x] episode:ep03/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] episode:yale_ep01/docx: HTTP 200 — status=200
- [x] episode:yale_ep01/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] episode:yale_ep01/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="yale_ep01_Study_Guide.docx"; filename*=UTF-8''yale_ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%8
- [x] episode:yale_ep01/docx: response headers are latin-1 safe
- [x] episode:yale_ep01/docx: body is not empty — 17180 bytes
- [x] episode:yale_ep01/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] episode:yale_ep01/docx: Content-Length matches the body — 17180 vs 17180
- [x] episode:yale_ep01/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] episode:yale_ep01/study_guide_md: HTTP 200 — status=200
- [x] episode:yale_ep01/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] episode:yale_ep01/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="yale_ep01_Study_Guide.md"; filename*=UTF-8''yale_ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%
- [x] episode:yale_ep01/study_guide_md: response headers are latin-1 safe
- [x] episode:yale_ep01/study_guide_md: body is not empty — 13721 bytes
- [x] episode:yale_ep01/study_guide_md: body is valid UTF-8 text — 9836 chars
- [x] episode:yale_ep01/study_guide_md: body is not an error message — # 🏛️ yale_ep01_精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释义 | 课堂原声例句 | 中文翻译 |

- [x] episode:yale_ep01/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] episode:yale_ep01/study_guide_md: English definitions (32) present in study_guide_md — 0 missing e.g. []
- [x] episode:yale_ep01/anki_csv: HTTP 200 — status=200
- [x] episode:yale_ep01/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] episode:yale_ep01/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="yale_ep01_Anki.csv"; filename*=UTF-8''yale_ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%8C_Ank
- [x] episode:yale_ep01/anki_csv: response headers are latin-1 safe
- [x] episode:yale_ep01/anki_csv: body is not empty — 60170 bytes
- [x] episode:yale_ep01/anki_csv: body is valid UTF-8 text — 52260 chars
- [x] episode:yale_ep01/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
<div style='font-family:sans-serif; text-alig
- [x] episode:yale_ep01/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] episode:yale_ep01/anki_csv: English definitions (32) present in anki_csv — 0 missing e.g. []
- [x] episode:yale_ep01/eudic_quizlet: HTTP 200 — status=200
- [x] episode:yale_ep01/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:yale_ep01/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="yale_ep01_Eudic_Quizlet.txt"; filename*=UTF-8''yale_ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%
- [x] episode:yale_ep01/eudic_quizlet: response headers are latin-1 safe
- [x] episode:yale_ep01/eudic_quizlet: body is not empty — 12747 bytes
- [x] episode:yale_ep01/eudic_quizlet: body is valid UTF-8 text — 8968 chars
- [x] episode:yale_ep01/eudic_quizlet: body is not an error message — harmony	/ˈhɑːrməni/ n. 和谐，融洽；协调\na state of peaceful agreement among different parts	Plato argues that justice in the so
- [x] episode:yale_ep01/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] episode:yale_ep01/eudic_quizlet: English definitions (32) present in eudic_quizlet — 0 missing e.g. []
- [x] episode:yale_ep01/words_only: HTTP 200 — status=200
- [x] episode:yale_ep01/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] episode:yale_ep01/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="yale_ep01_Words_Only.txt"; filename*=UTF-8''yale_ep01_%E7%B2%BE%E8%AF%BB%E6%89%8B%E5%86%
- [x] episode:yale_ep01/words_only: response headers are latin-1 safe
- [x] episode:yale_ep01/words_only: body is not empty — 438 bytes
- [x] episode:yale_ep01/words_only: body is valid UTF-8 text — 438 chars
- [x] episode:yale_ep01/words_only: body is not an error message — harmony
rational
conflict
virtue
reflection
proportion
flourish
instinct
discipline
perspective
eudaimonia
temperance
ap
- [x] episode:yale_ep01/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] collection:harvard_justice/docx: HTTP 200 — status=200
- [x] collection:harvard_justice/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] collection:harvard_justice/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="Justice_Study_Guide.docx"; filename*=UTF-8''%E5%93%88%E4%BD%9B%E5%A4%A7%E5%AD%A6%E3%80%8
- [x] collection:harvard_justice/docx: response headers are latin-1 safe
- [x] collection:harvard_justice/docx: body is not empty — 75010 bytes
- [x] collection:harvard_justice/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] collection:harvard_justice/docx: Content-Length matches the body — 75010 vs 75010
- [x] collection:harvard_justice/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] collection:harvard_justice/study_guide_md: HTTP 200 — status=200
- [x] collection:harvard_justice/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] collection:harvard_justice/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="Justice_Study_Guide.md"; filename*=UTF-8''%E5%93%88%E4%BD%9B%E5%A4%A7%E5%AD%A6%E3%80%8A%
- [x] collection:harvard_justice/study_guide_md: response headers are latin-1 safe
- [x] collection:harvard_justice/study_guide_md: body is not empty — 109552 bytes
- [x] collection:harvard_justice/study_guide_md: body is valid UTF-8 text — 101910 chars
- [x] collection:harvard_justice/study_guide_md: body is not an error message — # 🏛️ 哈佛大学《公正：该如何做是好？》(Justice)_合集精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释义 
- [x] collection:harvard_justice/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] collection:harvard_justice/study_guide_md: English definitions (381) present in study_guide_md — 0 missing e.g. []
- [x] collection:harvard_justice/anki_csv: HTTP 200 — status=200
- [x] collection:harvard_justice/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] collection:harvard_justice/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="Justice_Anki.csv"; filename*=UTF-8''%E5%93%88%E4%BD%9B%E5%A4%A7%E5%AD%A6%E3%80%8A%E5%85%
- [x] collection:harvard_justice/anki_csv: response headers are latin-1 safe
- [x] collection:harvard_justice/anki_csv: body is not empty — 627887 bytes
- [x] collection:harvard_justice/anki_csv: body is valid UTF-8 text — 608696 chars
- [x] collection:harvard_justice/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
"<div style='font-family:sans-serif; text-ali
- [x] collection:harvard_justice/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] collection:harvard_justice/anki_csv: English definitions (381) present in anki_csv — 0 missing e.g. []
- [x] collection:harvard_justice/eudic_quizlet: HTTP 200 — status=200
- [x] collection:harvard_justice/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:harvard_justice/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="Justice_Eudic_Quizlet.txt"; filename*=UTF-8''%E5%93%88%E4%BD%9B%E5%A4%A7%E5%AD%A6%E3%80%
- [x] collection:harvard_justice/eudic_quizlet: response headers are latin-1 safe
- [x] collection:harvard_justice/eudic_quizlet: body is not empty — 100563 bytes
- [x] collection:harvard_justice/eudic_quizlet: body is valid UTF-8 text — 93063 chars
- [x] collection:harvard_justice/eudic_quizlet: body is not an error message — trolley	/ˈtrɒli/ n. 有轨电车；手推车\nan electric vehicle running on rails that carries passengers along city streets	This is a 
- [x] collection:harvard_justice/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] collection:harvard_justice/eudic_quizlet: English definitions (381) present in eudic_quizlet — 0 missing e.g. []
- [x] collection:harvard_justice/words_only: HTTP 200 — status=200
- [x] collection:harvard_justice/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:harvard_justice/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="Justice_Words_Only.txt"; filename*=UTF-8''%E5%93%88%E4%BD%9B%E5%A4%A7%E5%AD%A6%E3%80%8A%
- [x] collection:harvard_justice/words_only: response headers are latin-1 safe
- [x] collection:harvard_justice/words_only: body is not empty — 4100 bytes
- [x] collection:harvard_justice/words_only: body is valid UTF-8 text — 4100 chars
- [x] collection:harvard_justice/words_only: body is not an error message — trolley
murder
genocide
justifies
sacrificing
onlooker
mentality
totalitarianism
circumstance
endorsed
reconciling
where
- [x] collection:harvard_justice/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] collection:exam_vocabulary/docx: HTTP 200 — status=200
- [x] collection:exam_vocabulary/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] collection:exam_vocabulary/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="GRE_Study_Guide.docx"; filename*=UTF-8''%E8%80%83%E8%AF%95%E4%B8%8E%E5%AD%A6%E6%9C%AF%E8
- [x] collection:exam_vocabulary/docx: response headers are latin-1 safe
- [x] collection:exam_vocabulary/docx: body is not empty — 1074631 bytes
- [x] collection:exam_vocabulary/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] collection:exam_vocabulary/docx: Content-Length matches the body — 1074631 vs 1074631
- [x] collection:exam_vocabulary/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] collection:exam_vocabulary/study_guide_md: HTTP 200 — status=200
- [x] collection:exam_vocabulary/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] collection:exam_vocabulary/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="GRE_Study_Guide.md"; filename*=UTF-8''%E8%80%83%E8%AF%95%E4%B8%8E%E5%AD%A6%E6%9C%AF%E8%A
- [x] collection:exam_vocabulary/study_guide_md: response headers are latin-1 safe
- [x] collection:exam_vocabulary/study_guide_md: body is not empty — 1243980 bytes
- [x] collection:exam_vocabulary/study_guide_md: body is valid UTF-8 text — 1103963 chars
- [x] collection:exam_vocabulary/study_guide_md: body is not an error message — # 🏛️ 考试与学术词汇（托福 / 雅思 / GRE / 考研 / 学术词组）_合集精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释
- [x] collection:exam_vocabulary/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] collection:exam_vocabulary/study_guide_md: English definitions (6650) present in study_guide_md — 0 missing e.g. []
- [x] collection:exam_vocabulary/anki_csv: HTTP 200 — status=200
- [x] collection:exam_vocabulary/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] collection:exam_vocabulary/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="GRE_Anki.csv"; filename*=UTF-8''%E8%80%83%E8%AF%95%E4%B8%8E%E5%AD%A6%E6%9C%AF%E8%AF%8D%E
- [x] collection:exam_vocabulary/anki_csv: response headers are latin-1 safe
- [x] collection:exam_vocabulary/anki_csv: body is not empty — 8717646 bytes
- [x] collection:exam_vocabulary/anki_csv: body is valid UTF-8 text — 8364398 chars
- [x] collection:exam_vocabulary/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
<div style='font-family:sans-serif; text-alig
- [x] collection:exam_vocabulary/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] collection:exam_vocabulary/anki_csv: English definitions (6650) present in anki_csv — 0 missing e.g. []
- [x] collection:exam_vocabulary/eudic_quizlet: HTTP 200 — status=200
- [x] collection:exam_vocabulary/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:exam_vocabulary/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="GRE_Eudic_Quizlet.txt"; filename*=UTF-8''%E8%80%83%E8%AF%95%E4%B8%8E%E5%AD%A6%E6%9C%AF%E
- [x] collection:exam_vocabulary/eudic_quizlet: response headers are latin-1 safe
- [x] collection:exam_vocabulary/eudic_quizlet: body is not empty — 1077733 bytes
- [x] collection:exam_vocabulary/eudic_quizlet: body is valid UTF-8 text — 937864 chars
- [x] collection:exam_vocabulary/eudic_quizlet: body is not an error message — account for	 对…负有责任；对…做出解释；说明……的原因；导致；（比例）占\nto explain or give a reason for something	 ()
in spite of	 不管\neven though 
- [x] collection:exam_vocabulary/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] collection:exam_vocabulary/eudic_quizlet: English definitions (6650) present in eudic_quizlet — 0 missing e.g. []
- [x] collection:exam_vocabulary/words_only: HTTP 200 — status=200
- [x] collection:exam_vocabulary/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:exam_vocabulary/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="GRE_Words_Only.txt"; filename*=UTF-8''%E8%80%83%E8%AF%95%E4%B8%8E%E5%AD%A6%E6%9C%AF%E8%A
- [x] collection:exam_vocabulary/words_only: response headers are latin-1 safe
- [x] collection:exam_vocabulary/words_only: body is not empty — 62811 bytes
- [x] collection:exam_vocabulary/words_only: body is valid UTF-8 text — 62811 chars
- [x] collection:exam_vocabulary/words_only: body is not an error message — account for
in spite of
per capita
space shuttle
tinplate
conciseness
hirsute
airsickness
quadrilateral
reheating
embryo
- [x] collection:exam_vocabulary/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] collection:yale_philosophy/docx: HTTP 200 — status=200
- [x] collection:yale_philosophy/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] collection:yale_philosophy/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="Human_Nature_Study_Guide.docx"; filename*=UTF-8''%E8%80%B6%E9%B2%81%E5%A4%A7%E5%AD%A6%E3
- [x] collection:yale_philosophy/docx: response headers are latin-1 safe
- [x] collection:yale_philosophy/docx: body is not empty — 17265 bytes
- [x] collection:yale_philosophy/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] collection:yale_philosophy/docx: Content-Length matches the body — 17265 vs 17265
- [x] collection:yale_philosophy/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] collection:yale_philosophy/study_guide_md: HTTP 200 — status=200
- [x] collection:yale_philosophy/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] collection:yale_philosophy/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="Human_Nature_Study_Guide.md"; filename*=UTF-8''%E8%80%B6%E9%B2%81%E5%A4%A7%E5%AD%A6%E3%8
- [x] collection:yale_philosophy/study_guide_md: response headers are latin-1 safe
- [x] collection:yale_philosophy/study_guide_md: body is not empty — 13771 bytes
- [x] collection:yale_philosophy/study_guide_md: body is valid UTF-8 text — 9856 chars
- [x] collection:yale_philosophy/study_guide_md: body is not an error message — # 🏛️ 耶鲁大学《哲学与人性科学》(Human Nature)_合集精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释
- [x] collection:yale_philosophy/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] collection:yale_philosophy/study_guide_md: English definitions (32) present in study_guide_md — 0 missing e.g. []
- [x] collection:yale_philosophy/anki_csv: HTTP 200 — status=200
- [x] collection:yale_philosophy/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] collection:yale_philosophy/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="Human_Nature_Anki.csv"; filename*=UTF-8''%E8%80%B6%E9%B2%81%E5%A4%A7%E5%AD%A6%E3%80%8A%E
- [x] collection:yale_philosophy/anki_csv: response headers are latin-1 safe
- [x] collection:yale_philosophy/anki_csv: body is not empty — 60170 bytes
- [x] collection:yale_philosophy/anki_csv: body is valid UTF-8 text — 52260 chars
- [x] collection:yale_philosophy/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
<div style='font-family:sans-serif; text-alig
- [x] collection:yale_philosophy/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] collection:yale_philosophy/anki_csv: English definitions (32) present in anki_csv — 0 missing e.g. []
- [x] collection:yale_philosophy/eudic_quizlet: HTTP 200 — status=200
- [x] collection:yale_philosophy/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:yale_philosophy/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="Human_Nature_Eudic_Quizlet.txt"; filename*=UTF-8''%E8%80%B6%E9%B2%81%E5%A4%A7%E5%AD%A6%E
- [x] collection:yale_philosophy/eudic_quizlet: response headers are latin-1 safe
- [x] collection:yale_philosophy/eudic_quizlet: body is not empty — 12747 bytes
- [x] collection:yale_philosophy/eudic_quizlet: body is valid UTF-8 text — 8968 chars
- [x] collection:yale_philosophy/eudic_quizlet: body is not an error message — harmony	/ˈhɑːrməni/ n. 和谐，融洽；协调\na state of peaceful agreement among different parts	Plato argues that justice in the so
- [x] collection:yale_philosophy/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] collection:yale_philosophy/eudic_quizlet: English definitions (32) present in eudic_quizlet — 0 missing e.g. []
- [x] collection:yale_philosophy/words_only: HTTP 200 — status=200
- [x] collection:yale_philosophy/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:yale_philosophy/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="Human_Nature_Words_Only.txt"; filename*=UTF-8''%E8%80%B6%E9%B2%81%E5%A4%A7%E5%AD%A6%E3%8
- [x] collection:yale_philosophy/words_only: response headers are latin-1 safe
- [x] collection:yale_philosophy/words_only: body is not empty — 438 bytes
- [x] collection:yale_philosophy/words_only: body is valid UTF-8 text — 438 chars
- [x] collection:yale_philosophy/words_only: body is not an error message — harmony
rational
conflict
virtue
reflection
proportion
flourish
instinct
discipline
perspective
eudaimonia
temperance
ap
- [x] collection:yale_philosophy/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] collection:custom_imports/docx: HTTP 200 — status=200
- [x] collection:custom_imports/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] collection:custom_imports/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="User_Imports_Study_Guide.docx"; filename*=UTF-8''%E6%B3%95%E7%90%86%E5%AD%A6%E4%B8%8E%E5
- [x] collection:custom_imports/docx: response headers are latin-1 safe
- [x] collection:custom_imports/docx: body is not empty — 10267 bytes
- [x] collection:custom_imports/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] collection:custom_imports/docx: Content-Length matches the body — 10267 vs 10267
- [x] collection:custom_imports/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] collection:custom_imports/study_guide_md: HTTP 200 — status=200
- [x] collection:custom_imports/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] collection:custom_imports/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="User_Imports_Study_Guide.md"; filename*=UTF-8''%E6%B3%95%E7%90%86%E5%AD%A6%E4%B8%8E%E5%8
- [x] collection:custom_imports/study_guide_md: response headers are latin-1 safe
- [x] collection:custom_imports/study_guide_md: body is not empty — 5500 bytes
- [x] collection:custom_imports/study_guide_md: body is valid UTF-8 text — 3974 chars
- [x] collection:custom_imports/study_guide_md: body is not an error message — # 🏛️ 法理学与公共伦理名家研讨合集 (User Imports)_合集精读手册 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英
- [x] collection:custom_imports/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] collection:custom_imports/study_guide_md: English definitions (12) present in study_guide_md — 0 missing e.g. []
- [x] collection:custom_imports/anki_csv: HTTP 200 — status=200
- [x] collection:custom_imports/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] collection:custom_imports/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="User_Imports_Anki.csv"; filename*=UTF-8''%E6%B3%95%E7%90%86%E5%AD%A6%E4%B8%8E%E5%85%AC%E
- [x] collection:custom_imports/anki_csv: response headers are latin-1 safe
- [x] collection:custom_imports/anki_csv: body is not empty — 22983 bytes
- [x] collection:custom_imports/anki_csv: body is valid UTF-8 text — 20075 chars
- [x] collection:custom_imports/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
"<div style='font-family:sans-serif; text-ali
- [x] collection:custom_imports/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] collection:custom_imports/anki_csv: English definitions (12) present in anki_csv — 0 missing e.g. []
- [x] collection:custom_imports/eudic_quizlet: HTTP 200 — status=200
- [x] collection:custom_imports/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:custom_imports/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="User_Imports_Eudic_Quizlet.txt"; filename*=UTF-8''%E6%B3%95%E7%90%86%E5%AD%A6%E4%B8%8E%E
- [x] collection:custom_imports/eudic_quizlet: response headers are latin-1 safe
- [x] collection:custom_imports/eudic_quizlet: body is not empty — 4912 bytes
- [x] collection:custom_imports/eudic_quizlet: body is valid UTF-8 text — 3524 chars
- [x] collection:custom_imports/eudic_quizlet: body is not an error message — utilitarianism	/ˌjuːtɪlɪˈteəriənɪzəm/ n. 功利主义（以最大幸福为道德标准的伦理理论）\nthe belief that the right action is the one that produce
- [x] collection:custom_imports/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] collection:custom_imports/eudic_quizlet: English definitions (12) present in eudic_quizlet — 0 missing e.g. []
- [x] collection:custom_imports/words_only: HTTP 200 — status=200
- [x] collection:custom_imports/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] collection:custom_imports/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="User_Imports_Words_Only.txt"; filename*=UTF-8''%E6%B3%95%E7%90%86%E5%AD%A6%E4%B8%8E%E5%8
- [x] collection:custom_imports/words_only: response headers are latin-1 safe
- [x] collection:custom_imports/words_only: body is not empty — 205 bytes
- [x] collection:custom_imports/words_only: body is valid UTF-8 text — 205 chars
- [x] collection:custom_imports/words_only: body is not an error message — utilitarianism
deontological ethics
principle of utility
general welfare
jurisprudence
consequentialist
human dignity
de
- [x] collection:custom_imports/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] vocab-bank/docx: HTTP 200 — status=200
- [x] vocab-bank/docx: Content-Type is application/vnd.openxmlformats-officedocument.wordprocessingml.document — application/vnd.openxmlformats-officedocument.wordprocessingml.document
- [x] vocab-bank/docx: Content-Disposition has an ASCII filename and filename* — attachment; filename="Harvard_Justice_Universal_Vocab_Bank_Study_Guide.docx"; filename*=UTF-8''Harvard_Justice
- [x] vocab-bank/docx: response headers are latin-1 safe
- [x] vocab-bank/docx: body is not empty — 754676 bytes
- [x] vocab-bank/docx: body is really a zip package — magic=b'PK\x03\x04\x14\x00\x00\x00'
- [x] vocab-bank/docx: Content-Length matches the body — 754676 vs 754676
- [x] vocab-bank/docx: embedded .docx passes the package gate — 0/30 checks failed
- [x] vocab-bank/study_guide_md: HTTP 200 — status=200
- [x] vocab-bank/study_guide_md: Content-Type is text/markdown — text/markdown; charset=utf-8
- [x] vocab-bank/study_guide_md: Content-Disposition has an ASCII filename and filename* — attachment; filename="Harvard_Justice_Universal_Vocab_Bank_Study_Guide.md"; filename*=UTF-8''Harvard_Justice_U
- [x] vocab-bank/study_guide_md: response headers are latin-1 safe
- [x] vocab-bank/study_guide_md: body is not empty — 830831 bytes
- [x] vocab-bank/study_guide_md: body is valid UTF-8 text — 677182 chars
- [x] vocab-bank/study_guide_md: body is not an error message — # 🏛️ Harvard_Justice_Universal_Vocab_Bank 听说精读词表手册

> 哈佛大学《Justice》公开课 · Michael Sandel 教授

| 序号 | 单词 | 音标 | 词性与中文释义 | 英
- [x] vocab-bank/study_guide_md: every word present in the study_guide_md payload — 0 missing e.g. []
- [x] vocab-bank/study_guide_md: English definitions (3568) present in study_guide_md — 0 missing e.g. []
- [x] vocab-bank/anki_csv: HTTP 200 — status=200
- [x] vocab-bank/anki_csv: Content-Type is text/csv — text/csv; charset=utf-8
- [x] vocab-bank/anki_csv: Content-Disposition has an ASCII filename and filename* — attachment; filename="Harvard_Justice_Universal_Vocab_Bank_Anki.csv"; filename*=UTF-8''Harvard_Justice_Univers
- [x] vocab-bank/anki_csv: response headers are latin-1 safe
- [x] vocab-bank/anki_csv: body is not empty — 5089126 bytes
- [x] vocab-bank/anki_csv: body is valid UTF-8 text — 4742724 chars
- [x] vocab-bank/anki_csv: body is not an error message — Front,Back,Word,Phonetic,Definition,EnglishDefinition,Example,Translation
"<div style='font-family:sans-serif; text-ali
- [x] vocab-bank/anki_csv: every word present in the anki_csv payload — 0 missing e.g. []
- [x] vocab-bank/anki_csv: English definitions (3568) present in anki_csv — 0 missing e.g. []
- [x] vocab-bank/eudic_quizlet: HTTP 200 — status=200
- [x] vocab-bank/eudic_quizlet: Content-Type is text/plain — text/plain; charset=utf-8
- [x] vocab-bank/eudic_quizlet: Content-Disposition has an ASCII filename and filename* — attachment; filename="Harvard_Justice_Universal_Vocab_Bank_Eudic_Quizlet.txt"; filename*=UTF-8''Harvard_Justic
- [x] vocab-bank/eudic_quizlet: response headers are latin-1 safe
- [x] vocab-bank/eudic_quizlet: body is not empty — 743026 bytes
- [x] vocab-bank/eudic_quizlet: body is valid UTF-8 text — 589475 chars
- [x] vocab-bank/eudic_quizlet: body is not an error message — utilitarianism	/ˌjuːtɪlɪˈteriənɪzəm/ n. 功利主义（以最大幸福为道德标准的伦理学说）\nthe belief that the right action is the one that produces
- [x] vocab-bank/eudic_quizlet: every word present in the eudic_quizlet payload — 0 missing e.g. []
- [x] vocab-bank/eudic_quizlet: English definitions (3568) present in eudic_quizlet — 0 missing e.g. []
- [x] vocab-bank/words_only: HTTP 200 — status=200
- [x] vocab-bank/words_only: Content-Type is text/plain — text/plain; charset=utf-8
- [x] vocab-bank/words_only: Content-Disposition has an ASCII filename and filename* — attachment; filename="Harvard_Justice_Universal_Vocab_Bank_Words_Only.txt"; filename*=UTF-8''Harvard_Justice_U
- [x] vocab-bank/words_only: response headers are latin-1 safe
- [x] vocab-bank/words_only: body is not empty — 35911 bytes
- [x] vocab-bank/words_only: body is valid UTF-8 text — 35911 chars
- [x] vocab-bank/words_only: body is not an error message — utilitarianism
consequentialist
categorical
trolley
sidetrack
conundrum
dilemma
onlooker
deliberation
cannibalism
shipwr
- [x] vocab-bank/words_only: every word present in the words_only payload — 0 missing e.g. []
- [x] CJK download title (the ticket's trigger) returns a real .docx — status=200 magic=b'PK\x03\x04\x14\x00\x00\x00'
