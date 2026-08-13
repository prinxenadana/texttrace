# 🔍 TextTrace — Cross-Platform Text Attribution OSINT Tool

**Find the same text posted across different platforms.**

Give it text from a Facebook post → it finds the same text on X (Twitter), Reddit, forums, blogs, and 30+ other platforms using three-tier matching.

---

## 🎯 What It Does

```
Source Text (e.g., Facebook post)
    │
    ▼
┌─────────────────────────────────────┐
│  SEARCH ENGINES                     │
│  DuckDuckGo · Bing · Yandex        │
│  - Exact phrase queries             │
│  - Proper noun combinations         │
│  - Content word groups              │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  THREE-TIER CONTENT MATCHING        │
│                                     │
│  Tier 1: EXACT — SHA-256 hash      │
│  → Identical copy-paste             │
│                                     │
│  Tier 2: FUZZY — rapidfuzz          │
│  → Near-duplicates, typos, edits    │
│                                     │
│  Tier 3: STYLOMETRIC — N-gram       │
│  → Same author, different wording   │
└──────────────┬──────────────────────┘
               │
               ▼
  Matches + scores + platform detection
  (X/Twitter, Facebook, Reddit, Telegram, etc.)
```

---

## ⚡ Quick Start

### Install dependencies

```bash
pip install httpx beautifulsoup4 rapidfuzz

# Optional: for advanced stylometric matching
pip install scikit-learn
```

### Run

```bash
# Search for exact text across the internet
python texttrace.py --text "Your text here"

# Extract text from a URL then search
python texttrace.py --url https://facebook.com/somepost

# All engines, broad search
python texttrace.py --text "some text" --engines duckduckgo,bing,yandex --threshold 40

# Fuzzy-only matching
python texttrace.py --text "some text" --tier fuzzy --threshold 70

# JSON output for scripting
python texttrace.py --text "some text" --json > results.json

# Save report to file
python texttrace.py --text "some text" --output report.json
```

---

## 🛠️ Options

| Flag | Default | Description |
|------|---------|-------------|
| `--text`, `-t` | — | Source text to search for |
| `--url`, `-u` | — | URL to extract source text from |
| `--threshold` | `50` | Minimum match score (0-100) |
| `--tier` | `all` | Matching tier: `exact`, `fuzzy`, `stylometric`, `all` |
| `--engines` | `duckduckgo,bing` | Comma-separated search engines |
| `--max-results` | `15` | Max results per engine |
| `--no-extract` | off | Skip full-page content extraction (faster but less accurate) |
| `--json` | off | Output results as JSON |
| `--output`, `-o` | — | Save report to file |
| `--verbose`, `-v` | off | Verbose output |

---

## 🔬 Matching Tiers Explained

### Tier 1: Exact (Hash Match)
SHA-256 of normalized text. Catches **identical copies** — same words, same order. No false positives.

### Tier 2: Fuzzy (String Similarity)
Uses [rapidfuzz](https://github.com/maxbachmann/rapidfuzz) with four metrics:
- **Ratio** — overall string similarity
- **Partial Ratio** — best substring match (catches quoted excerpts)
- **Token Sort Ratio** — word-order independent
- **Token Set Ratio** — handles extra/missing words

Great for catching near-duplicates where someone changed a few words.

### Tier 3: Stylometric (Writing Style)
Even if the text is completely rewritten, the **writing style** can match:
- Bigram/trigram cosine similarity
- TF-IDF cosine similarity (if scikit-learn installed)
- Captures sentence structure, word choice patterns

Best for linking **same author, different wording**.

---

## 🌐 Platform Detection

Automatically identifies 30+ platforms from result URLs:

| Category | Platforms |
|----------|-----------|
| **Social Media** | X/Twitter, Facebook, Instagram, Reddit, LinkedIn, TikTok, Threads, Snapchat, Pinterest, Tumblr |
| **Messaging** | Telegram, Discord, WhatsApp |
| **Video** | YouTube |
| **News/Blog** | Medium, Substack, Quora |
| **Alt Social** | Truth Social, Parler, Gab, Mastodon |
| **Dev/Tech** | GitHub, Pastebin |
| **Forums** | 4chan, 8kun |
| **Gaming** | Steam |
| **Regional** | VK (VKontakte), Weibo |

---

## 📋 Real-World OSINT Use Cases

| Use Case | Example |
|----------|---------|
| **Cross-posting detection** | Same person posting identical content across platforms under different identities |
| **Content theft/plagiarism** | Someone copied your post verbatim |
| **Misinformation tracking** | Same narrative appearing on multiple platforms simultaneously |
| **Dual-identity linking** | Matching writing style to connect anonymous accounts |
| **Brand monitoring** | Where is your content being reshared? |
| **Influence operation detection** | Coordinated messaging across platforms |

---

## 🔑 No API Keys Required

TextTrace uses **only free, no-auth methods**:

- **DuckDuckGo** — HTML search scraping
- **Bing** — search result parsing
- **Yandex** — search result parsing
- **BeautifulSoup** — web content extraction

No paid APIs. No rate-limited free tiers. No sign-ups.

---

## ⚠️ Limitations

- Rate-limited by search engines (3-4s delay between queries)
- Cannot access private/locked social media posts
- DDG may temporarily rate-limit (202 response) on excessive queries
- Stylometric matching needs 50+ words to be reliable
- Content extraction depends on page being publicly accessible

---

## 🤝 Contributing

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

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
