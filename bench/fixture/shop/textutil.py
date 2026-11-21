SMALL_WORDS = {"a", "an", "and", "of", "the", "to"}


def slugify(text):
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return "-".join(cleaned.split())


def truncate(text, limit, suffix="..."):
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)] + suffix


def title_case(text):
    words = text.lower().split()
    result = []
    for i, word in enumerate(words):
        if i > 0 and word in SMALL_WORDS:
            result.append(word)
        else:
            result.append(word.capitalize())
    return " ".join(result)


def word_count(text):
    return len(text.split())


def initials(name):
    parts = [p for p in name.split() if p]
    if len(parts) == 0:
        return ""
    return "".join(p[0].upper() for p in parts[:3])
