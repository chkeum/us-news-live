"""Free parallel translator — Google Translate with persistent cache and top-N limit.

Strategy:
  - Persistent cache at data/translate_cache.json (committed to repo)
  - Translate only the TOP 50 items by relevance rank (not all 200)
  - 30 concurrent workers via ThreadPoolExecutor (10-20x faster than sequential)
  - Falls back to DeepL if DEEPL_API_KEY is set (higher quality)
  - Total cost: $0, typical time: 10-20s first run, <3s after cache warms up

Usage:
  DEEPL_API_KEY=xxx python translate.py    # optional, better quality
  python translate.py                       # free Google fallback
Inputs:  ../data/news_feed.json
Cache:   ../data/translate_cache.json  (persistent, committed)
"""
import os
import re
import json
import time
import hashlib
import requests
from urllib.parse import quote
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

DEEPL_KEY = os.environ.get("DEEPL_API_KEY", "")
MAX_WORKERS = 30
TOP_N = 50            # only translate top N items by rank (they're already ranked by score)
REQUEST_TIMEOUT = 8

# ---------- Cache ----------
def cache_key(text):
    t = (text or "").strip()[:300]
    return "t:" + hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]

def load_cache(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(path, cache):
    # Keep cache bounded
    if len(cache) > 5000:
        items = list(cache.items())[-5000:]
        cache = dict(items)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ---------- Engines ----------
def translate_deepl(text):
    if not DEEPL_KEY or not text: return None
    endpoint = "https://api-free.deepl.com/v2/translate" if ":fx" in DEEPL_KEY else "https://api.deepl.com/v2/translate"
    try:
        r = requests.post(endpoint, data={
            "auth_key": DEEPL_KEY,
            "text": text,
            "target_lang": "KO",
            "source_lang": "EN",
        }, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        trs = r.json().get("translations", [])
        if trs:
            return trs[0].get("text")
    except Exception as e:
        print(f"[translate] DeepL failed: {e}")
    return None

def translate_google_free(text):
    """Unofficial Google Translate endpoint. Free, no auth."""
    if not text: return None
    try:
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=en&tl=ko&dt=t&q=" + quote(text))
        r = requests.get(url, timeout=REQUEST_TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        segments = data[0] or []
        return "".join(seg[0] for seg in segments if seg and seg[0]).strip() or None
    except Exception as e:
        # swallow — will retry or fallback
        return None

def translate_one(text):
    """Try DeepL first (if key), then Google."""
    if not text or not text.strip():
        return None
    return translate_deepl(text) or translate_google_free(text)

# ---------- Utilities ----------
def is_korean(s):
    if not s: return False
    return bool(re.search(r"[\uac00-\ud7af]", s))

# ---------- Main ----------
def main():
    base = os.path.dirname(os.path.abspath(__file__))
    feed_path = os.path.join(base, "..", "data", "news_feed.json")
    cache_path = os.path.join(base, "..", "data", "translate_cache.json")

    if not os.path.exists(feed_path):
        print(f"[translate] no feed at {feed_path}, skipping")
        return

    with open(feed_path, "r", encoding="utf-8") as f:
        feed = json.load(f)
    items = feed.get("items", [])

    cache = load_cache(cache_path)
    print(f"[translate] feed has {len(items)} items · cache has {len(cache)}")

    # Step 1: Apply cache to all items (even those below TOP_N — in case they were cached earlier)
    cache_hits = 0
    for it in items:
        tkey = cache_key(it.get("title"))
        cached_title = cache.get(tkey)
        if cached_title and isinstance(cached_title, dict):
            if cached_title.get("title_kr"):
                it["title_kr"] = cached_title["title_kr"]
                cache_hits += 1
            if cached_title.get("summary_kr"):
                it["summary_kr"] = cached_title["summary_kr"]
        # Items already in Korean — mark as such
        if not it.get("title_kr") and is_korean(it.get("title") or ""):
            it["title_kr"] = it["title"]
            it["summary_kr"] = it.get("summary")

    # Step 2: Find TOP_N items still needing translation
    top_items = items[:TOP_N]
    needs = []
    for it in top_items:
        if it.get("title_kr") and is_korean(it["title_kr"]):
            continue
        if is_korean(it.get("title") or ""):
            continue
        needs.append(it)

    if not needs:
        print(f"[translate] nothing new to translate (cache hits={cache_hits})")
        save_cache(cache_path, cache)
        write_feed(feed, feed_path)
        return

    print(f"[translate] parallel translating {len(needs)} new items (cache hits={cache_hits}, workers={MAX_WORKERS})")
    start = time.time()

    # Step 3: Parallel translate (title + summary per item)
    def translate_item(it):
        title_out = translate_one(it.get("title"))
        summary = (it.get("summary") or "").strip()[:260]
        summary_out = translate_one(summary) if len(summary) > 20 else None
        return it, title_out, summary_out

    completed = 0
    failures = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(translate_item, it) for it in needs]
        for fut in as_completed(futures):
            try:
                it, t_kr, s_kr = fut.result()
                if t_kr:
                    it["title_kr"] = t_kr
                    completed += 1
                    # Update cache
                    tkey = cache_key(it.get("title"))
                    cache[tkey] = {
                        "title_kr": t_kr,
                        "summary_kr": s_kr,
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    }
                if s_kr:
                    it["summary_kr"] = s_kr
                if not t_kr:
                    failures += 1
            except Exception as e:
                failures += 1

    elapsed = time.time() - start
    print(f"[translate] done — translated {completed} items, {failures} failures, {elapsed:.1f}s elapsed")

    save_cache(cache_path, cache)
    write_feed(feed, feed_path)

def write_feed(feed, feed_path):
    feed["translated_at"] = datetime.now(timezone.utc).isoformat()
    feed["translation_engine"] = "deepl" if DEEPL_KEY else "google-parallel"
    with open(feed_path, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
