"""Claude API batch translator — fast, cheap, high-quality EN→KR.

Model: claude-haiku-4-5-20251001 (Anthropic's fastest/cheapest tier)
Strategy: batch 50 items per API call with JSON output format
Cache: persistent JSON committed to repo (data/translate_cache.json)

Cost estimate per run (after cache warm-up):
  ~20 new items × 1 call (= 1 batch of ≤50) × ~2,500 tokens
  = ~$0.01/run using Haiku tier pricing ($0.80/M in, $4/M out)

Usage:
  ANTHROPIC_API_KEY=sk-ant-... python translate_claude.py
Inputs: ../data/news_feed.json  (translates EN → adds title_kr/summary_kr)
Cache:  ../data/translate_cache.json  (persistent, committed to repo)
"""
import os
import re
import json
import time
import requests
from datetime import datetime, timezone

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_TRANSLATE_MODEL", "claude-haiku-4-5-20251001")

BATCH_SIZE = 40           # items per API call (conservative to stay under token limits)
MAX_NEW_PER_RUN = 120     # cap to keep costs bounded per run
MAX_SUMMARY_CHARS = 260   # trim long summaries before sending

PROMPT_TEMPLATE = """You are translating US financial news headlines and summaries from English to Korean for a retail trader.

Rules:
- Use friendly Korean 반말체 ending in "~에요/~어요" (not formal 합니다체).
- Keep tickers in English (NVDA, TSLA, S&P 500, Nasdaq, FOMC, CPI).
- Keep numbers, percentages, currency symbols as-is ($, %, ¥, ₩).
- Keep proper nouns in English unless they have a standard Korean rendering (e.g., 엔비디아 is acceptable for Nvidia in summaries, but keep NVDA for ticker references).
- Do NOT translate company legal forms like Inc., Corp., Ltd., PLC — keep as-is.
- Translation should sound natural, like a Korean trader talking to a friend.
- Keep it concise — no adding explanations or disclaimers.
- If the English is already in Korean or unintelligible, return the original.

For each item below, output a JSON array with this exact schema:
[{"id": "item-id", "title_kr": "한국어 제목", "summary_kr": "한국어 요약 또는 null"}]

Output ONLY the JSON array, nothing else. No markdown, no explanations.

Items to translate:
{items_json}"""


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
        # Trim to most recently added (cache is insertion-ordered)
        items = list(cache.items())[-5000:]
        cache = dict(items)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def translate_batch(items):
    """Call Claude API with a batch of items.

    items: [{ "id": str, "title": str, "summary": str|None }]
    Returns: dict mapping id → {"title_kr": str, "summary_kr": str|None}
    """
    if not items: return {}
    if not API_KEY:
        print("[translate-claude] no ANTHROPIC_API_KEY — skipping")
        return {}

    payload_items = []
    for it in items:
        payload_items.append({
            "id": it["id"],
            "title": it["title"],
            "summary": (it.get("summary") or "")[:MAX_SUMMARY_CHARS] or None,
        })
    prompt = PROMPT_TEMPLATE.format(items_json=json.dumps(payload_items, ensure_ascii=False))

    body = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        r = requests.post(API_URL, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        content = data.get("content", [])
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")
        # Extract JSON array (sometimes model wraps with markdown despite the rule)
        m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if not m:
            print(f"[translate-claude] no JSON found in response: {text[:200]}")
            return {}
        translations = json.loads(m.group(0))
        result = {}
        for tr in translations:
            _id = tr.get("id")
            if not _id: continue
            result[_id] = {
                "title_kr": tr.get("title_kr"),
                "summary_kr": tr.get("summary_kr"),
            }
        usage = data.get("usage", {})
        print(f"[translate-claude] batch ok — {len(result)} items, "
              f"in={usage.get('input_tokens')} out={usage.get('output_tokens')}")
        return result
    except requests.HTTPError as e:
        print(f"[translate-claude] HTTP error: {e.response.status_code} {e.response.text[:300]}")
        return {}
    except Exception as e:
        print(f"[translate-claude] batch failed: {e}")
        return {}


def is_korean(s):
    if not s: return False
    # Heuristic: at least some hangul characters
    return bool(re.search(r"[\uac00-\ud7af]", s))


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    feed_path = os.path.join(base, "..", "data", "news_feed.json")
    cache_path = os.path.join(base, "..", "data", "translate_cache.json")

    if not os.path.exists(feed_path):
        print(f"[translate-claude] no feed at {feed_path}, skipping")
        return

    with open(feed_path, "r", encoding="utf-8") as f:
        feed = json.load(f)
    items = feed.get("items", [])

    cache = load_cache(cache_path)
    print(f"[translate-claude] feed has {len(items)} items · cache has {len(cache)}")

    # Apply cache first
    hits = 0
    for it in items:
        cache_key = cache_key_for(it)
        cached = cache.get(cache_key)
        if cached:
            if cached.get("title_kr"): it["title_kr"] = cached["title_kr"]
            if cached.get("summary_kr"): it["summary_kr"] = cached["summary_kr"]
            hits += 1

    # Find items still needing translation (no title_kr, not already Korean)
    needs = []
    for it in items:
        if it.get("title_kr") and is_korean(it["title_kr"]):
            continue
        if is_korean(it.get("title") or ""):
            # Already Korean — mark as such
            it["title_kr"] = it.get("title_kr") or it.get("title")
            it["summary_kr"] = it.get("summary_kr") or it.get("summary")
            continue
        needs.append({
            "id": it.get("id"),
            "title": it.get("title") or "",
            "summary": it.get("summary") or "",
        })

    # Cap per run (cost control)
    if len(needs) > MAX_NEW_PER_RUN:
        print(f"[translate-claude] capping {len(needs)} → {MAX_NEW_PER_RUN}")
        needs = needs[:MAX_NEW_PER_RUN]

    if not needs:
        print(f"[translate-claude] nothing new to translate (cache hit={hits})")
        save_cache(cache_path, cache)
        feed["translated_at"] = datetime.now(timezone.utc).isoformat()
        with open(feed_path, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False, indent=2)
        return

    print(f"[translate-claude] translating {len(needs)} new items (cache hit={hits})")

    # Batch
    translated = 0
    for i in range(0, len(needs), BATCH_SIZE):
        batch = needs[i:i + BATCH_SIZE]
        result = translate_batch(batch)
        # Apply results + update cache
        for item in items:
            _id = item.get("id")
            if _id in result:
                tr = result[_id]
                if tr.get("title_kr"):
                    item["title_kr"] = tr["title_kr"]
                if tr.get("summary_kr"):
                    item["summary_kr"] = tr["summary_kr"]
                ck = cache_key_for(item)
                cache[ck] = {
                    "title_kr": tr.get("title_kr"),
                    "summary_kr": tr.get("summary_kr"),
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                }
                translated += 1
        # Brief pause between batches
        if i + BATCH_SIZE < len(needs):
            time.sleep(0.5)

    save_cache(cache_path, cache)

    feed["translated_at"] = datetime.now(timezone.utc).isoformat()
    feed["translation_engine"] = f"claude:{MODEL}"
    with open(feed_path, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    print(f"[translate-claude] done — translated {translated} new items")


def cache_key_for(item):
    """Stable key per item (title hash). Reusing same title across runs = cache hit."""
    import hashlib
    title = (item.get("title") or "").strip()[:200]
    return "t:" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    main()
