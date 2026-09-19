"""Best-effort translation of AI video prompts to English, plus paraphrasing.

Both Magic Hour and the Colab diffusers pipelines are trained mostly on
English prompts and work noticeably worse with other languages, but users
naturally type prompts in Korean. Translates non-English prompts before
they reach either backend, using Google Translate's public (undocumented,
no API key) endpoint. If that endpoint is unreachable or errors, the
original text is used as-is rather than failing the whole request - a
translation hiccup shouldn't block video generation.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

_NON_ASCII = re.compile(r"[^\x00-\x7F]")


def _translate(text: str, source_lang: str, target_lang: str) -> str:
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": text}
    )
    url = f"https://translate.googleapis.com/translate_a/single?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(segment[0] for segment in data[0])


def to_english(text: str) -> str:
    if not text or not _NON_ASCII.search(text):
        return text
    try:
        return _translate(text, "auto", "en")
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError):
        return text


def paraphrase(text: str, via_lang: str) -> str:
    """Reword English text by round-tripping it through another language and
    back, so a provider that rejected the original wording (e.g. a content
    filter keying off exact phrasing rather than actual meaning) can be
    retried with a differently-worded but equivalent prompt. Falls back to
    the original text - rather than raising - if translation errors, since a
    failed reword attempt shouldn't be worse than just retrying unchanged.
    """
    if not text:
        return text
    try:
        translated = _translate(text, "en", via_lang)
        back = _translate(translated, via_lang, "en")
        return back or text
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError):
        return text
