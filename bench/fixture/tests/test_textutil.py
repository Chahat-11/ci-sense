from shop import textutil


def test_slugify():
    assert textutil.slugify("Hello, World!") == "hello-world"


def test_truncate():
    assert textutil.truncate("abcdefghij", 6) == "abc..."
    assert textutil.truncate("short", 10) == "short"


def test_title_case():
    assert textutil.title_case("the lord of the rings") == "The Lord of the Rings"


def test_word_count():
    assert textutil.word_count("one two  three") == 3


def test_initials():
    assert textutil.initials("ada king lovelace") == "AKL"
