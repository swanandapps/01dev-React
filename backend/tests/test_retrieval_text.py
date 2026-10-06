from app.models import TranscriptChunk
from app.retrieval.text import lexical_doc, lexical_fields, tokenize


def test_tokenize_keeps_acronyms_and_code_tokens():
    assert tokenize("What is an IIFE?") == ["iife"]
    assert tokenize("publish with np") == ["publish", "np"]
    assert tokenize("useMemo vs React.memo") == ["usememo", "use", "memo", "vs", "react", "memo"]
    assert tokenize("innerHTML") == ["innerhtml", "inner", "html"]
    assert tokenize("ES modules and npm packages") == ["es", "module", "npm", "package"]
    assert tokenize("dependencies") == ["dependency"]


def test_tokenize_does_not_split_brand_names_or_mangle_short_words():
    assert tokenize("JavaScript and TypeScript") == ["javascript", "typescript"]
    assert tokenize("class status analysis uses") == ["class", "status", "analysis", "uses"]
    assert tokenize("a 6 x") == []
    assert tokenize("8.1 - The `npm link` command") == ["npm", "link", "command"]


def test_lexical_fields_and_weighted_doc():
    c = TranscriptChunk(chunk_id="x", course_id="c", course_title="C", lecture_id="l", lecture_title="6.5 - IIFE",
                        text="raw iffy", start_time=0, end_time=1, text_clean="clean IIFE body", summary="wraps code",
                        keywords=["module pattern"], questions=["what is scope?"])
    a, b, cc = lexical_fields(c)
    assert a == ["iife", "module", "pattern"] and b == ["wrap", "code", "scope"] and cc == ["clean", "iife", "body"]
    doc = lexical_doc(c)
    assert doc.count("iife") == 3 + 1 and doc.count("wrap") == 2 and doc.count("body") == 1
