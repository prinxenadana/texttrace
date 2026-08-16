#!/usr/bin/env python3
"""
TextTrace v2 — Cross-Platform Text Attribution OSINT Tool
==========================================================
Red-team hardened. Async parallel search, Tor/proxy OPSEC, extended
stylometry, Wayback/Cache/paste-site coverage, batch/chain/watch modes,
site operators, entity extraction, partial matching, caching, checkpoints,
PDF reports, IOC extraction, diff view, confidence scoring,
stealth/aggressive modes, 40+ platforms.

Usage:
  python texttrace.py --text "Hello world" --tor
  python texttrace.py --text "some text" --site twitter.com --engines all
  python texttrace.py --batch targets.txt --output results/
  python texttrace.py --text "some text" --chain --depth 2
  python texttrace.py --url https://facebook.com/post --stealth
"""

import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
import random
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Dependencies ─────────────────────────────────────────────────────────────

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

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    import curl_cffi.requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

# ─── User Agent Pool (50+ real UAs) ───────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Vivaldi/7.1.0.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# ─── Platform Detection (40+ platforms) ───────────────────────────────────────

PLATFORM_PATTERNS = {
    "twitter/x": [r"(?:twitter\.com|x\.com)"],
    "facebook": [r"facebook\.com", r"fb\.com", r"fb\.me"],
    "instagram": [r"instagram\.com", r"instagr\.am"],
    "reddit": [r"reddit\.com"],
    "linkedin": [r"linkedin\.com"],
    "tiktok": [r"tiktok\.com"],
    "youtube": [r"youtube\.com", r"youtu\.be"],
    "telegram": [r"t\.me", r"telegram\.me"],
    "mastodon": [r"mastodon\.\w+", r"masto\.dn", r"poast\.cc"],
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
    "paste_e": [r"paste\.ee"],
    "ghostbin": [r"ghostbin\.com"],
    "justpaste": [r"justpaste\.it"],
    "4chan": [r"4chan\.org", r"4channel\.org"],
    "8kun": [r"8kun\.top"],
    "steam": [r"steamcommunity\.com"],
    "vkontakte": [r"vk\.com"],
    "weibo": [r"weibo\.\w+"],
    "snapchat": [r"snapchat\.com"],
    "bluesky": [r"bsky\.app"],
    "kick": [r"kick\.com"],
    "rumble": [r"rumble\.com"],
    "gettr": [r"gettr\.com"],
    "nostr": [r"nos\.lol", r"primal\.net", r"snort\.social"],
    "patreon": [r"patreon\.com"],
    "deviantart": [r"deviantart\.com"],
    "ao3": [r"archiveofourown\.org"],
    "fanfiction": [r"fanfiction\.net"],
    "xiaohongshu": [r"xiaohongshu\.com", r"xhslink\.com"],
    "stacker_news": [r"stacker\.news"],
}

# ─── Confidence Levels ─────────────────────────────────────────────────────────

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNVERIFIED = "UNVERIFIED"


def confidence_from_score(max_score: float, match_tier: str) -> str:
    """Determine confidence level from score and tier."""
    if "exact" in (match_tier or ""):
        return CONFIDENCE_HIGH
    elif max_score >= 75:
        return CONFIDENCE_MEDIUM
    elif max_score >= 50:
        return CONFIDENCE_LOW
    else:
        return CONFIDENCE_UNVERIFIED


# ─── Caching ──────────────────────────────────────────────────────────────────

CACHE_DIR = Path.home() / ".texttrace" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cache_get(fingerprint: str) -> Optional[dict]:
    """Check if we have cached results for this text fingerprint."""
    fpath = CACHE_DIR / f"{fingerprint}.json"
    if fpath.exists():
        age = time.time() - fpath.stat().st_mtime
        if age < 3600 * 6:  # 6 hour cache
            with open(fpath) as f:
                return json.load(f)
    return None


def cache_put(fingerprint: str, report: dict):
    """Cache a report by text fingerprint."""
    fpath = CACHE_DIR / f"{fingerprint}.json"
    with open(fpath, "w") as f:
        json.dump(report, f, indent=2, default=str)


# ─── Text Normalization ────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip URLs/special chars."""
    text = text.lower()
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[@#]', '', text)
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
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


# ─── Partial Matching (extract best substring) ────────────────────────────────

def partial_match_score(source: str, target: str) -> float:
    """Find the best-matching substring in target against source. 
    Uses sliding window approach — much more accurate for snippet-vs-fullpage."""
    if not HAS_RAPIDFUZZ:
        return 0.0

    src_norm = normalize_text(source)
    tgt_norm = normalize_text(target)
    src_words = src_norm.split()
    tgt_words = tgt_norm.split()

    if not src_words or not tgt_words:
        return 0.0

    # If source is shorter, find it in target
    src_len = len(src_words)
    tgt_len = len(tgt_words)

    if src_len >= tgt_len:
        # Just compare directly
        return fuzz.partial_ratio(src_norm, tgt_norm)

    best_score = 0.0
    window_size = src_len
    step = max(1, window_size // 4)

    for i in range(0, tgt_len - window_size + 1, step):
        window = " ".join(tgt_words[i:i + window_size])
        score = fuzz.partial_ratio(src_norm, window)
        if score > best_score:
            best_score = score
            if best_score >= 95:
                break  # Good enough

    return best_score


# ─── Tier 3: Extended Stylometric Match ────────────────────────────────────────

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

    return (dot / (mag_a * mag_b)) * 100


def vocabulary_richness(text: str) -> dict:
    """Vocabulary richness metrics — distinctive per author."""
    words = normalize_text(text).split()
    if not words:
        return {"ttr": 0, "hapax_ratio": 0, "yules_k": 0}

    types = set(words)
    tokens = len(words)
    freq = Counter(words)

    # Type-Token Ratio
    ttr = len(types) / tokens

    # Hapax Legomena Ratio (words appearing exactly once)
    hapax = sum(1 for w, c in freq.items() if c == 1)
    hapax_ratio = hapax / tokens

    # Yule's K (vocabulary diversity — lower = more diverse)
    N = tokens
    M2 = sum(c * c for c in freq.values())
    yules_k = 10000 * (M2 - N) / (N * N) if N > 0 else 0

    return {"ttr": round(ttr, 4), "hapax_ratio": round(hapax_ratio, 4), "yules_k": round(yules_k, 2)}


def punctuation_fingerprint(text: str) -> dict:
    """Punctuation usage patterns — very distinctive per author."""
    punct_chars = '.,;:!?-()[]{}"\'…–—'
    counts = Counter(c for c in text if c in punct_chars)
    total = sum(counts.values())
    if total == 0:
        return {}

    # Normalize to percentages
    return {f"punct_{k}": round(v / total * 100, 2) for k, v in counts.items()}


def sentence_length_stats(text: str) -> dict:
    """Sentence length distribution — distinctive per author."""
    sentences = re.split(r'[.!?]+', text)
    lengths = [len(s.split()) for s in sentences if len(s.split()) > 0]
    if not lengths:
        return {"sent_mean": 0, "sent_std": 0, "sent_min": 0, "sent_max": 0, "sent_median": 0}

    mean = sum(lengths) / len(lengths)
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    std = math.sqrt(variance)
    median = sorted(lengths)[len(lengths) // 2]

    return {
        "sent_mean": round(mean, 2),
        "sent_std": round(std, 2),
        "sent_min": min(lengths),
        "sent_max": max(lengths),
        "sent_median": median,
    }


def compare_stylometric_features(features_a: dict, features_b: dict) -> float:
    """Compare two sets of stylometric features, return 0-100 similarity."""
    common_keys = set(features_a.keys()) & set(features_b.keys())
    if not common_keys:
        return 0.0

    # Cosine similarity over feature vectors
    vec_a = [features_a[k] for k in common_keys]
    vec_b = [features_b[k] for k in common_keys]

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return (dot / (mag_a * mag_b)) * 100


def stylometric_score(source: str, target: str) -> dict:
    """Extended stylometric comparison — writeprints for authorship attribution."""
    scores = {
        "bigram_cosine": ngram_cosine_similarity(source, target, n=2),
        "trigram_cosine": ngram_cosine_similarity(source, target, n=3),
    }

    # Extended features
    vocab_a = vocabulary_richness(source)
    vocab_b = vocabulary_richness(target)
    vocab_similarity = compare_stylometric_features(vocab_a, vocab_b)
    scores["vocabulary_similarity"] = round(vocab_similarity, 2)

    punct_a = punctuation_fingerprint(source)
    punct_b = punctuation_fingerprint(target)
    punct_similarity = compare_stylometric_features(punct_a, punct_b)
    scores["punctuation_similarity"] = round(punct_similarity, 2)

    sent_a = sentence_length_stats(source)
    sent_b = sentence_length_stats(target)
    sent_similarity = compare_stylometric_features(sent_a, sent_b)
    scores["sentence_similarity"] = round(sent_similarity, 2)

    # TF-IDF (if sklearn available)
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

    # Weighted average — extended features get more weight
    weights = {
        "bigram_cosine": 1.0,
        "trigram_cosine": 1.5,
        "vocabulary_similarity": 2.0,
        "punctuation_similarity": 1.5,
        "sentence_similarity": 1.5,
        "tfidf_cosine": 2.0,
    }
    total_weight = sum(weights.get(k, 1.0) for k, v in scores.items() if v > 0)
    weighted_sum = sum(scores[k] * weights.get(k, 1.0) for k in scores if scores[k] > 0)
    scores["overall"] = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0

    # Store raw features for report
    scores["_vocab"] = vocab_a
    scores["_punct"] = punct_a
    scores["_sent"] = sent_a

    return scores


# ─── Entity Extraction ────────────────────────────────────────────────────────

def extract_entities(text: str) -> dict:
    """Extract named entities, emails, phone numbers, usernames, IPs from text."""
    entities = {
        "emails": list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))),
        "phones": list(set(re.findall(r'(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text))),
        "ips": list(set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text))),
        "urls": list(set(re.findall(r'https?://[^\s<>"\']+', text))),
        "usernames": list(set(re.findall(r'@([a-zA-Z0-9_]{3,15})', text))),
        "hashtags": list(set(re.findall(r'#([a-zA-Z0-9_]{2,})', text))),
    }

    # Named entity heuristics — capitalized sequences
    cap_words = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
    entities["named_entities"] = list(set(cap_words))[:20]

    return entities


def entity_overlap_score(entities_a: dict, entities_b: dict) -> float:
    """Calculate overlap between entity sets — strong same-author signal."""
    all_keys = set(entities_a.keys()) & set(entities_b.keys())
    if not all_keys:
        return 0.0

    overlaps = 0
    total = 0
    for key in all_keys:
        set_a = set(str(x).lower() for x in entities_a.get(key, []))
        set_b = set(str(x).lower() for x in entities_b.get(key, []))
        if set_a and set_b:
            overlap = len(set_a & set_b)
            union = len(set_a | set_b)
            if union > 0:
                overlaps += overlap
                total += union
        else:
            total += max(len(set_a), len(set_b))

    return (overlaps / total * 100) if total > 0 else 0.0


# ─── Diff View ────────────────────────────────────────────────────────────────

def text_diff(source: str, target: str) -> list:
    """Generate a word-level diff between source and target text."""
    src_words = normalize_text(source).split()
    tgt_words = normalize_text(target).split()

    from difflib import SequenceMatcher
    sm = SequenceMatcher(None, src_words, tgt_words)

    diff = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            diff.append({"type": "equal", "text": " ".join(src_words[i1:i2])})
        elif op == 'replace':
            diff.append({"type": "removed", "text": " ".join(src_words[i1:i2])})
            diff.append({"type": "added", "text": " ".join(tgt_words[j1:j2])})
        elif op == 'delete':
            diff.append({"type": "removed", "text": " ".join(src_words[i1:i2])})
        elif op == 'insert':
            diff.append({"type": "added", "text": " ".join(tgt_words[j1:j2])})

    return diff


# ─── Async Search Engine Scraping ─────────────────────────────────────────────

def _random_headers() -> dict:
    """Generate randomized headers with realistic browser ordering."""
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.8", "en,en-US;q=0.9"]),
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


async def _async_get(client: httpx.AsyncClient, url: str, params: dict = None, retries: int = 3) -> httpx.Response:
    """Async GET with retry and adaptive backoff."""
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params)
            if resp.status_code in (202, 429):
                # Rate limited — exponential backoff
                wait = (8 if resp.status_code == 202 else 15) * (2 ** attempt) + random.uniform(1, 5)
                print(f"    [!] Rate limited ({resp.status_code}), waiting {wait:.0f}s before retry {attempt+1}/{retries}...")
                await asyncio.sleep(wait)
                continue
            if resp.status_code == 403:
                # Blocked — not much we can do with this client
                return resp
            return resp
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt == retries:
                raise
            await asyncio.sleep(3 * (2 ** attempt))
    return None


async def search_duckduckgo(query: str, max_results: int = 30, client: httpx.AsyncClient = None) -> list:
    """Search DuckDuckGo HTML and parse results. Falls back to curl_cffi if blocked."""
    results = []

    try:
        # Try curl_cffi first for realistic TLS fingerprint (avoids 202 rate-limits)
        if HAS_CURL_CFFI:
            resp = cffi_requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                impersonate=random.choice(["chrome131", "chrome120", "chrome116"]),
                timeout=20,
            )
            html = resp.text if resp.status_code == 200 else ""
        else:
            if client is None:
                client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())
            resp = await _async_get(client, "https://html.duckduckgo.com/html/", params={"q": query})
            html = resp.text if resp and resp.status_code == 200 and len(resp.text) > 2000 else ""

        if not html:
            return results

        soup = BeautifulSoup(html, 'html.parser')
        for div in soup.find_all('div', class_=re.compile(r'result')):
            title_elem = div.find('a', class_='result__a')
            snippet_elem = div.find('a', class_='result__snippet') or div.find('td', class_='result__snippet')

            if not title_elem:
                continue

            raw_url = title_elem.get('href', '')
            title = title_elem.get_text(strip=True)
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

            real_url_match = re.search(r'uddg=([^&]+)', raw_url)
            url = urllib.parse.unquote(real_url_match.group(1)) if real_url_match else raw_url

            # Skip DDG internal links and /l/ redirects without real URLs
            if not url or url.startswith('/') or 'duckduckgo.com' in url:
                continue

            results.append({"title": title, "url": url, "snippet": snippet, "engine": "duckduckgo"})

    except Exception as e:
        print(f"  [!] DuckDuckGo search error: {e}")

    return results[:max_results]


async def search_bing(query: str, max_results: int = 20, client: httpx.AsyncClient = None) -> list:
    """Search Bing and parse results. Falls back to curl_cffi if blocked."""
    results = []
    try:
        # Try curl_cffi first for realistic TLS fingerprint
        if HAS_CURL_CFFI:
            resp = cffi_requests.get(
                "https://www.bing.com/search",
                params={"q": query},
                impersonate=random.choice(["chrome131", "chrome120", "chrome116"]),
                timeout=20,
            )
            html = resp.text if resp.status_code == 200 else ""
        else:
            if client is None:
                client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())
            resp = await _async_get(client, "https://www.bing.com/search", params={"q": query})
            html = resp.text if resp and resp.status_code == 200 else ""

        if not html or len(html) < 500:
            return results

        soup = BeautifulSoup(html, 'html.parser')
        for li in soup.find_all('li', class_='b_algo'):
            title_elem = li.find('h2')
            link_elem = li.find('a')
            snippet_elem = li.find('p') or li.find('div', class_='b_caption')

            if not link_elem:
                continue

            title = title_elem.get_text(strip=True) if title_elem else ''
            url = link_elem.get('href', '')
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

            if url and 'bing.com/ck/' in url:
                m = re.search(r'[?&]u=([^&]+)', url)
                if m:
                    # Bing encodes URLs as base64 with 2-char prefix
                    raw_u = m.group(1)
                    try:
                        decoded = base64.urlsafe_b64decode(raw_u[2:] + '==')
                        url = decoded.decode('utf-8', errors='ignore')
                    except Exception:
                        url = urllib.parse.unquote(raw_u)

            # Also use <cite> text as fallback for bing.com/ck/ URLs
            if url and 'bing.com/ck/' in url:
                cite = li.find('cite')
                if cite:
                    cite_text = cite.get_text(strip=True)
                    if cite_text.startswith('http'):
                        url = cite_text

            if url and url.startswith('http') and 'bing.com/ck/' not in url:
                results.append({"title": title, "url": url, "snippet": snippet, "engine": "bing"})

    except Exception as e:
        print(f"  [!] Bing search error: {e}")

    return results[:max_results]


async def search_yandex(query: str, max_results: int = 15, client: httpx.AsyncClient = None) -> list:
    """Search Yandex and parse results."""
    results = []
    try:
        headers = _random_headers()
        headers["Accept-Language"] = "en,en-US;q=0.9"
        if client is None:
            client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers)

        resp = await _async_get(client, "https://yandex.com/search/", params={"text": query, "lr": 87})
        if not resp or resp.status_code != 200:
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
                results.append({"title": title, "url": url, "snippet": snippet, "engine": "yandex"})

    except Exception as e:
        print(f"  [!] Yandex search error: {e}")

    return results[:max_results]


async def search_google(query: str, max_results: int = 20, client: httpx.AsyncClient = None) -> list:
    """Search Google via curl_cffi (stealth TLS) if available, else httpx."""
    results = []
    try:
        if HAS_CURL_CFFI:
            # Use curl_cffi for realistic TLS fingerprint
            resp = cffi_requests.get(
                "https://www.google.com/search",
                params={"q": query, "num": max_results},
                impersonate="chrome131",
                timeout=20,
            )
            text = resp.text
        else:
            if client is None:
                client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())
            resp = await _async_get(client, "https://www.google.com/search", params={"q": query, "num": str(max_results)})
            if not resp or resp.status_code != 200:
                return results
            text = resp.text

        soup = BeautifulSoup(text, 'html.parser')
        for g in soup.find_all('div', class_='g'):
            title_elem = g.find('h3')
            link_elem = g.find('a')
            snippet_elem = g.find('div', class_=['VwiC3b', 'yDYNvb'])

            if not link_elem:
                continue

            url = link_elem.get('href', '')
            title = title_elem.get_text(strip=True) if title_elem else ''
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

            if url and url.startswith('http'):
                results.append({"title": title, "url": url, "snippet": snippet, "engine": "google"})

    except Exception as e:
        print(f"  [!] Google search error: {e}")

    return results[:max_results]


async def search_github_code(query: str, max_results: int = 20, client: httpx.AsyncClient = None, github_token: str = None) -> list:
    """Search GitHub Code (public repos) for matching text.
    Strategy:
    1. If github_token provided → use GitHub REST API (authenticated, 30 req/min)
    2. No token → use DDG/Bing with site:github.com operator (scrapes GitHub results)
    No API key required for the fallback — works for free."""
    results = []
    try:
        # Strategy 1: Authenticated GitHub API
        if github_token:
            headers = _random_headers()
            headers["Accept"] = "application/vnd.github+json"
            headers["Authorization"] = f"Bearer {github_token}"

            if client is None:
                client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers)

            resp = await _async_get(client, "https://api.github.com/search/code", params={
                "q": query,
                "per_page": min(max_results, 30),
            })

            if resp and resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    repo = item.get("repository", {})
                    repo_full = repo.get("full_name", "")
                    path = item.get("path", "")
                    html_url = item.get("html_url", "")
                    title = f"{repo_full}/{path}" if repo_full else path
                    raw_url = f"https://raw.githubusercontent.com/{repo_full}/{repo.get('default_branch', 'main')}/{path}"
                    results.append({"title": title, "url": html_url, "snippet": item.get("name", ""), "engine": "github_code", "raw_url": raw_url})

            return results[:max_results]

        # Strategy 2: Search repos via API (unauthenticated, works)
        headers = _random_headers()
        headers["Accept"] = "application/vnd.github+json"

        repo_client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers)
        resp = await _async_get(repo_client, "https://api.github.com/search/repositories", params={
            "q": query,
            "per_page": min(max_results, 10),
        })
        await repo_client.aclose()

        if resp and resp.status_code == 200:
            data = resp.json()
            for item in data.get("items", []):
                full_name = item.get("full_name", "")
                html_url = item.get("html_url", "")
                desc = item.get("description", "")[:200] if item.get("description") else ""
                stars = item.get("stargazers_count", 0)
                results.append({
                    "title": f"{full_name} ★{stars}",
                    "url": html_url,
                    "snippet": desc,
                    "engine": "github_code",
                })

        # Strategy 3: Use DDG with site:github.com for code/file results
        site_query = f"site:github.com {query}"
        if HAS_CURL_CFFI:
            ddg_resp = cffi_requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": site_query},
                impersonate="chrome131",
                timeout=20,
            )
            html = ddg_resp.text if ddg_resp.status_code == 200 else ""
        else:
            if client is None:
                client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())
            ddg_resp = await _async_get(client, "https://html.duckduckgo.com/html/", params={"q": site_query})
            html = ddg_resp.text if ddg_resp and ddg_resp.status_code == 200 and len(ddg_resp.text) > 2000 else ""

        if html:
            soup = BeautifulSoup(html, 'html.parser')
            for div in soup.find_all('div', class_=re.compile(r'result')):
                title_elem = div.find('a', class_='result__a')
                if not title_elem:
                    continue
                raw_url = title_elem.get('href', '')
                title = title_elem.get_text(strip=True)
                url_match = re.search(r'uddg=([^&]+)', raw_url)
                url = urllib.parse.unquote(url_match.group(1)) if url_match else raw_url
                if url and 'github.com' in url:
                    results.append({"title": title, "url": url, "snippet": "", "engine": "github_code"})

    except Exception as e:
        print(f"  [!] GitHub Code search error: {e}")

    # Deduplicate by URL
    seen = set()
    unique = []
    for r in results:
        if r['url'] not in seen:
            seen.add(r['url'])
            unique.append(r)

    return unique[:max_results]


async def search_github_gists(query: str, max_results: int = 15, client: httpx.AsyncClient = None) -> list:
    """Search GitHub Gists for matching text.
    Gists are commonly used for pasting code, notes, leaked text.
    Uses GitHub's REST API — no auth needed (10 req/min unauthenticated)."""
    results = []
    try:
        headers = _random_headers()
        headers["Accept"] = "application/vnd.github+json"

        if client is None:
            client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers)

        # GitHub Gist search isn't a direct API endpoint, but we can use
        # the main GitHub search API with gist qualifier, or scrape the page
        # Use the web search approach for gists since API doesn't have gist search
        # Instead, we search via the regular search page for gists
        if HAS_CURL_CFFI:
            resp = cffi_requests.get(
                "https://gist.github.com/search",
                params={"q": query},
                impersonate="chrome131",
                timeout=20,
            )
            html = resp.text if resp.status_code == 200 else ""
        else:
            if client is None:
                client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers)
            resp = await _async_get(client, "https://gist.github.com/search", params={"q": query})
            html = resp.text if resp and resp.status_code == 200 else ""

        if not html:
            return results

        soup = BeautifulSoup(html, 'html.parser')

        # Parse gist results from the HTML
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            # Match gist URLs: /username/hash or gist.github.com/username/hash
            gist_match = re.match(r'/([a-zA-Z0-9\-]+)/([a-f0-9]{20,40})', href)
            if gist_match and gist_match.group(1) not in ('discover', 'global', 'search', 'login', 'signup', 'settings', 'explore', 'trending'):
                url = f"https://gist.github.com{href}" if href.startswith('/') else href
                title = link.get_text(strip=True) or f"Gist by {gist_match.group(1)}"
                results.append({"title": title, "url": url, "snippet": "", "engine": "github_gist"})

    except Exception as e:
        print(f"  [!] GitHub Gist search error: {e}")

    return results[:max_results]


async def search_wayback(url_pattern: str, client: httpx.AsyncClient = None) -> list:
    """Search Wayback Machine CDX API for archived versions of URLs matching a pattern."""
    results = []
    try:
        if client is None:
            client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())

        resp = await _async_get(client, "https://web.archive.org/cdx/search/cdx", params={
            "url": url_pattern,
            "matchType": "domain",
            "output": "json",
            "fl": "original,timestamp,statuscode",
            "limit": 20,
            "filter": "statuscode:200",
        })

        if not resp or resp.status_code != 200:
            return results

        data = resp.json()
        if len(data) <= 1:
            return results

        for row in data[1:]:  # Skip header row
            url, timestamp, status = row
            wayback_url = f"https://web.archive.org/web/{timestamp}/{url}"
            results.append({
                "title": f"Wayback Archive ({timestamp})",
                "url": wayback_url,
                "snippet": f"Archived version from {timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}",
                "engine": "wayback",
            })

    except Exception as e:
        print(f"  [!] Wayback search error: {e}")

    return results


async def search_google_cache(url: str, client: httpx.AsyncClient = None) -> list:
    """Check Google Cache for a URL."""
    results = []
    try:
        if client is None:
            client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())

        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        resp = await _async_get(client, cache_url)

        if resp and resp.status_code == 200:
            results.append({
                "title": f"Google Cache: {url[:80]}",
                "url": cache_url,
                "snippet": "Cached version available",
                "engine": "google_cache",
            })

    except Exception as e:
        print(f"  [!] Google Cache error: {e}")

    return results


async def search_archive_today(url: str, client: httpx.AsyncClient = None) -> list:
    """Check archive.today for archived versions."""
    results = []
    try:
        if client is None:
            client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())

        resp = await _async_get(client, f"https://archive.today/newest/{url}")
        if resp and resp.status_code == 200:
            results.append({
                "title": f"Archive.today: {url[:80]}",
                "url": f"https://archive.today/newest/{url}",
                "snippet": "Archived version available",
                "engine": "archive_today",
            })

    except Exception as e:
        print(f"  [!] Archive.today error: {e}")

    return results


async def search_paste_sites(query: str, client: httpx.AsyncClient = None) -> list:
    """Search paste sites (Pastebin, Paste.ee, etc.) for matching text."""
    results = []
    if client is None:
        client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())

    paste_sites = [
        ("pastebin.com", "https://pastebin.com/search?q=", "div.gsc-webResult"),
        ("paste.ee", "https://paste.ee/search?q=", None),
    ]

    for site_name, search_url, selector in paste_sites:
        try:
            resp = await _async_get(client, search_url + urllib.parse.quote(query))
            if resp and resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a.get('href', '')
                    text = a.get_text(strip=True)
                    if href and ('/p/' in href or '/raw' in href or '/view' in href):
                        full_url = href if href.startswith('http') else f"https://{site_name}{href}"
                        results.append({
                            "title": text[:100] if text else f"Paste on {site_name}",
                            "url": full_url,
                            "snippet": text[:200] if text else "",
                            "engine": f"paste_{site_name.split('.')[0]}",
                        })
        except Exception:
            continue

    return results[:15]


# ─── Content Extraction ────────────────────────────────────────────────────────

async def extract_text_from_url(url: str, client: httpx.AsyncClient = None) -> str:
    """Scrape and extract visible text from a URL."""
    try:
        if client is None:
            client = httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_random_headers())

        resp = await _async_get(client, url)
        if not resp or resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, 'html.parser')

        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
            tag.decompose()

        # Try to extract publish date
        date_meta = (
            soup.find('meta', attrs={'property': 'article:published_time'}) or
            soup.find('meta', attrs={'property': 'og:published_time'}) or
            soup.find('time')
        )

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


# ─── Search Query Generation (with operators) ──────────────────────────────────

def generate_search_queries(text: str, site: str = None, exclude: str = None) -> list:
    """Generate multiple search queries from source text for maximum coverage.
    Supports site: and -site: operators.
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

    # Build operator suffix
    op_suffix = ""
    if site:
        op_suffix += f" site:{site}"
    if exclude:
        for ex in exclude.split(","):
            ex = ex.strip()
            if ex:
                op_suffix += f" -site:{ex}"

    # ── Strategy 1: Proper nouns / distinctive capitalized terms ──
    original_words = text.split()
    proper_nouns = []
    for w in original_words:
        clean = re.sub(r'[^a-zA-Z0-9\-]', '', w)
        if not clean or len(clean) <= 2:
            continue
        is_capitalized = clean[0].isupper()
        is_all_caps = clean.isupper() and len(clean) > 2
        is_hyphenated = '-' in clean and len(clean) > 4

        if is_capitalized or is_all_caps or is_hyphenated:
            lower = clean.lower()
            if lower not in stop_words and lower not in {'people','often','one','two','also','around'}:
                proper_nouns.append(clean)

    proper_nouns = list(dict.fromkeys(proper_nouns))

    if proper_nouns:
        all_pairs = []
        for i in range(min(len(proper_nouns), 10)):
            for j in range(i + 1, min(len(proper_nouns), 10)):
                pair = f'{proper_nouns[i]} {proper_nouns[j]}'
                specificity = sum(len(w) for w in [proper_nouns[i], proper_nouns[j]])
                if '-' in proper_nouns[i] or '-' in proper_nouns[j]:
                    specificity += 10
                all_pairs.append((pair, specificity))

        all_pairs.sort(key=lambda x: x[1], reverse=True)
        for pair, _ in all_pairs:
            queries.append(pair + op_suffix)

        # Boolean AND queries
        if len(proper_nouns) >= 2:
            top2 = sorted(proper_nouns, key=len, reverse=True)[:2]
            queries.append(f"{top2[0]} AND {top2[1]}" + op_suffix)

        if len(proper_nouns) >= 3:
            sorted_nouns = sorted(proper_nouns, key=len, reverse=True)
            for i in range(min(len(sorted_nouns) - 2, 5)):
                queries.append(f'{sorted_nouns[i]} {sorted_nouns[i+1]} {sorted_nouns[i+2]}' + op_suffix)

    # ── Strategy 2: Content word groups ──
    content_words = [w for w in words if w not in stop_words and len(w) > 2]
    if len(content_words) >= 3:
        group_size = min(4, len(content_words))
        for i in range(0, min(len(content_words), 12), 3):
            group = content_words[i:i + group_size]
            if len(group) >= 3:
                queries.append(' '.join(group) + op_suffix)

    # ── Strategy 3: Short distinctive quoted phrases ──
    if len(words) >= 3:
        phrase = []
        for w in words:
            if w not in stop_words and len(w) > 2:
                phrase.append(w)
                if len(phrase) >= 3:
                    queries.append(f'"{ " ".join(phrase) }"' + op_suffix)
                    phrase = []
            else:
                if len(phrase) >= 3:
                    queries.append(f'"{" ".join(phrase)}"' + op_suffix)
                phrase = []

    # ── Strategy 4: Platform-specific queries ──
    if site:
        site_queries = []
        for pn in proper_nouns[:3]:
            site_queries.append(f"site:{site} {pn}")
        queries.extend(site_queries)

    # Deduplicate, filter too-short, preserve order
    seen = set()
    unique = []
    for q in queries:
        q_clean = q.strip()
        if q_clean and q_clean not in seen and len(q_clean) >= 8:
            seen.add(q_clean)
            unique.append(q_clean)

    return unique[:20]


# ─── Main Orchestration ────────────────────────────────────────────────────────

async def run_texttrace(
    source_text: str,
    source_url: str = None,
    threshold: float = 50,
    tier: str = "all",
    engines: list = None,
    max_results: int = 15,
    extract_content: bool = True,
    verbose: bool = False,
    quiet: bool = False,
    progress_callback=None,
    site: str = None,
    exclude: str = None,
    proxy: str = None,
    tor: bool = False,
    stealth: bool = False,
    aggressive: bool = False,
    check_archives: bool = True,
    check_paste_sites: bool = True,
    check_google: bool = True,
    batch_mode: bool = False,
    chain_mode: bool = False,
    chain_depth: int = 1,
    watch_mode: bool = False,
    watch_interval: int = 3600,
    output_dir: str = None,
    github_token: str = None,
) -> dict:
    """Main TextTrace v2 pipeline — async, OPSEC-hardened, full coverage."""

    def _emit(msg_type, message, **extra):
        if not quiet:
            print(message)
        if progress_callback:
            progress_callback({"type": msg_type, "message": message, **extra})

    start_time = time.time()

    # ── OPSEC Setup ──
    proxy_url = None
    if tor:
        proxy_url = "socks5://127.0.0.1:9050"
        _emit("opsec", "[🔒] Tor mode: routing through SOCKS5 proxy")
    elif proxy:
        proxy_url = proxy
        _emit("opsec", f"[🔒] Proxy: {proxy}")

    # Stealth = max delays, no page fetch, snippet-only
    if stealth:
        extract_content = False
        _emit("opsec", "[🔒] Stealth mode: snippet-only matching, no page fetching")

    # Aggressive = all engines, max results, deep crawl
    if aggressive:
        engines = ["duckduckgo", "bing", "yandex", "google", "github_code", "github_gist"]
        max_results = 50
        _emit("opsec", "[⚡] Aggressive mode: all engines, max results")

    # Build async client with proxy
    client_kwargs = {
        "timeout": 30 if not stealth else 60,
        "follow_redirects": True,
        "headers": _random_headers(),
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    async with httpx.AsyncClient(**client_kwargs) as client:

        # ── Step 1: Get source text ──
        if source_url:
            _emit("extract", f"[*] Extracting text from: {source_url}")
            extracted = await extract_text_from_url(source_url, client)
            if extracted:
                source_text = extracted
                _emit("extract", f"    Extracted {len(source_text)} characters")
            else:
                _emit("warning", "    [!] Failed to extract text, using provided text if any")

        if not source_text:
            return {"error": "No source text provided", "matches": []}

        preview = source_text[:200] + ("..." if len(source_text) > 200 else "")
        _emit("source", f"[*] Source text ({len(source_text)} chars): \"{preview}\"")

        src_fingerprint = text_fingerprint(source_text)
        _emit("fingerprint", f"    Fingerprint: {src_fingerprint[:16]}...", fingerprint=src_fingerprint)

        # ── Check Cache ──
        if not batch_mode and not chain_mode:
            cached = cache_get(src_fingerprint)
            if cached:
                _emit("cache", f"[*] Cache hit! Using cached results (age: {int(time.time() - CACHE_DIR.joinpath(f'{src_fingerprint}.json').stat().st_mtime)}s)")
                cached["metadata"]["from_cache"] = True
                return cached

        # ── Step 2: Generate search queries ──
        queries = generate_search_queries(source_text, site=site, exclude=exclude)
        _emit("queries", f"[*] Generated {len(queries)} search queries:", queries=queries)

        # ── Step 3: Search engines (PARALLEL) ──
        if engines is None:
            engines = ["duckduckgo", "bing"]
            if check_google:
                engines.append("google")
            engines.append("github_code")
            engines.append("github_gist")

        all_results = []
        seen_urls = set()

        _emit("searching", f"[*] Searching {len(engines)} engines in parallel...")

        # Build search tasks — each engine gets queries in parallel batches
        search_tasks = []

        for engine in engines:
            for qi, query in enumerate(queries[:10]):
                delay = random.uniform(2, 5) if stealth else random.uniform(0.5, 2)
                if engine == "duckduckgo":
                    search_tasks.append(("duckduckgo", query, delay))
                elif engine == "bing":
                    search_tasks.append(("bing", query, delay))
                elif engine == "yandex":
                    search_tasks.append(("yandex", query, delay))
                elif engine == "google":
                    search_tasks.append(("google", query, delay))
                elif engine == "github_code":
                    search_tasks.append(("github_code", query, delay))
                elif engine == "github_gist":
                    search_tasks.append(("github_gist", query, delay))

        # Execute searches with concurrency control
        semaphore = asyncio.Semaphore(5 if not stealth else 2)

        async def _search_with_semaphore(engine, query, delay):
            await asyncio.sleep(delay)
            async with semaphore:
                if engine == "duckduckgo":
                    return await search_duckduckgo(query, max_results, client)
                elif engine == "bing":
                    return await search_bing(query, max_results, client)
                elif engine == "yandex":
                    return await search_yandex(query, max_results, client)
                elif engine == "google":
                    return await search_google(query, max_results, client)
                elif engine == "github_code":
                    return await search_github_code(query, max_results, client, github_token=github_token)
                elif engine == "github_gist":
                    return await search_github_gists(query, max_results, client)
            return []

        # Run all searches concurrently
        task_coros = [_search_with_semaphore(e, q, d) for e, q, d in search_tasks]
        search_results = await asyncio.gather(*task_coros, return_exceptions=True)

        for result_list in search_results:
            if isinstance(result_list, Exception):
                continue
            for r in result_list:
                if r['url'] not in seen_urls:
                    seen_urls.add(r['url'])
                    all_results.append(r)

        _emit("results", f"[*] Found {len(all_results)} unique results from search engines", count=len(all_results))

        # ── Archive & Paste Site Checks ──
        if check_archives:
            _emit("searching", "[*] Checking archives (Wayback, Google Cache, Archive.today)...")
            archive_tasks = []
            # Check top matching URLs for archives
            for r in all_results[:10]:
                domain = urllib.parse.urlparse(r['url']).netloc
                archive_tasks.append(search_wayback(domain, client))
                archive_tasks.append(search_google_cache(r['url'], client))
                archive_tasks.append(search_archive_today(r['url'], client))

            archive_results = await asyncio.gather(*archive_tasks, return_exceptions=True)
            for result_list in archive_results:
                if isinstance(result_list, Exception):
                    continue
                for r in result_list:
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        all_results.append(r)

        if check_paste_sites:
            _emit("searching", "[*] Checking paste sites...")
            paste_results = await search_paste_sites(" ".join(normalize_text(source_text).split()[:6]), client)
            for r in paste_results:
                if r['url'] not in seen_urls:
                    seen_urls.add(r['url'])
                    all_results.append(r)

        _emit("results", f"[*] Total results including archives: {len(all_results)}", count=len(all_results))

        # ── Step 4: Extract & match ──
        matches = []
        source_platform = detect_platform(source_url) if source_url else "input"
        source_entities = extract_entities(source_text)

        # Checkpoint every 10 results
        checkpoint_count = 0

        for i, result in enumerate(all_results):
            platform = detect_platform(result['url'])
            snippet_text = result.get('snippet', '')

            match_data = {
                "url": result['url'],
                "title": result['title'],
                "platform": platform,
                "engine": result['engine'],
                "scores": {},
                "max_score": 0,
                "match_tier": None,
                "confidence": CONFIDENCE_UNVERIFIED,
                "entities": {},
                "entity_overlap": 0,
                "diff": [],
            }

            # Tier 1: Exact match
            if tier in ("all", "exact"):
                exact = exact_match_score(source_text, snippet_text)
                match_data["scores"]["exact"] = exact
                if exact > match_data["max_score"]:
                    match_data["max_score"] = exact
                    match_data["match_tier"] = "exact"

            # Tier 2: Fuzzy match
            if tier in ("all", "fuzzy") and HAS_RAPIDFUZZ:
                fuzzy = fuzzy_match_score(source_text, snippet_text)
                match_data["scores"]["fuzzy"] = fuzzy
                best_fuzzy = max(fuzzy.values())
                if best_fuzzy > match_data["max_score"]:
                    match_data["max_score"] = best_fuzzy
                    match_data["match_tier"] = "fuzzy"

            # Partial matching (sliding window)
            if tier in ("all", "fuzzy") and HAS_RAPIDFUZZ:
                partial = partial_match_score(source_text, snippet_text)
                match_data["scores"]["partial_window"] = partial
                if partial > match_data["max_score"]:
                    match_data["max_score"] = partial
                    match_data["match_tier"] = "fuzzy (partial)"

            # If snippet match is low and content extraction enabled, fetch page
            if extract_content and match_data["max_score"] < threshold:
                _emit("fetching", f"    [{i+1}/{len(all_results)}] Fetching: {result['url'][:80]}...", current=i+1, total=len(all_results))
                page_text = await extract_text_from_url(result['url'], client)

                if page_text and len(page_text) > 20:
                    # Partial match on full page (much better than comparing full source to full page)
                    if tier in ("all", "fuzzy") and HAS_RAPIDFUZZ:
                        partial_full = partial_match_score(source_text, page_text)
                        if partial_full > match_data["max_score"]:
                            match_data["scores"]["partial_fullpage"] = partial_full
                            match_data["max_score"] = partial_full
                            match_data["match_tier"] = "fuzzy (full page, partial)"

                    # Full fuzzy on page
                    if tier in ("all", "fuzzy") and HAS_RAPIDFUZZ:
                        fuzzy = fuzzy_match_score(source_text, page_text)
                        best_fuzzy = max(fuzzy.values())
                        if best_fuzzy > match_data["max_score"]:
                            match_data["scores"]["fuzzy_full"] = fuzzy
                            match_data["max_score"] = best_fuzzy
                            match_data["match_tier"] = "fuzzy (full page)"

                    # Exact on page
                    if tier in ("all", "exact"):
                        exact = exact_match_score(source_text, page_text)
                        if exact > match_data["scores"].get("exact", 0):
                            match_data["scores"]["exact_full"] = exact
                            if exact > match_data["max_score"]:
                                match_data["max_score"] = exact
                                match_data["match_tier"] = "exact (full page)"

                    # Stylometric on page
                    if tier in ("all", "stylometric"):
                        stylo = stylometric_score(source_text, page_text)
                        best_stylo = stylo.get("overall", 0)
                        if best_stylo > match_data["max_score"]:
                            match_data["scores"]["stylometric_full"] = stylo
                            match_data["max_score"] = best_stylo
                            match_data["match_tier"] = "stylometric (full page)"

                    # Entity extraction from matched page
                    page_entities = extract_entities(page_text)
                    match_data["entities"] = page_entities
                    entity_overlap = entity_overlap_score(source_entities, page_entities)
                    match_data["entity_overlap"] = round(entity_overlap, 2)
                    if entity_overlap > 30:  # Significant entity overlap boosts confidence
                        match_data["scores"]["entity_overlap"] = entity_overlap

                    # Diff view
                    if match_data["max_score"] > 30:
                        match_data["diff"] = text_diff(source_text, page_text)[:50]

                await asyncio.sleep(0.3 if not stealth else 1.5)

            # Tier 3: Stylometric on snippet
            if tier in ("all", "stylometric") and len(snippet_text) > 30:
                stylo = stylometric_score(source_text, snippet_text)
                best_stylo = stylo.get("overall", 0)
                if best_stylo > match_data["max_score"]:
                    match_data["scores"]["stylometric"] = stylo
                    match_data["max_score"] = best_stylo
                    match_data["match_tier"] = "stylometric"

            # Confidence level
            match_data["confidence"] = confidence_from_score(match_data["max_score"], match_data["match_tier"])

            # Include if above threshold
            if match_data["max_score"] >= threshold:
                matches.append(match_data)

            # Checkpoint every 10 results
            checkpoint_count += 1
            if checkpoint_count % 10 == 0 and output_dir:
                _save_checkpoint(output_dir, src_fingerprint, matches)

        # Sort by score descending
        matches.sort(key=lambda x: x['max_score'], reverse=True)

        elapsed = time.time() - start_time
        _emit("matching", f"[*] Matching complete: {len(matches)} matches above {threshold}% threshold", matches_count=len(matches))

        # ── Step 5: Build identity graph ──
        platform_to_matches = defaultdict(list)
        for m in matches:
            platform_to_matches[m['platform']].append(m)

        identity_links = []
        platforms_seen = set()
        for m in matches:
            if m['platform'] not in platforms_seen:
                platforms_seen.add(m['platform'])
            # Link matches with entity overlap > 30
            for other in matches:
                if other is m:
                    continue
                if m.get('entity_overlap', 0) > 30 and other.get('entity_overlap', 0) > 30:
                    shared_entities = set(str(x).lower() for x in m.get('entities', {}).get('emails', []) + m.get('entities', {}).get('usernames', []))
                    other_entities = set(str(x).lower() for x in other.get('entities', {}).get('emails', []) + other.get('entities', {}).get('usernames', []))
                    overlap = shared_entities & other_entities
                    if overlap:
                        identity_links.append({
                            "match_a_url": m['url'][:80],
                            "match_b_url": other['url'][:80],
                            "shared_entities": list(overlap),
                            "platform_a": m['platform'],
                            "platform_b": other['platform'],
                        })

        # ── Step 6: Build report ──
        report = {
            "metadata": {
                "version": "2.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_text_preview": source_text[:300],
                "source_fingerprint": src_fingerprint,
                "source_url": source_url,
                "source_platform": source_platform,
                "source_entities": source_entities,
                "threshold": threshold,
                "tier": tier,
                "engines_used": engines,
                "queries_generated": len(queries),
                "total_search_results": len(all_results),
                "elapsed_seconds": round(elapsed, 2),
                "opsec": {
                    "tor": tor,
                    "proxy": proxy if proxy else None,
                    "stealth": stealth,
                    "aggressive": aggressive,
                },
                "site_filter": site,
                "exclude_sites": exclude,
            },
            "stats": {
                "results_scanned": len(all_results),
                "matches_found": len(matches),
                "platforms_matched": list(set(m['platform'] for m in matches)),
                "match_tiers": dict(Counter(m['match_tier'] for m in matches)),
                "confidence_levels": dict(Counter(m['confidence'] for m in matches)),
                "avg_score": round(sum(m['max_score'] for m in matches) / len(matches), 2) if matches else 0,
            },
            "identity_graph": {
                "platforms": list(platforms_seen),
                "links": identity_links[:20],
            },
            "matches": matches,
            "next_steps": _generate_next_steps(matches, source_entities),
        }

        # Cache the report
        if not batch_mode:
            cache_put(src_fingerprint, report)

    # ── Chain mode: follow top matches ──
    if chain_mode and chain_depth > 0 and matches:
        _emit("chain", f"[*] Chain mode: following top {min(3, len(matches))} matches (depth {chain_depth})...")
        chain_reports = []
        for m in matches[:3]:
            if m['platform'] != source_platform:  # Don't chain to same platform
                chain_text = ""
                try:
                    chain_text = await extract_text_from_url(m['url'])
                except Exception:
                    continue
                if chain_text and len(chain_text) > 50:
                    chain_report = await run_texttrace(
                        source_text=chain_text,
                        threshold=threshold,
                        tier=tier,
                        engines=engines,
                        max_results=max_results,
                        extract_content=extract_content,
                        verbose=verbose,
                        progress_callback=progress_callback,
                        site=site,
                        exclude=exclude,
                        proxy=proxy_url,
                        chain_mode=True,
                        chain_depth=chain_depth - 1,
                        output_dir=output_dir,
                    )
                    if "matches" in chain_report:
                        chain_reports.append({"chained_from": m['url'][:80], "report": chain_report})

        if chain_reports:
            report["chain_results"] = chain_reports

    return report


def _generate_next_steps(matches: list, source_entities: dict) -> list:
    """Auto-generate recommended next steps based on results."""
    steps = []
    platforms = set(m['platform'] for m in matches)

    if "twitter/x" in platforms:
        steps.append("🐦 3+ Twitter/X matches found — run `maigret` or `sherlock` on discovered usernames")
    if "telegram" in platforms:
        steps.append("📱 Telegram matches found — search tgstat.com for channel membership")
    if "reddit" in platforms:
        steps.append("🖥 Reddit matches found — check user post history via old.reddit.com")
    if source_entities.get("emails"):
        steps.append(f"📧 Email found in source — run `holehe` or `h8mail` on: {', '.join(source_entities['emails'][:3])}")
    if source_entities.get("phones"):
        steps.append(f"📞 Phone found — run `PhoneInfoga` on: {', '.join(source_entities['phones'][:3])}")
    if len(matches) >= 5 and len(platforms) >= 3:
        steps.append("🔗 Multi-platform presence detected — build identity graph, check for cross-platform username reuse")

    return steps


def _save_checkpoint(output_dir: str, fingerprint: str, matches: list):
    """Save intermediate results as checkpoint."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    cp_file = out_path / f"checkpoint_{fingerprint[:12]}.json"
    with open(cp_file, "w") as f:
        json.dump({"checkpoint": True, "matches_so_far": matches}, f, indent=2, default=str)


# ─── PDF Report Generation ────────────────────────────────────────────────────

def generate_pdf_report(report: dict, output_path: str):
    """Generate a formatted PDF report."""
    if not HAS_FPDF:
        print("WARNING: fpdf2 not installed. Run: pip install fpdf2")
        return

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "TextTrace v2 - OSINT Attribution Report", ln=True, align="C")
    pdf.ln(5)

    # Metadata
    meta = report.get("metadata", {})
    stats = report.get("stats", {})
    pdf.set_font("Helvetica", "", 10)

    pdf.cell(0, 6, f"Generated: {meta.get('timestamp', 'N/A')}", ln=True)
    pdf.cell(0, 6, f"Source preview: {meta.get('source_text_preview', '')[:80]}...", ln=True)
    pdf.cell(0, 6, f"Fingerprint: {meta.get('source_fingerprint', '')[:24]}...", ln=True)
    pdf.cell(0, 6, f"Threshold: {meta.get('threshold', 'N/A')}%", ln=True)
    pdf.cell(0, 6, f"Elapsed: {meta.get('elapsed_seconds', 'N/A')}s", ln=True)
    pdf.cell(0, 6, f"Results scanned: {stats.get('results_scanned', 0)}", ln=True)
    pdf.cell(0, 6, f"Matches found: {stats.get('matches_found', 0)}", ln=True)
    pdf.cell(0, 6, f"Platforms: {', '.join(stats.get('platforms_matched', []))}", ln=True)
    pdf.ln(8)

    # Confidence summary
    conf_levels = stats.get("confidence_levels", {})
    if conf_levels:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Confidence Summary", ln=True)
        pdf.set_font("Helvetica", "", 10)
        for level, count in conf_levels.items():
            pdf.cell(0, 6, f"  {level}: {count} matches", ln=True)
        pdf.ln(5)

    # Top matches
    matches = report.get("matches", [])
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Top Matches", ln=True)
    pdf.set_font("Helvetica", "", 9)

    for i, m in enumerate(matches[:20]):
        conf = m.get("confidence", "UNVERIFIED")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, f"Match #{i+1} [{conf}] - Score: {m['max_score']:.1f}%", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, f"  Platform: {m['platform']}  |  Tier: {m.get('match_tier', 'N/A')}  |  Engine: {m['engine']}", ln=True)
        pdf.cell(0, 5, f"  URL: {m['url'][:100]}", ln=True)
        pdf.cell(0, 5, f"  Title: {m.get('title', '')[:80]}", ln=True)
        if m.get('entity_overlap', 0) > 0:
            pdf.cell(0, 5, f"  Entity overlap: {m['entity_overlap']:.1f}%", ln=True)
        pdf.ln(3)

    # Next steps
    next_steps = report.get("next_steps", [])
    if next_steps:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Recommended Next Steps", ln=True)
        pdf.set_font("Helvetica", "", 9)
        for step in next_steps:
            pdf.cell(0, 6, f"  {step}", ln=True)

    pdf.output(output_path)
    print(f"\n[+] PDF report saved to: {output_path}")


# ─── Report Formatting ─────────────────────────────────────────────────────────

def print_report(report: dict):
    """Pretty-print the TextTrace v2 report."""
    meta = report["metadata"]
    stats = report["stats"]
    matches = report["matches"]
    id_graph = report.get("identity_graph", {})

    print("\n" + "=" * 78)
    print("  🔍 TEXTTRACE v2 — Cross-Platform Text Attribution Report")
    print("=" * 78)

    print(f"\n  Source preview: \"{meta['source_text_preview'][:100]}...\"")
    print(f"  Fingerprint:    {meta['source_fingerprint'][:24]}...")
    print(f"  Source URL:     {meta.get('source_url', 'N/A')}")
    print(f"  Source platform: {meta['source_platform']}")
    print(f"  Threshold:      {meta['threshold']}%")
    print(f"  Matching tier:  {meta['tier']}")
    print(f"  Engines:        {', '.join(meta['engines_used'])}")
    print(f"  Scan time:      {meta['elapsed_seconds']}s")

    opsec = meta.get('opsec', {})
    if opsec.get('tor'):
        print(f"  OPSEC:          🔒 Tor")
    if opsec.get('proxy'):
        print(f"  OPSEC:          🔒 Proxy: {opsec['proxy']}")
    if opsec.get('stealth'):
        print(f"  OPSEC:          🔒 Stealth mode")
    if opsec.get('aggressive'):
        print(f"  Mode:           ⚡ Aggressive")

    print(f"\n  Results scanned: {stats['results_scanned']}")
    print(f"  Matches found:   {stats['matches_found']}")
    print(f"  Platforms:       {', '.join(stats['platforms_matched']) if stats['platforms_matched'] else 'none'}")
    print(f"  Match tiers:     {dict(stats['match_tiers'])}")
    print(f"  Confidence:      {dict(stats.get('confidence_levels', {}))}")
    print(f"  Avg score:       {stats.get('avg_score', 0):.1f}%")

    # Identity graph
    if id_graph.get('links'):
        print(f"\n  🔗 Identity Links: {len(id_graph['links'])} potential same-author connections")
        for link in id_graph['links'][:5]:
            print(f"    {link['platform_a']} ↔ {link['platform_b']} (shared: {', '.join(link.get('shared_entities', []))})")

    if not matches:
        print("\n  ⚠️  No matches found above threshold.")
        return

    print(f"\n{'─' * 78}")
    print(f"  TOP MATCHES")
    print(f"{'─' * 78}")

    for i, m in enumerate(matches[:20]):
        conf = m.get('confidence', 'UNVERIFIED')
        conf_icon = "🟢" if conf == "HIGH" else "🟡" if conf == "MEDIUM" else "🟠" if conf == "LOW" else "⚪"

        print(f"\n  ┌─ Match #{i+1} {conf_icon} [{conf}] ─────────────────────────")
        print(f"  │ Platform:     {m['platform']}")
        print(f"  │ Score:        {m['max_score']:.1f}%")
        print(f"  │ Tier:         {m['match_tier']}")
        print(f"  │ URL:          {m['url'][:100]}")
        print(f"  │ Title:        {m['title'][:80]}")
        print(f"  │ Engine:       {m['engine']}")
        if m.get('entity_overlap', 0) > 0:
            print(f"  │ Entity overlap: {m['entity_overlap']:.1f}%")

        for score_name, score_val in m['scores'].items():
            if isinstance(score_val, dict):
                if score_name.startswith('_'):
                    continue  # Skip raw features in summary
                print(f"  │ {score_name}:")
                for k, v in score_val.items():
                    if k.startswith('_'):
                        continue
                    print(f"  │   {k}: {v:.1f}" if isinstance(v, float) else f"  │   {k}: {v}")
            else:
                print(f"  │ {score_name}: {score_val:.1f}")

        print(f"  └─────────────────────────────────────────────────────")

    # Next steps
    next_steps = report.get("next_steps", [])
    if next_steps:
        print(f"\n{'─' * 78}")
        print(f"  📋 RECOMMENDED NEXT STEPS")
        print(f"{'─' * 78}")
        for step in next_steps:
            print(f"  {step}")

    print(f"\n{'=' * 78}")
    print(f"  Total: {len(matches)} matches above {meta['threshold']}% threshold")
    print(f"{'=' * 78}\n")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TextTrace v2 — Cross-Platform Text Attribution OSINT Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  python texttrace.py --text "I think AI will change everything"

  # Search with Tor for OPSEC
  python texttrace.py --text "some text" --tor

  # Search only on Twitter
  python texttrace.py --text "some text" --site twitter.com

  # Stealth mode (max OPSEC, snippet-only)
  python texttrace.py --text "some text" --stealth

  # Aggressive mode (all engines, max results)
  python texttrace.py --text "some text" --aggressive

  # Batch mode — search multiple texts from file
  python texttrace.py --batch targets.txt --output results/

  # Chain mode — follow top matches recursively
  python texttrace.py --text "some text" --chain --depth 2

  # Watch mode — re-run every 2 hours
  python texttrace.py --text "some text" --watch --interval 7200

  # PDF report
  python texttrace.py --text "some text" --pdf report.pdf

  # URL source with all engines
  python texttrace.py --url https://facebook.com/somepost --engines all
        """,
    )

    # Input
    parser.add_argument("--text", "-t", help="Source text to search for")
    parser.add_argument("--url", "-u", help="URL to extract source text from")
    parser.add_argument("--batch", help="File with one text per line for batch mode")

    # Search options
    parser.add_argument("--threshold", type=float, default=50, help="Minimum match score 0-100 (default: 50)")
    parser.add_argument("--tier", choices=["exact", "fuzzy", "stylometric", "all"], default="all", help="Matching tier (default: all)")
    parser.add_argument("--engines", default="duckduckgo,bing", help="Comma-separated engines or 'all' (default: duckduckgo,bing)")
    parser.add_argument("--max-results", type=int, default=15, help="Max results per engine (default: 15)")
    parser.add_argument("--no-extract", action="store_true", help="Skip full-page content extraction")
    parser.add_argument("--site", help="Only search this platform (e.g., twitter.com, reddit.com)")
    parser.add_argument("--exclude", help="Exclude these sites (comma-separated, e.g., pinterest.com,facebook.com)")

    # OPSEC
    parser.add_argument("--tor", action="store_true", help="Route through Tor SOCKS5 proxy (127.0.0.1:9050)")
    parser.add_argument("--proxy", help="Custom proxy URL (e.g., socks5://host:port, http://host:port)")
    parser.add_argument("--stealth", action="store_true", help="Stealth mode: max delays, snippet-only, no page fetch")
    parser.add_argument("--aggressive", action="store_true", help="Aggressive mode: all engines, max results, deep crawl")
    parser.add_argument("--github-token", help="GitHub PAT for authenticated code search (30 req/min vs 10 unauthenticated)")

    # Coverage
    parser.add_argument("--no-archives", action="store_true", help="Skip archive checks (Wayback, Google Cache)")
    parser.add_argument("--no-paste", action="store_true", help="Skip paste site checks")
    parser.add_argument("--no-google", action="store_true", help="Skip Google search")

    # Operational modes
    parser.add_argument("--chain", action="store_true", help="Chain mode: follow top matches recursively")
    parser.add_argument("--depth", type=int, default=1, help="Chain depth (default: 1)")
    parser.add_argument("--watch", action="store_true", help="Watch mode: re-run periodically")
    parser.add_argument("--interval", type=int, default=3600, help="Watch interval in seconds (default: 3600)")

    # Output
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", "-o", help="Save report to file")
    parser.add_argument("--pdf", help="Generate PDF report to file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not args.text and not args.url and not args.batch:
        parser.error("Either --text, --url, or --batch is required")

    # Parse engines
    if args.engines == "all":
        engines = ["duckduckgo", "bing", "yandex", "google", "github_code", "github_gist"]
    else:
        engines = [e.strip() for e in args.engines.split(",")]

    # ── Batch mode ──
    if args.batch:
        with open(args.batch) as f:
            texts = [line.strip() for line in f if line.strip()]

        print(f"\n[*] Batch mode: {len(texts)} texts to process")
        results = []

        for idx, text in enumerate(texts):
            print(f"\n{'='*60}")
            print(f"  Batch item {idx+1}/{len(texts)}: \"{text[:60]}...\"")
            print(f"{'='*60}")

            report = asyncio.run(run_texttrace(
                source_text=text,
                threshold=args.threshold,
                tier=args.tier,
                engines=engines,
                max_results=args.max_results,
                extract_content=not args.no_extract,
                verbose=args.verbose,
        quiet=args.json,
                site=args.site,
                exclude=args.exclude,
                proxy=args.proxy,
                tor=args.tor,
                stealth=args.stealth,
                aggressive=args.aggressive,
                check_archives=not args.no_archives,
                check_paste_sites=not args.no_paste,
                check_google=not args.no_google,
                batch_mode=True,
                output_dir=args.output,
            ))

            if args.output:
                out_path = Path(args.output)
                out_path.mkdir(parents=True, exist_ok=True)
                with open(out_path / f"batch_{idx+1}.json", "w") as fout:
                    json.dump(report, fout, indent=2, default=str)

            results.append(report)

        print(f"\n[*] Batch complete: {len(results)} reports generated")
        if args.output:
            print(f"[*] Reports saved to: {args.output}/")
        return

    # ── Watch mode ──
    if args.watch:
        print(f"\n[*] Watch mode: running every {args.interval}s (Ctrl+C to stop)")
        iteration = 0
        while True:
            iteration += 1
            print(f"\n{'='*60}")
            print(f"  Watch iteration #{iteration} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            report = asyncio.run(run_texttrace(
                source_text=args.text or "",
                source_url=args.url,
                threshold=args.threshold,
                tier=args.tier,
                engines=engines,
                max_results=args.max_results,
                extract_content=not args.no_extract,
                verbose=args.verbose,
        quiet=args.json,
                site=args.site,
                exclude=args.exclude,
                proxy=args.proxy,
                tor=args.tor,
                stealth=args.stealth,
                aggressive=args.aggressive,
                check_archives=not args.no_archives,
                check_paste_sites=not args.no_paste,
                check_google=not args.no_google,
                output_dir=args.output,
            ))

            if args.json:
                print(json.dumps(report, indent=2, default=str))
            else:
                print_report(report)

            if args.pdf:
                generate_pdf_report(report, args.pdf)

            if args.output:
                out_path = Path(args.output)
                out_path.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                with open(out_path / f"watch_{ts}.json", "w") as f:
                    json.dump(report, f, indent=2, default=str)

            print(f"\n[*] Next run in {args.interval}s...")
            time.sleep(args.interval)

    # ── Single run ──
    report = asyncio.run(run_texttrace(
        source_text=args.text or "",
        source_url=args.url,
        threshold=args.threshold,
        tier=args.tier,
        engines=engines,
        max_results=args.max_results,
        extract_content=not args.no_extract,
        verbose=args.verbose,
        quiet=args.json,
        site=args.site,
        exclude=args.exclude,
        proxy=args.proxy,
        tor=args.tor,
        stealth=args.stealth,
        aggressive=args.aggressive,
        check_archives=not args.no_archives,
        check_paste_sites=not args.no_paste,
        check_google=not args.no_google,
        chain_mode=args.chain,
        chain_depth=args.depth,
        output_dir=args.output,
        github_token=args.github_token,
    ))

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)

    if args.pdf:
        generate_pdf_report(report, args.pdf)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n[✓] Report saved to: {args.output}")


if __name__ == "__main__":
    main()
