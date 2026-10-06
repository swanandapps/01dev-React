from app.models import TranscriptChunk
from app.retrieval.text import lexical_doc, lexical_fields, tokenize


def test_tokenize_keeps_acronyms_and_code_tokens():
    assert tokenize("What is an IIFE?") == ["iife"]
    assert tokenize("publish with np") == ["publish", "with", "np"]
    assert tokenize("useMemo vs React.memo") == ["usememo", "use", "memo", "react", "memo"]
    assert tokenize("innerHTML") == ["innerhtml", "inner", "html"]
    assert tokenize("ES modules and npm packages") == ["es", "module", "npm", "package"]
    assert tokenize("dependencies") == ["dependency"]


def test_tokenize_does_not_split_brand_names_or_mangle_short_words():
    assert tokenize("JavaScript and TypeScript") == ["javascript", "typescript"]
    assert tokenize("class status analysis uses") == ["class", "status", "analysis", "use"]
    assert tokenize("a 6 x") == []
    assert tokenize("8.1 - The `npm link` command") == ["npm", "link", "command"]


def test_lexical_fields_and_weighted_doc():
    c = TranscriptChunk(chunk_id="x", course_id="c", course_title="C", lecture_id="l", lecture_title="6.5 - IIFE",
                        text="raw iffy", start_time=0, end_time=1, text_clean="clean IIFE body", summary="wraps code",
                        keywords=["module pattern"], questions=["what is scope?"])
    kw, sq, title, text = lexical_fields(c)
    assert kw == ["module", "pattern"] and sq == ["wrap", "code", "scope"]
    assert title == ["iife"] and text == ["clean", "iife", "body"]
    doc = lexical_doc(c)
    assert doc.count("module") == 3 and doc.count("wrap") == 2 and doc.count("iife") == 1 + 1 and doc.count("body") == 1


def test_code_keywords_are_not_stopwords():
    assert tokenize("what is this keyword") == ["this", "keyword"]
    assert tokenize("let vs const") == ["let", "const"]
    assert tokenize("render versus commit") == ["render", "commit"]
    assert tokenize("if else") == ["if", "else"]


def test_stem_es_plurals_short_plurals_and_exceptions():
    assert tokenize("indexes boxes matches") == ["index", "box", "match"]
    assert tokenize("refs keys maps args") == ["ref", "key", "map", "arg"]
    assert tokenize("series canvas alias status bus class") == ["series", "canvas", "alias", "status", "bus", "class"]
