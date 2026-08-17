# 🔍 TextTrace v2 — Cross-Platform Text Attribution OSINT Tool

**Find the same text — or the same author — across 42+ platforms.**

Give it text from a Facebook post → it finds the same text on X (Twitter), Reddit, forums, blogs, paste sites, archived pages, and 40+ other platforms using three-tier matching with confidence scoring.

**v2 is a complete rewrite** with async parallel search, OPSEC hardening (Tor/proxy/stealth), extended stylometric authorship attribution, Google search via curl_cffi, archive coverage (Wayback/Cache/Archive.today), batch/chain/watch operational modes, entity extraction, diff view, PDF reports, and a full web dashboard.

---

## 🎯 What It Does

```
Source Text (e.g., Facebook post)
    │
    ▼
┌─────────────────────────────────────────────┐
│  SEARCH ENGINES (async parallel)             │
│  DuckDuckGo · Bing · Yandex · Google        │
│  + Wayback CDX · Google Cache · Archive.today│
│  + Paste sites (Pastebin, Paste.ee)          │
│  - Exact phrase queries                      │
│  - Proper noun combinations                  │
│  - Site operators (--site twitter.com)       │
│  - 50+ rotating user agents                  │
│  - curl_cffi stealth TLS fingerprints        │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  FIVE-TIER CONTENT MATCHING                  │
│                                              │
│  Tier 1: EXACT — SHA-256 hash              │
│  → Identical copy-paste                      │
│                                              │
│  Tier 2: FUZZY — rapidfuzz                  │
│  → Near-duplicates, typos, edits            │
│                                              │
│  Tier 2b: PARTIAL — sliding window          │
│  → Snippet embedded in full page             │
│                                              │
│  Tier 3: EXTENDED STYLOMETRIC               │
│  → Vocabulary richness (TTR, Yule's K)      │
│  → Punctuation fingerprint                  │
│  → Sentence length distribution              │
│  → N-gram cosine similarity                 │
│  → TF-IDF cosine (with sklearn)             │
│  → Same author, different wording            │
│                                              │
│  Tier 4: ENTITY OVERLAP                     │
│  → Shared emails, usernames, phones, IPs    │
│  → Strong same-author signal                │
└──────────────┬──────────────────────────────┘
               │
               ▼
  Matches + confidence scores + platform detection
  + identity graph + entity extraction + diff view
  (X/Twitter, Facebook, Reddit, Telegram, Pastebin, etc.)
```

---

## ⚡ Quick Start

### Install dependencies

```bash
pip install httpx beautifulsoup4 rapidfuzz fpdf2 curl-cffi

# Optional: for advanced TF-IDF stylometric matching
pip install scikit-learn
```

### Run

```bash
# Basic search
python texttrace.py --text "Your text here"

# Extract text from a URL then search
python texttrace.py --url https://facebook.com/somepost

# All engines (DDG + Bing + Yandex + Google)
python texttrace.py --text "some text" --engines all

# Route through Tor for OPSEC
python texttrace.py --text "some text" --tor

# Stealth mode (max OPSEC — snippet-only, no page fetching)
python texttrace.py --text "some text" --stealth

# Aggressive mode (all engines, max results, deep crawl)
python texttrace.py --text "some text" --aggressive

# Search only on Twitter/X
python texttrace.py --text "some text" --site twitter.com

# Chain mode — follow top matches and re-trace them
python texttrace.py --text "some text" --chain --depth 2

# Batch mode — process multiple texts from file
python texttrace.py --batch targets.txt --output results/

# Watch mode — re-run every 2 hours
python texttrace.py --text "some text" --watch --interval 7200

# Generate PDF report
python texttrace.py --text "some text" --pdf report.pdf

# JSON output for scripting
python texttrace.py --text "some text" --json > results.json
```

---

## 🛡️ OPSEC Modes

TextTrace v2 is red-team hardened. Three OPSEC modes for different threat models:

| Mode | Flag | Behavior |
|------|------|----------|
| **Normal** | _(default)_ | Standard search, extracts full page content for comparison |
| **Stealth** | `--stealth` | Maximum OPSEC — snippet-only matching, no page fetching, long delays between requests, limited concurrency |
| **Aggressive** | `--aggressive` | All engines, max results, deep crawl — use when speed matters more than OPSEC |
| **Tor** | `--tor` | Routes ALL traffic through Tor SOCKS5 proxy (127.0.0.1:9050) |
| **Custom Proxy** | `--proxy socks5://host:port` | Route through any SOCKS5/HTTP proxy |

### Anti-Detection Features

- **50+ rotating User-Agent strings** — real browser UAs from Chrome, Firefox, Safari, Edge, Opera, Vivaldi
- **curl_cffi TLS fingerprints** — realistic browser TLS handshakes (avoids bot detection on DDG, Bing, Google)
- **Exponential backoff** on rate limits (202/429) — auto-retries with increasing wait times
- **Per-request header randomization** — Accept-Language, Cache-Control, etc.
- **Concurrent search with semaphore** — up to 5 parallel requests (2 in stealth mode)

---

## 🧠 Matching Tiers Explained

### Tier 1: Exact (Hash Match)
SHA-256 of normalized text. Catches **identical copies** — same words, same order. No false positives.

### Tier 2: Fuzzy (String Similarity)
Uses [rapidfuzz](https://github.com/maxbachmann/rapidfuzz) with four metrics:
- **Ratio** — overall string similarity
- **Partial Ratio** — best substring match (catches quoted excerpts)
- **Token Sort Ratio** — word-order independent
- **Token Set Ratio** — handles extra/missing words

Plus **sliding-window partial matching** — finds the best-matching substring in a full page against your source text. Much more accurate than comparing full-page to full-page.

### Tier 3: Extended Stylometric (Writing Style)
**New in v2** — even if the text is completely rewritten, the writing style can match:

| Feature | What It Measures |
|---------|-----------------|
| **Vocabulary richness** | Type-Token Ratio, Hapax Legomena, Yule's K — how diverse is the vocabulary? |
| **Punctuation fingerprint** | Usage patterns of .,;:!?()- — very distinctive per author |
| **Sentence length stats** | Mean, std dev, min, max, median — captures writing rhythm |
| **N-gram cosine** | Bigram/trigram overlap — captures phrase patterns |
| **TF-IDF cosine** | (with sklearn) Weighted term importance comparison |

Best for linking **same author, different wording**.

### Tier 4: Entity Overlap
Extracts named entities (emails, phones, IPs, usernames, hashtags, capitalized sequences) from both source and match text. Overlapping entities = strong same-author signal.

### Confidence Scoring

Every match gets a confidence level:

| Level | Badge | Criteria |
|-------|-------|----------|
| **HIGH** | 🟢 | Exact hash match |
| **MEDIUM** | 🟡 | Score ≥ 75% |
| **LOW** | 🟠 | Score ≥ 50% |
| **UNVERIFIED** | ⚪ | Score < 50% |

---

## 🌐 Platform Detection (42+ Platforms)

Automatically identifies platforms from result URLs:

| Category | Platforms |
|----------|-----------|
| **Social Media** | X/Twitter, Facebook, Instagram, Reddit, LinkedIn, TikTok, Threads, Snapchat, Pinterest, Tumblr, Bluesky, Kick |
| **Messaging** | Telegram, Discord, WhatsApp |
| **Video** | YouTube, Rumble |
| **News/Blog** | Medium, Substack, Quora, Patreon |
| **Alt Social** | Truth Social, Parler, Gab, Mastodon, Nostr, GETTR, Stacker News |
| **Dev/Tech** | GitHub |
| **Paste Sites** | Pastebin, Paste.ee, Ghostbin, JustPaste.it |
| **Forums** | 4chan, 8kun |
| **Gaming** | Steam |
| **Regional** | VK (VKontakte), Weibo, Xiaohongshu |
| **Creative** | DeviantArt, AO3, FanFiction.net |

---

## 🔧 All Options

| Flag | Default | Description |
|------|---------|-------------|
| `--text`, `-t` | — | Source text to search for |
| `--url`, `-u` | — | URL to extract source text from |
| `--batch` | — | File with one text per line for batch mode |
| `--threshold` | `50` | Minimum match score (0-100) |
| `--tier` | `all` | Matching tier: `exact`, `fuzzy`, `stylometric`, `all` |
| `--engines` | `duckduckgo,bing` | Comma-separated engines or `all` |
| `--max-results` | `15` | Max results per engine |
| `--no-extract` | off | Skip full-page content extraction |
| `--site` | — | Only search this platform (e.g., `twitter.com`) |
| `--exclude` | — | Exclude sites (comma-separated) |
| `--tor` | off | Route through Tor SOCKS5 proxy (:9050) |
| `--proxy` | — | Custom proxy URL (socks5/http) |
| `--stealth` | off | Stealth mode: max delays, snippet-only |
| `--aggressive` | off | Aggressive mode: all engines, max results |
| `--no-archives` | off | Skip archive checks (Wayback, Cache, Archive.today) |
| `--no-paste` | off | Skip paste site checks |
| `--no-google` | off | Skip Google search |
| `--chain` | off | Chain mode: follow top matches recursively |
| `--depth` | `1` | Chain depth (1-3) |
| `--watch` | off | Watch mode: re-run periodically |
| `--interval` | `3600` | Watch interval in seconds |
| `--json` | off | Output as JSON |
| `--output`, `-o` | — | Save report to file |
| `--pdf` | — | Generate PDF report |
| `--verbose`, `-v` | off | Verbose output |

---

## 🖥️ Web Dashboard

TextTrace includes a **local web dashboard** — a modern, dark-themed OSINT UI with real-time streaming, confidence badges, entity tags, diff view, and identity graph visualization.

![TextTrace v2 Dashboard](dashboard-screenshot.png)

### Quick Start

```bash
# Install dashboard dependencies
pip install -r dashboard-requirements.txt

# Launch the dashboard
python app.py

# → Open http://localhost:5000 in your browser
```

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Text / URL Input** | Paste source text or provide a URL to extract from |
| **Tier Selection** | Choose exact, fuzzy, stylometric, or all matching tiers |
| **Engine Selection** | Pick which search engines to use (DDG, Bing, Yandex, Google, all) |
| **Threshold Slider** | Adjust match sensitivity from 0-100% |
| **OPSEC Panel** | Toggle Tor, stealth, aggressive modes; set custom proxy |
| **Site Filters** | Target specific platforms or exclude noise |
| **Chain Mode** | Multi-hop attribution from the dashboard |
| **Archive/Paste Toggles** | Enable/disable Wayback, Cache, paste site checks |
| **Live Progress (SSE)** | Real-time streaming of search progress with progress bar |
| **Confidence Badges** | 🟢 HIGH / 🟡 MEDIUM / 🟠 LOW / ⚪ UNVERIFIED |
| **Entity Tags** | Extracted emails, usernames, phones shown as tags |
| **Diff View** | Word-level diff between source and match (red/green) |
| **Identity Graph** | Cross-platform same-author connection links |
| **Next Steps** | Auto-generated OSINT recommendations based on results |
| **Stats Dashboard** | At-a-glance: matches, scanned, platforms, time, confidence breakdown |
| **Match Cards** | Expandable cards with full score breakdowns and entity overlap |
| **Search History** | All past searches saved locally — click to reload |
| **JSON/PDF Export** | Download any report as JSON or PDF |

### Network Access

```bash
# Localhost only (default)
python app.py --port 5000

# Accessible from network
python app.py --host 0.0.0.0 --port 8080
```

### Dashboard Architecture

```
Browser (UI)  ←──SSE──→  Flask (app.py)  ──→  texttrace.py
     │                         │
     │                         ├── /api/search (POST) → starts background search
     │                         ├── /api/progress/<id> (SSE) → real-time updates
     │                         ├── /api/history (GET) → past searches
     │                         ├── /api/history/<id> (GET) → full report
     │                         ├── /api/history/<id>/download (GET) → JSON export
     │                         ├── /api/history/<id>/pdf (GET) → PDF report
     │                         └── /api/health (GET) → feature flags
     │
     └── data/history/*.json → locally saved reports
```

---

## 🔑 No API Keys Required

TextTrace uses **only free, no-auth methods** (core) — with optional auth for enhanced coverage:

| Feature | No Key? | With Key? |
|---------|---------|-----------|
| DDG / Bing / Yandex search | ✅ Free | — |
| GitHub Code search | ✅ Free (repos + DDG fallback) | `--github-token` → full code search API (30 req/min) |
| Wayback / Google Cache / Archive.today | ✅ Free | — |
| Paste sites | ✅ Free | — |
| Stylometry / Fuzzy match | ✅ Free | — |

## 🌍 Multi-Language Support

TextTrace works with **any language** — not just English:

| Language | Support | Tokenization |
|----------|---------|-------------|
| English / Latin scripts | ✅ Full | Word-level (whitespace) |
| Chinese (中文) | ✅ Full | Character-level + bigrams |
| Japanese (日本語) | ✅ Full | Character-level (Hiragana/Katakana/Kanji) |
| Korean (한국어) | ✅ Full | Character-level (Hangul) |
| Arabic (العربية) | ✅ Full | Word-level + Arabic stop words |
| Russian / Cyrillic (Русский) | ✅ Full | Word-level |
| Hindi / Devanagari (हिन्दी) | ✅ Full | Word-level |
| Mixed / Multilingual | ✅ Full | Auto-detect + mixed tokenization |

**How it works:**
- Auto-detects the script/language from Unicode ranges
- CJK text: character-level tokenization + bigram matching (no spaces between words)
- Arabic: word-level + Arabic stop word filtering
- Named entity extraction works for all scripts (Unicode regex)
- Stylometry adapts per language (CJK: char-level n-grams; Latin: word-level)
- Search queries adapt: CJK uses phrase queries, Arabic filters common words

- **DuckDuckGo** — HTML search scraping (via curl_cffi for stealth TLS)
- **Bing** — search result parsing (via curl_cffi)
- **Yandex** — search result parsing
- **Google** — search via curl_cffi browser impersonation
- **GitHub Code** — search public repo code (no API key)
- **GitHub Gists** — search gists (common for leaked text/pastebin-style content)
- **Wayback Machine** — free CDX API, no auth
- **Google Cache** — public cache URLs
- **Archive.today** — public archive
- **Paste sites** — Pastebin, Paste.ee search

No paid APIs. No rate-limited free tiers. No sign-ups. This is an **OPSEC advantage** — no API keys to leak, no accounts to compromise.

---

## 📋 Real-World OSINT Use Cases

| Use Case | Example |
|----------|---------|
| **Cross-posting detection** | Same person posting identical content across platforms under different identities |
| **Content theft/plagiarism** | Someone copied your post verbatim |
| **Misinformation tracking** | Same narrative appearing on multiple platforms simultaneously |
| **Dual-identity linking** | Matching writing style to connect anonymous accounts |
| **Authorship attribution** | Link anonymous posts to a known author via stylometric analysis |
| **Brand monitoring** | Where is your content being reshared? |
| **Influence operation detection** | Coordinated messaging across platforms |
| **Deleted content recovery** | Find cached/archived versions of removed posts |
| **Leak detection** | Find your text on paste sites (Pastebin, etc.) |
| **Multi-hop tracing** | Chain mode: trace matches, extract their text, trace again |

---

## ⚠️ Limitations

- Search engines may rate-limit on excessive queries (exponential backoff handles this)
- Cannot access private/locked social media posts
- Stylometric matching needs 50+ words to be reliable
- Content extraction depends on page being publicly accessible
- Google may occasionally block even curl_cffi — use `--tor` for IP rotation
- Watch mode runs indefinitely until Ctrl+C

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## ⭐ Support

If this tool helped your investigation, give it a star! It helps others discover it.

---

<p align="center">
  Built for OSINT investigators, by OSINT investigators 🔍
</p>
