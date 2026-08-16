#!/usr/bin/env python3
"""
TextTrace Web Dashboard v2 — Local web UI for the TextTrace OSINT tool.
Serves a modern dashboard interface that wraps texttrace.py v2.

Usage:
    python app.py                  # Default: http://localhost:5000
    python app.py --port 8080      # Custom port
    python app.py --host 0.0.0.0   # Accessible from network
"""

import argparse
import asyncio
import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, send_file

# Import texttrace core
import texttrace

app = Flask(__name__)

# ─── Storage ───────────────────────────────────────────────────────────────────

HISTORY_DIR = Path(__file__).parent / "data" / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# Active search sessions
SESSIONS = {}


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    """Start a new texttrace search. Returns session_id for SSE streaming."""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    source_text = data.get("text", "").strip()
    source_url = data.get("url", "").strip()
    threshold = float(data.get("threshold", 50))
    tier = data.get("tier", "all")
    engines = data.get("engines", "duckduckgo,bing").split(",")
    engines = [e.strip() for e in engines if e.strip()]
    if "all" in engines:
        engines = ["duckduckgo", "bing", "yandex", "google"]
    max_results = int(data.get("max_results", 15))
    extract_content = data.get("extract_content", True)
    site = data.get("site", "").strip() or None
    exclude = data.get("exclude", "").strip() or None
    tor = data.get("tor", False)
    proxy = data.get("proxy", "").strip() or None
    stealth = data.get("stealth", False)
    aggressive = data.get("aggressive", False)
    check_archives = data.get("check_archives", True)
    check_paste = data.get("check_paste", True)
    check_google = data.get("check_google", True)
    chain = data.get("chain", False)
    chain_depth = int(data.get("chain_depth", 1))
    github_token = data.get("github_token", "").strip() or None

    if not source_text and not source_url:
        return jsonify({"error": "Either text or url is required"}), 400

    session_id = str(uuid.uuid4())[:8]
    msg_queue = queue.Queue()
    SESSIONS[session_id] = {
        "queue": msg_queue,
        "report": None,
        "status": "running",
        "started_at": datetime.now().isoformat(),
    }

    def progress_callback(msg):
        msg_queue.put(msg)

    def run_search():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report = loop.run_until_complete(
                texttrace.run_texttrace(
                    source_text=source_text,
                    source_url=source_url if source_url else None,
                    threshold=threshold,
                    tier=tier,
                    engines=engines,
                    max_results=max_results,
                    extract_content=extract_content,
                    verbose=False,
                    progress_callback=progress_callback,
                    site=site,
                    exclude=exclude,
                    tor=tor,
                    proxy=proxy,
                    stealth=stealth,
                    aggressive=aggressive,
                    check_archives=check_archives,
                    check_paste_sites=check_paste,
                    check_google=check_google,
                    chain_mode=chain,
                    chain_depth=chain_depth,
                    github_token=github_token,
                )
            )
            SESSIONS[session_id]["report"] = report
            SESSIONS[session_id]["status"] = "completed"

            if "error" not in report:
                save_history(session_id, report)

            msg_queue.put({"type": "complete", "report": report})
        except Exception as e:
            SESSIONS[session_id]["status"] = "error"
            msg_queue.put({"type": "error", "message": str(e)})
        finally:
            loop.close()

    thread = threading.Thread(target=run_search, daemon=True)
    thread.start()

    return jsonify({"session_id": session_id})


@app.route("/api/progress/<session_id>")
def api_progress(session_id):
    """SSE stream for real-time progress updates."""
    def stream():
        session = SESSIONS.get(session_id)
        if not session:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid session'})}\n\n"
            return

        msg_queue = session["queue"]

        while True:
            try:
                msg = msg_queue.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"

                if msg.get("type") in ("complete", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

                if session["status"] in ("completed", "error"):
                    if session["report"]:
                        yield f"data: {json.dumps({'type': 'complete', 'report': session['report']})}\n\n"
                    break

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/history")
def api_history():
    """Get list of past searches."""
    history = []
    for f in sorted(HISTORY_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f) as fh:
                data = json.load(fh)
                meta = data.get("metadata", {})
                stats = data.get("stats", {})
                id_graph = data.get("identity_graph", {})
                history.append({
                    "id": f.stem,
                    "timestamp": meta.get("timestamp", ""),
                    "source_preview": meta.get("source_text_preview", "")[:100],
                    "matches": stats.get("matches_found", 0),
                    "results_scanned": stats.get("results_scanned", 0),
                    "elapsed": meta.get("elapsed_seconds", 0),
                    "platforms": stats.get("platforms_matched", []),
                    "confidence": stats.get("confidence_levels", {}),
                    "identity_links": len(id_graph.get("links", [])),
                })
        except Exception:
            continue

    return jsonify({"history": history[:50]})


@app.route("/api/history/<search_id>")
def api_history_detail(search_id):
    """Get full report for a past search."""
    filepath = HISTORY_DIR / f"{search_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404

    with open(filepath) as f:
        return jsonify(json.load(f))


@app.route("/api/history/<search_id>/download")
def api_history_download(search_id):
    """Download a report as JSON file."""
    filepath = HISTORY_DIR / f"{search_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=f"texttrace-report-{search_id}.json",
        mimetype="application/json",
    )


@app.route("/api/history/<search_id>/pdf")
def api_history_pdf(search_id):
    """Generate and download a PDF report."""
    filepath = HISTORY_DIR / f"{search_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Not found"}), 404

    with open(filepath) as f:
        report = json.load(f)

    pdf_path = HISTORY_DIR / f"texttrace-report-{search_id}.pdf"
    texttrace.generate_pdf_report(report, str(pdf_path))

    if pdf_path.exists():
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"texttrace-report-{search_id}.pdf",
            mimetype="application/pdf",
        )
    else:
        return jsonify({"error": "PDF generation failed — is fpdf2 installed?"}), 500


@app.route("/api/health")
def api_health():
    """Health check with feature flags."""
    return jsonify({
        "status": "ok",
        "texttrace_version": "2.0",
        "rapidfuzz": texttrace.HAS_RAPIDFUZZ,
        "sklearn": texttrace.HAS_SKLEARN,
        "fpdf": texttrace.HAS_FPDF,
        "curl_cffi": texttrace.HAS_CURL_CFFI,
        "active_sessions": len([s for s in SESSIONS.values() if s["status"] == "running"]),
        "platforms": len(texttrace.PLATFORM_PATTERNS),
    })


# ─── Helpers ───────────────────────────────────────────────────────────────────

def save_history(session_id, report):
    """Save report to history directory."""
    filepath = HISTORY_DIR / f"{session_id}.json"
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, default=str)


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TextTrace Web Dashboard v2 — Local web UI for TextTrace OSINT tool",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    print(f"\n  ╔══════════════════════════════════════════════════╗")
    print(f"  ║  🔍 TextTrace Web Dashboard v2                    ║")
    print(f"  ╠══════════════════════════════════════════════════╣")
    print(f"  ║  URL: http://{args.host}:{args.port:<32} ║" if len(f"http://{args.host}:{args.port}") <= 34 else f"  ║  URL: http://{args.host}:{args.port:<34}║")
    print(f"  ║  Mode: {'debug' if args.debug else 'production':<37} ║")
    print(f"  ╚══════════════════════════════════════════════════╝\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
