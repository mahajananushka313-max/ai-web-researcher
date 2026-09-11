import os
import sys
import subprocess
import urllib.parse
import urllib.request
import json
import streamlit as st
import markdown
from playwright.sync_api import sync_playwright
from duckduckgo_search import DDGS
import google.generativeai as genai

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

# Sidebar settings
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input(
        "Gemini API Key", 
        value="AQ.Ab8RN6LQ_D-ToDy3yvYKgqhwXyy9s1Z1w3abAX4qVe76QyjC8Q", 
        type="password"
    )
    article_limit = st.slider("Sources to Scrape", min_value=3, max_value=8, value=5)

# Input topic
query = st.text_input("Enter a research topic:", placeholder="e.g., data science trends 2026")
run_button = st.button("Run Deep Research", type="primary", use_container_width=True)

def perform_research(topic, num_articles, key):
    genai.configure(api_key=key)
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
    
    # 3. Gemini Synthesis
    status_text.info("Synthesizing grounded research brief with Gemini...")
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
    
    model = genai.GenerativeModel("gemini-flash-latest")
    response = model.generate_content(prompt)
    report_md = response.text
    
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