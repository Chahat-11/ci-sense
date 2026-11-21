def test_slugify_collapses_separators():
    assert textutil.slugify("  Multi   Word--Title ") == "multi-word-title"


def test_truncate_exact_limit():
    assert textutil.truncate("abcdef", 6) == "abcdef"
    assert textutil.truncate("abcdefg", 6, suffix="~") == "abcde~"


def test_title_case_first_small_word():
    assert textutil.title_case("a tale of two cities") == "A Tale of Two Cities"


def test_word_count_empty():
    assert textutil.word_count("") == 0


def test_initials_limits_and_empty():
    assert textutil.initials("") == ""
    assert textutil.initials("a b c d") == "ABC"
