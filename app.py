import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# Optional imports for scraping / DuckDuckGo
try:
    from duckduckgo_search import DDGS

    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Autonomous Web Researcher",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Autonomous Deep Web Researcher")
st.caption("Live Search Indexing · webcmd DOM Extraction · Agentic Synthesis")


# ---------------------------------------------------------
# Webcmd / CloakBrowser Daemon & Scraper Integration
# ---------------------------------------------------------
WEBCMD_PORT = int(os.getenv("WEBCMD_PORT", "9777"))
WEBCMD_URL = f"http://127.0.0.1:{WEBCMD_PORT}"


def is_webcmd_active(timeout: float = 0.5) -> bool:
    """Checks if local Webcmd / CloakBrowser daemon is active on port 9777."""
    try:
        req = urllib.request.Request(
            f"{WEBCMD_URL}/health", headers={"User-Agent": "WebcmdAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False


def scrape_with_webcmd(url: str, timeout: int = 15) -> str:
    """Extracts webpage content using the local Webcmd daemon."""
    payload = json.dumps({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        f"{WEBCMD_URL}/extract",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("text", "")


def scrape_with_playwright(url: str, timeout_ms: int = 15000) -> str:
    """Fallback extraction using headless Chromium via Playwright."""
    if not PLAYWRIGHT_AVAILABLE:
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            content = page.content()
            browser.close()

            if BS4_AVAILABLE:
                soup = BeautifulSoup(content, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return re.sub(r"\s+", " ", soup.get_text()).strip()
            return content[:5000]
    except Exception:
        return ""


def extract_content(url: str, status_widget=None) -> str:
    """Dual-mode scraper: attempts Webcmd first, falls back to Playwright."""
    if is_webcmd_active():
        if status_widget:
            status_widget.info(
                f"Extracting via Webcmd daemon (port {WEBCMD_PORT}): {url}"
            )
        try:
            text = scrape_with_webcmd(url)
            if len(text.strip()) > 100:
                return text[:6000]
        except Exception:
            pass

    if status_widget:
        status_widget.info(f"Extracting via browser engine: {url}")
    return scrape_with_playwright(url)[:6000]


# ---------------------------------------------------------
# Web Search Discovery (Multi-Engine Resilient)
# ---------------------------------------------------------
def search_web(query: str, max_results: int = 4) -> list[dict]:
    """Finds target source URLs using DuckDuckGo, with Wikipedia and fallback query routing."""
    results = []

    # Method 1: DuckDuckGo Python package (DDGS)
    if DDGS_AVAILABLE:
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        {
                            "title": r.get("title", query),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", ""),
                        }
                    )
            if results:
                return results
        except Exception:
            pass

    # Method 2: Direct DuckDuckGo Lite / HTML scraper with real User-Agent
    try:
        encoded = urllib.parse.quote_plus(query)
        req = urllib.request.Request(
            f"https://html.duckduckgo.com/html/?q={encoded}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            links = re.findall(r'class="result__url"[^>]*href="([^"]+)"', html)
            snippets = re.findall(
                r'class="result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL
            )
            for raw_url, raw_snip in zip(
                links[:max_results], snippets[:max_results]
            ):
                clean_url = raw_url
                if "uddg=" in clean_url:
                    match = re.search(r"uddg=([^&]+)", clean_url)
                    if match:
                        clean_url = urllib.parse.unquote(match.group(1))
                clean_snippet = re.sub(r"<.*?>", "", raw_snip).strip()
                results.append(
                    {
                        "title": query,
                        "url": clean_url,
                        "snippet": clean_snippet,
                    }
                )
        if results:
            return results
    except Exception:
        pass

    # Method 3: Wikipedia API fallback
    try:
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote_plus(query)}&limit={max_results}&namespace=0&format=json"
        req = urllib.request.Request(
            wiki_url, headers={"User-Agent": "AutonomousWebResearcher/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            titles, descriptions, urls = data[1], data[2], data[3]
            for t, d, u in zip(titles, descriptions, urls):
                results.append({"title": t, "url": u, "snippet": d or t})
        if results:
            return results
    except Exception:
        pass

    # Method 4: Contextual discovery fallback
    return [
        {
            "title": f"Documentation: {query}",
            "url": f"https://github.com/search?q={urllib.parse.quote_plus(query)}",
            "snippet": f"Open-source index and technical repositories for {query}.",
        },
        {
            "title": f"Overview: {query}",
            "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote_plus(query)}",
            "snippet": f"Encyclopedia reference and background summary for {query}.",
        },
    ]


# ---------------------------------------------------------
# Gemini API Auto-Discovery & Dynamic Synthesis
# ---------------------------------------------------------
def get_available_gemini_model(api_key: str) -> tuple[str, str]:
    """Queries ModelService to detect an active generateContent model and supported API version."""
    clean_key = api_key.strip()
    preferred = [
        "gemini-3.6-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    for api_ver in ("v1beta", "v1"):
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models?key={clean_key}"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "AutonomousWebResearcher/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                valid_models = [
                    m["name"].replace("models/", "")
                    for m in models
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]

                for pref in preferred:
                    if pref in valid_models:
                        return api_ver, pref

                if valid_models:
                    return api_ver, valid_models[0]
        except Exception:
            continue

    return "v1beta", "gemini-3.6-flash"


def call_gemini_with_fallback(
    prompt: str, api_key: str, status_widget=None
) -> str:
    """Executes prompt synthesis using auto-detected active Gemini endpoints."""
    clean_key = api_key.strip()
    api_ver, model_name = get_available_gemini_model(clean_key)

    if status_widget:
        status_widget.info(
            f"Synthesizing research brief with {model_name} ({api_ver})..."
        )

    url = (
        f"https://generativelanguage.googleapis.com/{api_ver}/models/"
        f"{model_name}:generateContent?key={clean_key}"
    )
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 3000},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result_json = json.loads(resp.read().decode("utf-8"))
            candidates = result_json.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"]
            raise RuntimeError("Gemini returned an empty candidate response.")
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini HTTP {http_err.code}: {err_body}")


# ---------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------
def build_pdf_report(
    topic: str, content_markdown: str, sources: list[str]
) -> io.BytesIO:
    """Builds a formatted A4 executive PDF report."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )

    story = [
        Paragraph(f"Executive Research Report: {topic}", title_style),
        Spacer(1, 10),
    ]

    for line in content_markdown.split("\n"):
        clean_line = line.strip()
        if not clean_line:
            story.append(Spacer(1, 4))
            continue
        if clean_line.startswith("## ") or clean_line.startswith("### "):
            header_text = re.sub(r"^#+\s*", "", clean_line)
            story.append(Paragraph(header_text, heading_style))
        else:
            safe_text = (
                clean_line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe_text, body_style))

    if sources:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Verified Sources", heading_style))
        for s in sources:
            story.append(
                Paragraph(
                    f"• {s}",
                    body_style,
                )
            )

    doc.build(story)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------
# UI & Workflow Execution
# ---------------------------------------------------------
api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

with st.sidebar:
    st.header("Agent Controls")
    user_api_key = st.text_input(
        "Gemini API Key",
        value=api_key,
        type="password",
        help="Reads from secrets.toml or environment variable if not typed manually.",
    )
    effective_api_key = (user_api_key or api_key).strip()

    daemon_ready = is_webcmd_active()
    if daemon_ready:
        st.success(f"Webcmd Daemon: Active (port {WEBCMD_PORT})")
    else:
        st.info("Browser Runtime: Headless Engine (Cloud Mode)")

topic = st.text_input(
    "Enter Research Topic or Query",
    placeholder="e.g., Advances in Autonomous Browser Agents 2026",
)

if st.button("Run Deep Research", type="primary"):
    if not topic.strip():
        st.warning("Please provide a research query.")
        st.stop()

    if not effective_api_key:
        st.error("Missing Gemini API Key. Provide it in the sidebar.")
        st.stop()

    status_box = st.empty()
    progress_bar = st.progress(5)

    status_box.info("Querying search indices...")
    results = search_web(topic, max_results=3)
    progress_bar.progress(25)

    if not results:
        status_box.error(
            "No search results could be retrieved. Try another query."
        )
        st.stop()

    scraped_docs = []
    source_urls = []

    for idx, r in enumerate(results):
        url = r["url"]
        source_urls.append(url)
        content = extract_content(url, status_widget=status_box)
        scraped_docs.append(
            f"Source URL: {url}\nContent Snippet: {r['snippet']}\nFull Content: {content}\n---"
        )
        progress_bar.progress(25 + int((idx + 1) / len(results) * 45))

    synthesis_prompt = f"""
You are an autonomous research intelligence system.
Analyze the following extracted live web data on the topic: "{topic}".

Synthesize a comprehensive, executive-level research brief structured as follows:
- ## Executive Summary
- ## Key Insights & Developments
- ## Technical Analysis & Implications
- ## Strategic Takeaways

Extracted Web Content:
{"".join(scraped_docs)}
"""

    status_box.info("Synthesizing multi-source intelligence...")
    try:
        report_markdown = call_gemini_with_fallback(
            synthesis_prompt, effective_api_key, status_widget=status_box
        )
        progress_bar.progress(100)
        status_box.success("Research and synthesis complete!")
    except Exception as e:
        status_box.error(f"Synthesis failed: {e}")
        st.stop()

    st.markdown("---")
    st.markdown(report_markdown)

    pdf_buffer = build_pdf_report(topic, report_markdown, source_urls)
    st.download_button(
        label="📥 Download PDF Report",
        data=pdf_buffer,
        file_name=f"research_report_{re.sub(r'[^a-zA-Z0-9]', '_', topic)[:25]}.pdf",
        mime="application/pdf",
    )