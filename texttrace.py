#!/usr/bin/env python3
"""
TextTrace — Cross-Platform Text Attribution OSINT Tool
======================================================
Grabs text from a source (URL or raw text), then searches the internet
for matching/similar content across platforms using three-tier matching:

  Tier 1 — Exact hash match (SHA-256 of normalized text)
  Tier 2 — Fuzzy string match (Levenshtein, partial ratio, token sort)
  Tier 3 — Stylometric match (N-gram cosine similarity for same author)

Search engines used (no API keys needed):
  - DuckDuckGo HTML
  - Bing
  - Google (via crawl4ai if available)

Usage:
  python texttrace.py --text "Hello world this is my post"
  python texttrace.py --url https://facebook.com/somepost
  python texttrace.py --text "Hello world" --threshold 70 --tier fuzzy
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone

# ─── Dependencies ──────────────────────────────────────────────────────────────

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip install beautifulsoup4")
    sys.exit(1)

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    print("WARNING: rapidfuzz not installed — fuzzy matching disabled. Run: pip install rapidfuzz")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sk_cosine
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


# ─── Config ────────────────────────────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Platforms we recognize in URLs
PLATFORM_PATTERNS = {
    "twitter/x": [r"(?:twitter\.com|x\.com)"],
    "facebook": [r"facebook\.com", r"fb\.com", r"fb\.me"],
    "instagram": [r"instagram\.com", r"instagr\.am"],
    "reddit": [r"reddit\.com"],
    "linkedin": [r"linkedin\.com"],
    "tiktok": [r"tiktok\.com"],
    "youtube": [r"youtube\.com", r"youtu\.be"],
    "telegram": [r"t\.me", r"telegram\.me"],
    "mastodon": [r"mastodon\.\w+", r"masto\.dn"],
    "threads": [r"threads\.net"],
    "truth_social": [r"truthsocial\.com"],
    "parler": [r"parler\.com"],
    "gab": [r"gab\.com"],
    "medium": [r"medium\.com"],
    "substack": [r"substack\.com"],
    "quora": [r"quora\.com"],
    "pinterest": [r"pinterest\.\w+"],
    "tumblr": [r"tumblr\.com"],
    "whatsapp": [r"whatsapp\.com", r"wa\.me"],
    "discord": [r"discord\.(?:com|gg)"],
    "github": [r"github\.com"],
    "pastebin": [r"pastebin\.com"],
    "4chan": [r"4chan\.org", r"4channel\.org"],
    "8kun": [r"8kun\.top"],
    "steam": [r"steamcommunity\.com"],
    "vkontakte": [r"vk\.com"],
    "weibo": [r"weibo\.\w+"],
    "snapchat": [r"snapchat\.com"],
}


# ─── Text Normalization ────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip URLs/special chars."""
    text = text.lower()
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove @mentions and #hashtags markers (keep the word)
    text = re.sub(r'[@#]', '', text)
    # Remove emojis and non-ASCII
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def text_fingerprint(text: str) -> str:
    """SHA-256 hash of normalized text — exact match signature."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


# ─── Tier 1: Exact Match ──────────────────────────────────────────────────────

def exact_match_score(source: str, target: str) -> float:
    """100 if fingerprints match, 0 otherwise."""
    return 100.0 if text_fingerprint(source) == text_fingerprint(target) else 0.0


# ─── Tier 2: Fuzzy Match ──────────────────────────────────────────────────────

def fuzzy_match_score(source: str, target: str) -> dict:
    """Multiple fuzzy similarity scores using rapidfuzz."""
    if not HAS_RAPIDFUZZ:
        return {"ratio": 0, "partial_ratio": 0, "token_sort_ratio": 0, "token_set_ratio": 0}

    src_norm = normalize_text(source)
    tgt_norm = normalize_text(target)

    return {
        "ratio": fuzz.ratio(src_norm, tgt_norm),
        "partial_ratio": fuzz.partial_ratio(src_norm, tgt_norm),
        "token_sort_ratio": fuzz.token_sort_ratio(src_norm, tgt_norm),
        "token_set_ratio": fuzz.token_set_ratio(src_norm, tgt_norm),
    }


# ─── Tier 3: Stylometric Match ────────────────────────────────────────────────

def ngram_cosine_similarity(text_a: str, text_b: str, n: int = 3) -> float:
    """N-gram cosine similarity — captures writing style even with different wording."""
    def get_ngrams(text: str, n: int) -> Counter:
        words = normalize_text(text).split()
        return Counter(tuple(words[i:i+n]) for i in range(len(words) - n + 1))

    ngrams_a = get_ngrams(text_a, n)
    ngrams_b = get_ngrams(text_b, n)

    if not ngrams_a or not ngrams_b:
        return 0.0

    all_keys = set(ngrams_a.keys()) | set(ngrams_b.keys())
    vec_a = [ngrams_a.get(k, 0) for k in all_keys]
    vec_b = [ngrams_b.get(k, 0) for k in all_keys]

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return (dot / (mag_a * mag_b)) * 100  # Scale to 0-100


def stylometric_score(source: str, target: str) -> dict:
    """Multi-feature stylometric comparison."""
    scores = {
        "bigram_cosine": ngram_cosine_similarity(source, target, n=2),
        "trigram_cosine": ngram_cosine_similarity(source, target, n=3),
    }

    if HAS_SKLEARN:
        try:
            vectorizer = TfidfVectorizer(ngram_range=(1, 3))
            src_norm = normalize_text(source)
            tgt_norm = normalize_text(target)
            tfidf_matrix = vectorizer.fit_transform([src_norm, tgt_norm])
            sim = sk_cosine(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0] * 100
            scores["tfidf_cosine"] = round(sim, 2)
        except Exception:
            scores["tfidf_cosine"] = 0.0

    # Average of available scores
    vals = [v for v in scores.values() if v > 0]
    scores["overall"] = round(sum(vals) / len(vals), 2) if vals else 0.0

    return scores


# ─── Search Engine Scraping ────────────────────────────────────────────────────

def search_duckduckgo(query: str, max_results: int = 30) -> list:
    """Search DuckDuckGo HTML and parse results."""
    results = []
    
    # Rotate user agents to avoid rate limiting
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    ]
    
    import random
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
            resp = client.get("https://html.duckduckgo.com/html/", params={"q": query})
            
            # DDG returns 202 when rate-limited
            if resp.status_code == 202:
                print(f"  [!] DDG rate-limited (202), cooling down...")
                time.sleep(8)
                # Retry with different UA
                headers["User-Agent"] = random.choice(user_agents)
                resp = client.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=headers)
            
            if resp.status_code != 200:
                return results

            # Check if we got real results
            if len(resp.text) < 2000:
                return results

            soup = BeautifulSoup(resp.text, 'html.parser')
            for div in soup.find_all('div', class_='result'):
                title_elem = div.find('a', class_='result__a')
                snippet_elem = div.find('a', class_='result__snippet')

                if not title_elem:
                    continue

                raw_url = title_elem.get('href', '')
                title = title_elem.get_text(strip=True)
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

                # Extract real URL from DDG redirect
                real_url_match = re.search(r'uddg=([^&]+)', raw_url)
                url = urllib.parse.unquote(real_url_match.group(1)) if real_url_match else raw_url

                if url and not url.startswith('/'):
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "engine": "duckduckgo",
                    })
    except Exception as e:
        print(f"  [!] DuckDuckGo search error: {e}")

    return results[:max_results]


def search_bing(query: str, max_results: int = 20) -> list:
    """Search Bing and parse results."""
    results = []
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            resp = client.get("https://www.bing.com/search", params={"q": query})
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, 'html.parser')
            for li in soup.find_all('li', class_='b_algo'):
                title_elem = li.find('h2')
                link_elem = li.find('a')
                snippet_elem = li.find('p') or li.find('div', class_='b_caption')

                if not link_elem:
                    continue

                title = title_elem.get_text(strip=True) if title_elem else ''
                url = link_elem.get('href', '')
                snippet = ''
                if snippet_elem:
                    snippet = snippet_elem.get_text(strip=True)

                # Resolve Bing redirect URLs
                if url and 'bing.com/ck/' in url:
                    m = re.search(r'[?&]u=([^&]+)', url)
                    if m:
                        url = urllib.parse.unquote(m.group(1))
                    else:
                        m2 = re.search(r'[?&]u=a1([^&]+)', url)
                        if m2:
                            import base64
                            try:
                                url = base64.b64decode(m2.group(1) + '==').decode('utf-8', errors='ignore')
                            except Exception:
                                pass

                if url and url.startswith('http') and 'bing.com/ck/' not in url:
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "engine": "bing",
                    })
    except Exception as e:
        print(f"  [!] Bing search error: {e}")

    return results[:max_results]


def search_yandex(query: str, max_results: int = 15) -> list:
    """Search Yandex and parse results."""
    results = []
    try:
        yandex_headers = {**HEADERS, "Accept-Language": "en,en-US;q=0.9"}
        with httpx.Client(timeout=20, follow_redirects=True, headers=yandex_headers) as client:
            resp = client.get("https://yandex.com/search/", params={"text": query, "lr": 87})
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, 'html.parser')
            for serp_item in soup.find_all('li', class_='serp-item'):
                link_elem = serp_item.find('a', class_='Link')
                title_elem = serp_item.find('span', class_='Typo')
                snippet_elem = serp_item.find('span', class_='ExtendedText')

                if not link_elem:
                    continue

                url = link_elem.get('href', '')
                title = title_elem.get_text(strip=True) if title_elem else ''
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

                if url and url.startswith('http'):
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "engine": "yandex",
                    })
    except Exception as e:
        print(f"  [!] Yandex search error: {e}")

    return results[:max_results]


# ─── Content Extraction ────────────────────────────────────────────────────────

def extract_text_from_url(url: str) -> str:
    """Scrape and extract visible text from a URL."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"  [!] Failed to fetch {url}: HTTP {resp.status_code}")
                return ""

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Remove script, style, nav, footer, header elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                tag.decompose()

            # Get main content or fall back to body
            main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|post|entry|message', re.I)) or soup.body
            if main:
                return main.get_text(separator=' ', strip=True)
            return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        print(f"  [!] Error extracting from {url}: {e}")
        return ""


# ─── Platform Detection ────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    """Identify which platform a URL belongs to."""
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, url, re.I):
                return platform
    return "unknown"


# ─── Search Query Generation ──────────────────────────────────────────────────

def generate_search_queries(text: str) -> list:
    """Generate multiple search queries from source text for maximum coverage.
    
    Strategy: Prioritize proper nouns and distinctive terms, then add
    short content-rich phrases. Avoid long quoted phrases full of stop words
    that search engines ignore.
    """
    queries = []
    normalized = normalize_text(text)
    words = normalized.split()

    stop_words = {
        'the','a','an','is','it','in','on','at','to','for','of','and','or','but',
        'this','that','with','was','are','be','have','has','had','not','they','we',
        'you','i','he','she','my','me','your','so','if','do','no','just','like',
        'up','out','about','into','than','then','can','will','would','could','should',
        'what','when','where','who','how','all','each','every','both','few','more',
        'most','other','some','such','only','own','same','also','very','even','still',
        'already','always','never','often','sometimes','usually','really','much',
        'many','well','back','over','after','before','between','through','during',
        'from','under','again','there','here','why','been','being','did','does',
        'done','get','got','make','made','take','took','come','came','go','went',
        'see','saw','know','knew','think','thought','say','said','tell','told',
        'find','found','give','gave','use','used','new','way','may','these','any',
        'which','their','them','they','its','our','us','am','because','as','until',
        'while','those','too','now','down','off','once',
    }

    # ── Strategy 1: Proper nouns / distinctive capitalized terms ──
    # These are the BEST search signals — "OSINT Varta Map", "CyberSudo", etc.
    original_words = text.split()
    proper_nouns = []
    for w in original_words:
        clean = re.sub(r'[^a-zA-Z0-9\-]', '', w)
        if not clean or len(clean) <= 2:
            continue
        # Capitalized word (not at sentence start) or all-caps or hyphenated
        is_capitalized = clean[0].isupper()
        is_all_caps = clean.isupper() and len(clean) > 2
        is_hyphenated = '-' in clean and len(clean) > 4
        
        if is_capitalized or is_all_caps or is_hyphenated:
            lower = clean.lower()
            if lower not in stop_words and lower not in {'people','often','one','two','also','around'}:
                proper_nouns.append(clean)

    # Deduplicate preserving order
    proper_nouns = list(dict.fromkeys(proper_nouns))

    if proper_nouns:
        # Pair proper nouns — prioritize rare/unusual pairs over generic ones
        # Score each pair by rarity (words that appear less commonly together)
        all_pairs = []
        for i in range(min(len(proper_nouns), 10)):
            for j in range(i + 1, min(len(proper_nouns), 10)):
                pair = f'{proper_nouns[i]} {proper_nouns[j]}'
                # Heuristic: longer words + hyphenated words = more specific
                specificity = sum(len(w) for w in [proper_nouns[i], proper_nouns[j]])
                if '-' in proper_nouns[i] or '-' in proper_nouns[j]:
                    specificity += 10  # Hyphenated terms are usually very specific
                all_pairs.append((pair, specificity))
        
        # Sort by specificity descending (most distinctive first)
        all_pairs.sort(key=lambda x: x[1], reverse=True)
        for pair, _ in all_pairs:
            queries.append(pair)
        
        # Groups of 3 proper nouns (most specific first)
        if len(proper_nouns) >= 3:
            # Sort proper nouns by length (longer = more specific) for grouping
            sorted_nouns = sorted(proper_nouns, key=len, reverse=True)
            for i in range(min(len(sorted_nouns) - 2, 5)):
                queries.append(f'{sorted_nouns[i]} {sorted_nouns[i+1]} {sorted_nouns[i+2]}')

    # ── Strategy 2: Content word groups (3-5 distinctive non-stop words) ──
    content_words = [w for w in words if w not in stop_words and len(w) > 2]
    if len(content_words) >= 3:
        group_size = min(4, len(content_words))
        for i in range(0, min(len(content_words), 12), 3):
            group = content_words[i:i + group_size]
            if len(group) >= 3:
                queries.append(' '.join(group))

    # ── Strategy 3: Short distinctive quoted phrases (3-4 content words) ──
    # Build phrases from consecutive content words
    if len(words) >= 3:
        phrase = []
        for w in words:
            if w not in stop_words and len(w) > 2:
                phrase.append(w)
                if len(phrase) >= 3:
                    queries.append(f'"{" ".join(phrase)}"')
                    phrase = []
            else:
                if len(phrase) >= 3:
                    queries.append(f'"{" ".join(phrase)}"')
                phrase = []

    # Deduplicate, filter too-short, preserve order
    seen = set()
    unique = []
    for q in queries:
        q_clean = q.strip()
        if q_clean and q_clean not in seen and len(q_clean) >= 8:
            seen.add(q_clean)
            unique.append(q_clean)

    return unique[:15]


# ─── Main Orchestration ────────────────────────────────────────────────────────

def run_texttrace(
    source_text: str,
    source_url: str = None,
    threshold: float = 60,
    tier: str = "all",
    engines: list = None,
    max_results: int = 15,
    extract_content: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Main TextTrace pipeline.

    Args:
        source_text: The text to search for (or used if --url not given)
        source_url: URL to extract source text from (overrides source_text)
        threshold: Minimum match score (0-100) to include in results
        tier: "exact", "fuzzy", "stylometric", or "all"
        engines: Search engines to use
        max_results: Max results per engine
        extract_content: Whether to scrape result pages for full text comparison
        verbose: Print detailed progress

    Returns:
        Dict with matches, stats, and metadata
    """
    start_time = time.time()

    # ── Step 1: Get source text ──
    if source_url:
        print(f"[*] Extracting text from: {source_url}")
        extracted = extract_text_from_url(source_url)
        if extracted:
            source_text = extracted
            print(f"    Extracted {len(source_text)} characters")
        else:
            print("    [!] Failed to extract text, using provided text if any")

    if not source_text:
        return {"error": "No source text provided", "matches": []}

    print(f"\n[*] Source text ({len(source_text)} chars):")
    preview = source_text[:200] + ("..." if len(source_text) > 200 else "")
    print(f"    \"{preview}\"")

    src_fingerprint = text_fingerprint(source_text)
    print(f"    Fingerprint: {src_fingerprint[:16]}...")

    # ── Step 2: Generate search queries ──
    queries = generate_search_queries(source_text)
    print(f"\n[*] Generated {len(queries)} search queries:")
    for i, q in enumerate(queries):
        print(f"    {i+1}. {q[:80]}{'...' if len(q) > 80 else ''}")

    # ── Step 3: Search engines ──
    if engines is None:
        engines = ["duckduckgo", "bing"]

    all_results = []
    seen_urls = set()

    for engine in engines:
        print(f"\n[*] Searching {engine}...")
        for qi, query in enumerate(queries[:8]):  # Up to 8 queries per engine
            if verbose:
                print(f"    Query {qi+1}/{min(len(queries),8)}: {query[:70]}...")
            if engine == "duckduckgo":
                results = search_duckduckgo(query, max_results)
            elif engine == "bing":
                results = search_bing(query, max_results)
            elif engine == "yandex":
                results = search_yandex(query, max_results)
            else:
                continue

            new_count = 0
            for r in results:
                if r['url'] not in seen_urls:
                    seen_urls.add(r['url'])
                    all_results.append(r)
                    new_count += 1

            if verbose and new_count > 0:
                print(f"    → {new_count} new results")

            # Adaptive delay: longer if DDG is rate-limiting
            if engine == "duckduckgo":
                time.sleep(4 if new_count == 0 else 3)
            else:
                time.sleep(3)

    print(f"\n[*] Found {len(all_results)} unique results from search engines")

    # ── Step 4: Extract & match ──
    matches = []
    source_platform = detect_platform(source_url) if source_url else "input"

    for i, result in enumerate(all_results):
        platform = detect_platform(result['url'])

        # Skip results from the same platform as source (we already know about those)
        # unless the user explicitly wants same-platform matches
        # same_platform = (platform == source_platform and platform != "unknown")

        # Start with snippet matching (no page fetch needed)
        snippet_text = result.get('snippet', '')

        match_data = {
            "url": result['url'],
            "title": result['title'],
            "platform": platform,
            "engine": result['engine'],
            "scores": {},
            "max_score": 0,
            "match_tier": None,
        }

        # Tier 1: Exact match on snippet
        if tier in ("all", "exact"):
            exact = exact_match_score(source_text, snippet_text)
            match_data["scores"]["exact"] = exact
            if exact > match_data["max_score"]:
                match_data["max_score"] = exact
                match_data["match_tier"] = "exact"

        # Tier 2: Fuzzy match on snippet
        if tier in ("all", "fuzzy") and HAS_RAPIDFUZZ:
            fuzzy = fuzzy_match_score(source_text, snippet_text)
            match_data["scores"]["fuzzy"] = fuzzy
            best_fuzzy = max(fuzzy.values())
            if best_fuzzy > match_data["max_score"]:
                match_data["max_score"] = best_fuzzy
                match_data["match_tier"] = "fuzzy"

        # If snippet match is low and content extraction is enabled, fetch the page
        if extract_content and match_data["max_score"] < threshold:
            if verbose:
                print(f"    Fetching page {i+1}/{len(all_results)}: {result['url'][:60]}...")
            page_text = extract_text_from_url(result['url'])

            if page_text and len(page_text) > 20:
                # Re-run all tiers on full page content
                if tier in ("all", "exact"):
                    exact = exact_match_score(source_text, page_text)
                    if exact > match_data["scores"].get("exact", 0):
                        match_data["scores"]["exact_full"] = exact
                        if exact > match_data["max_score"]:
                            match_data["max_score"] = exact
                            match_data["match_tier"] = "exact (full page)"

                if tier in ("all", "fuzzy") and HAS_RAPIDFUZZ:
                    fuzzy = fuzzy_match_score(source_text, page_text)
                    best_fuzzy = max(fuzzy.values())
                    if best_fuzzy > match_data["max_score"]:
                        match_data["scores"]["fuzzy_full"] = fuzzy
                        match_data["max_score"] = best_fuzzy
                        match_data["match_tier"] = "fuzzy (full page)"

                if tier in ("all", "stylometric"):
                    stylo = stylometric_score(source_text, page_text)
                    best_stylo = stylo.get("overall", 0)
                    if best_stylo > match_data["max_score"]:
                        match_data["scores"]["stylometric_full"] = stylo
                        match_data["max_score"] = best_stylo
                        match_data["match_tier"] = "stylometric (full page)"

            time.sleep(0.5)  # Rate limit page fetches

        # Tier 3: Stylometric on snippet (if enough text)
        if tier in ("all", "stylometric") and len(snippet_text) > 30:
            stylo = stylometric_score(source_text, snippet_text)
            best_stylo = stylo.get("overall", 0)
            if best_stylo > match_data["max_score"]:
                match_data["scores"]["stylometric"] = stylo
                match_data["max_score"] = best_stylo
                match_data["match_tier"] = "stylometric"

        # Include if above threshold
        if match_data["max_score"] >= threshold:
            matches.append(match_data)

    # Sort by score descending
    matches.sort(key=lambda x: x['max_score'], reverse=True)

    elapsed = time.time() - start_time

    # ── Step 5: Build report ──
    report = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_text_preview": source_text[:300],
            "source_fingerprint": src_fingerprint,
            "source_url": source_url,
            "source_platform": source_platform,
            "threshold": threshold,
            "tier": tier,
            "engines_used": engines,
            "queries_generated": len(queries),
            "total_search_results": len(all_results),
            "elapsed_seconds": round(elapsed, 2),
        },
        "stats": {
            "results_scanned": len(all_results),
            "matches_found": len(matches),
            "platforms_matched": list(set(m['platform'] for m in matches)),
            "match_tiers": Counter(m['match_tier'] for m in matches),
        },
        "matches": matches,
    }

    return report


# ─── Report Formatting ─────────────────────────────────────────────────────────

def print_report(report: dict):
    """Pretty-print the TextTrace report."""
    meta = report["metadata"]
    stats = report["stats"]
    matches = report["matches"]

    print("\n" + "=" * 72)
    print("  🔍 TEXTTRACE — Cross-Platform Text Attribution Report")
    print("=" * 72)

    print(f"\n  Source preview: \"{meta['source_text_preview'][:100]}...\"")
    print(f"  Fingerprint:    {meta['source_fingerprint'][:24]}...")
    print(f"  Source URL:     {meta.get('source_url', 'N/A')}")
    print(f"  Source platform: {meta['source_platform']}")
    print(f"  Threshold:      {meta['threshold']}%")
    print(f"  Matching tier:  {meta['tier']}")
    print(f"  Engines:        {', '.join(meta['engines_used'])}")
    print(f"  Scan time:      {meta['elapsed_seconds']}s")

    print(f"\n  Results scanned: {stats['results_scanned']}")
    print(f"  Matches found:   {stats['matches_found']}")
    print(f"  Platforms:       {', '.join(stats['platforms_matched']) if stats['platforms_matched'] else 'none'}")
    print(f"  Match tiers:     {dict(stats['match_tiers'])}")

    if not matches:
        print("\n  ⚠️  No matches found above threshold.")
        return

    print(f"\n{'─' * 72}")
    print(f"  TOP MATCHES")
    print(f"{'─' * 72}")

    for i, m in enumerate(matches[:20]):
        print(f"\n  ┌─ Match #{i+1} ─────────────────────────────────")
        print(f"  │ Platform:  {m['platform']}")
        print(f"  │ Score:     {m['max_score']:.1f}%")
        print(f"  │ Tier:      {m['match_tier']}")
        print(f"  │ URL:       {m['url'][:100]}")
        print(f"  │ Title:     {m['title'][:80]}")
        print(f"  │ Engine:    {m['engine']}")

        # Show detailed scores
        for score_name, score_val in m['scores'].items():
            if isinstance(score_val, dict):
                print(f"  │ {score_name}:")
                for k, v in score_val.items():
                    print(f"  │   {k}: {v:.1f}" if isinstance(v, float) else f"  │   {k}: {v}")
            else:
                print(f"  │ {score_name}: {score_val:.1f}")

        print(f"  └─────────────────────────────────────────────")

    print(f"\n{'=' * 72}")
    print(f"  Total: {len(matches)} matches above {meta['threshold']}% threshold")
    print(f"{'=' * 72}\n")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TextTrace — Cross-Platform Text Attribution OSINT Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for exact text across the internet
  python texttrace.py --text "I think AI will change everything"

  # Extract text from a URL and search for it
  python texttrace.py --url https://facebook.com/somepost

  # Use all engines with low threshold for broad search
  python texttrace.py --text "some quote" --engines duckduckgo,bing,yandex --threshold 40

  # Fuzzy-only matching
  python texttrace.py --text "some quote" --tier fuzzy --threshold 70

  # Output as JSON for further processing
  python texttrace.py --text "some quote" --json > results.json
        """,
    )
    parser.add_argument("--text", "-t", help="Source text to search for")
    parser.add_argument("--url", "-u", help="URL to extract source text from")
    parser.add_argument("--threshold", type=float, default=50, help="Minimum match score (0-100, default: 50)")
    parser.add_argument("--tier", choices=["exact", "fuzzy", "stylometric", "all"], default="all", help="Matching tier (default: all)")
    parser.add_argument("--engines", default="duckduckgo,bing", help="Comma-separated search engines (default: duckduckgo,bing)")
    parser.add_argument("--max-results", type=int, default=15, help="Max results per engine (default: 15)")
    parser.add_argument("--no-extract", action="store_true", help="Skip full-page content extraction (faster but less accurate)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", "-o", help="Save report to file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not args.text and not args.url:
        parser.error("Either --text or --url is required")

    engines = [e.strip() for e in args.engines.split(",")]

    report = run_texttrace(
        source_text=args.text or "",
        source_url=args.url,
        threshold=args.threshold,
        tier=args.tier,
        engines=engines,
        max_results=args.max_results,
        extract_content=not args.no_extract,
        verbose=args.verbose,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n[✓] Report saved to: {args.output}")


if __name__ == "__main__":
    main()
