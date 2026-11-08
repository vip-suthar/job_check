from detector.rules import highlight


def test_highlight_escapes_and_merges_overlapping_spans():
    text = "pay <b>fee</b> now"
    # spans (4, 10) and (8, 14) overlap and should become one <mark>
    assert str(highlight(text, [(8, 14), (4, 10)])) == "pay <mark>&lt;b&gt;fee&lt;/b&gt;</mark> now"


def test_highlight_without_spans_only_escapes():
    assert str(highlight("a < b", [])) == "a &lt; b"
