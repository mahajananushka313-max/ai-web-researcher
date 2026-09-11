import os
import sys
import time
import subprocess
import urllib.parse
import urllib.request
import json
import streamlit as st
import markdown
from playwright.sync_api import sync_playwright
from duckduckgo_search import DDGS

# Auto-download Playwright Chromium binary on cloud deployment
@st.cache_resource
def ensure_playwright_browser():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Browser installation failed: {e}")

ensure_playwright_browser()

# Page Configuration
st.set_page_config(page_title="Autonomous AI Web Researcher", page_icon="🔍", layout="wide")

st.title("🔍 Autonomous AI Web Researcher")
st.caption("Live Search Indexing · Dynamic DOM Extraction · Gemini Synthesis")

# Retrieve API key automatically from Streamlit Secrets or environment
default_key = ""
if "GEMINI_API_KEY" in st.secrets:
    default_key = st.secrets["GEMINI_API_KEY"]
elif os.getenv("GEMINI_API_KEY"):
    default_key = os.getenv("GEMINI_API_KEY")

# Sidebar settings
with st.sidebar:
    st.header("Configuration")
    if default_key:
        st.success("API Key loaded from environment secrets")
        api_key = default_key
    else:
        api_key = st.text_input(
            "Gemini API Key", 
            placeholder="Paste your Gemini key here...", 
            type="password"
        )
    article_limit = st.slider("Sources to Scrape", min_value=3, max_value=8, value=5)

# Input topic
query = st.text_input("Enter a research topic:", placeholder="e.g., data science trends 2026")
run_button = st.button("Run Deep Research", type="primary", use_container_width=True)

def call_gemini_with_fallback(prompt, key, status_widget):
    encoded_key = urllib.parse.quote(key)
    candidate_models = [
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]
    
    last_err = None
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    for model_name in candidate_models:
        status_widget.info(f"Synthesizing research brief with {model_name}...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={encoded_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result_json = json.loads(resp.read().decode("utf-8"))
                    return result_json["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as http_err:
                err_msg = http_err.read().decode("utf-8")
                last_err = f"({http_err.code}): {err_msg}"
                if http_err.code in (503, 429):
                    time.sleep(2)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                break

    raise RuntimeError(f"All model synthesis attempts failed: {last_err}")

def perform_research(topic, num_articles, key):
    key = key.strip()
    status_text = st.empty()
    status_text.info(f"Querying search index for: '{topic}'...")
    
    # 1. Fetch search results with backend fallback
    targets = []
    for backend_mode in ["api", "html", "lite"]:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(topic, max_results=num_articles * 2, backend=backend_mode))
                for item in results:
                    href = item.get("href")
                    title = item.get("title")
                    if href and href.startswith("http") and not any(skip in href for skip in ["duckduckgo.com", "bing.com"]):
                        if not any(t["url"] == href for t in targets):
                            targets.append({"title": title if title else href, "url": href})
                    if len(targets) >= num_articles:
                        break
            if targets:
                break
        except Exception:
            continue

    # Fallback to direct encyclopedic search if engine blocks cloud hosting
    if not targets:
        try:
            wiki_api = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(topic)}&limit={num_articles}&namespace=0&format=json"
            req = urllib.request.Request(wiki_api, headers={'User-Agent': 'AutonomousResearcher/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                titles, urls = data[1], data[3]
                for t, u in zip(titles, urls):
                    targets.append({"title": t, "url": u})
        except Exception:
            pass

    if not targets:
        raise RuntimeError("Search providers are currently throttling cloud requests. Please rephrase or try another topic.")

    # 2. Extract article text via Playwright
    notes_vault = []
    progress_bar = st.progress(0)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        reader_tab = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        for idx, item in enumerate(targets, 1):
            status_text.info(f"Reading source ({idx}/{len(targets)}): {item['title'][:45]}...")
            try:
                reader_tab.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
                paragraphs = reader_tab.locator("article p, main p, .post-content p, p").all_inner_texts()
                body = " ".join([p.strip() for p in paragraphs if len(p.strip()) > 50])
                if body:
                    notes_vault.append({"title": item["title"], "url": item["url"], "content": body[:3000]})
            except Exception:
                pass
            progress_bar.progress(idx / len(targets))
            
        reader_tab.close()
        browser.close()
    
    # 3. Gemini Synthesis with Resilient Fallback
    raw_research = ""
    for i, note in enumerate(notes_vault, 1):
        raw_research += f"\nSource {i}: {note['title']} ({note['url']})\n{note['content']}\n---\n"
        
    prompt = f"""
    You are an expert research analyst. Deep research requested for: "{topic}".
    
    Analyze the following gathered notes from recent web findings:
    {raw_research}
    
    Generate a comprehensive research brief containing:
    1. **Topic Overview & Executive Summary**
    2. **Key Findings & Cross-Comparison**
    3. **Source Reliability & Trust Check**
    """

    report_md = call_gemini_with_fallback(prompt, key, status_text)
    
    # 4. Generate Styled HTML & PDF
    html_body = markdown.markdown(report_md, extensions=["tables", "fenced_code"])
    styled_html = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: auto; padding: 20px; color: #222; }}
            h1, h2, h3 {{ border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
            blockquote {{ border-left: 3px solid #ccc; padding-left: 10px; color: #555; }}
        </style>
    </head>
    <body>
        <h1>Research Report: {topic.title()}</h1>
        {html_body}
    </body>
    </html>"""
    
    pdf_path = "final_research_report.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        pdf_page = browser.new_page()
        pdf_page.set_content(styled_html, wait_until="load")
        pdf_page.pdf(path=pdf_path, format="A4", margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"})
        browser.close()
        
    status_text.empty()
    progress_bar.empty()
    return report_md, pdf_path

if run_button:
    if not query.strip():
        st.warning("Please provide a search topic.")
    elif not api_key.strip():
        st.warning("Please configure your Gemini API key in Streamlit Secrets or sidebar.")
    else:
        with st.spinner("Executing autonomous research pipeline..."):
            try:
                markdown_report, pdf_file = perform_research(query, article_limit, api_key)
                st.success("Research completed!")
                
                with open(pdf_file, "rb") as f:
                    pdf_bytes = f.read()
                    
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.download_button(
                        label="📄 Download PDF Report",
                        data=pdf_bytes,
                        file_name=f"research_report_{query[:15].strip().replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                st.markdown("---")
                st.markdown(markdown_report)
            except Exception as e:
                st.error(f"Error during execution: {str(e)}")