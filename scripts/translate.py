"""Translate English news titles (and optionally summaries) to Korean.

Supports two providers:
  1. DeepL — best quality. Free tier 500k chars/month. Set DEEPL_API_KEY.
  2. Google Translate (unofficial free endpoint) — fallback. No key needed, rate limited.

Usage:
  DEEPL_API_KEY=xxx python translate.py
  # or with no key (uses Google Translate fallback)
Inputs: ../data/news_feed.json
Outputs: ../data/news_feed.json (in-place, adds title_kr / summary_kr fields)
"""
import os
import json
import time
import requests
from urllib.parse import quote
from datetime import datetime, timezone

DEEPL_KEY = os.environ.get("DEEPL_API_KEY", "")
CACHE_PATH = "/tmp/translate_cache.json"

def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def translate_deepl(text):
    if not DEEPL_KEY or not text: return None
    # Free tier uses api-free.deepl.com, paid uses api.deepl.com
    endpoint = "https://api-free.deepl.com/v2/translate" if ":fx" in DEEPL_KEY else "https://api.deepl.com/v2/translate"
    try:
        r = requests.post(endpoint, data={
            "auth_key": DEEPL_KEY,
            "text": text,
            "target_lang": "KO",
            "source_lang": "EN",
        }, timeout=15)
        r.raise_for_status()
        translations = r.json().get("translations", [])
        if translations:
            return translations[0].get("text")
    except Exception as e:
        print(f"[translate] DeepL failed: {e}")
    return None

def translate_google_free(text):
    """Unofficial free Google Translate endpoint. Best-effort, may throttle."""
    if not text: return None
    try:
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=en&tl=ko&dt=t&q=" + quote(text))
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        # data[0] is array of segment pairs: [[ko, en, ...], ...]
        segments = data[0] or []
        return "".join(seg[0] for seg in segments if seg and seg[0]).strip()
    except Exception as e:
        print(f"[translate] Google fallback failed: {e}")
        return None

def translate(text, cache):
    if not text: return None
    text = text.strip()
    if not text: return None
    if text in cache:
        return cache[text]
    result = translate_deepl(text) or translate_google_free(text)
    if result:
        cache[text] = result
        time.sleep(0.25)  # be polite on free endpoints
    return result

def main():
    feed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "news_feed.json")
    if not os.path.exists(feed_path):
        print(f"[translate] no feed at {feed_path}, skipping")
        return
    with open(feed_path, "r", encoding="utf-8") as f:
        feed = json.load(f)
    items = feed.get("items", [])
    cache = load_cache()

    translated = 0
    for it in items:
        if it.get("title_kr") and it.get("summary_kr"):
            continue
        title = it.get("title")
        summary = it.get("summary")
        title_kr = translate(title, cache)
        if title_kr:
            it["title_kr"] = title_kr
            translated += 1
        if summary and len(summary) > 20:
            summary_kr = translate(summary[:280], cache)
            if summary_kr:
                it["summary_kr"] = summary_kr

    save_cache(cache)
    feed["translated_at"] = datetime.now(timezone.utc).isoformat()
    with open(feed_path, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    print(f"[translate] translated {translated} items")

if __name__ == "__main__":
    main()
