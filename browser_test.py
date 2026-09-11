import sys
import markdown
from playwright.sync_api import sync_playwright
import google.generativeai as genai

# 1. Handle CLI Arguments via sys.argv
if len(sys.argv) > 1:
    # Joins all arguments after the script name into one search query
    query = " ".join(sys.argv[1:])
else:
    # Default fallback if no arguments are provided
    query = "artificial intelligence latest research"

print(f"Target Research Query: '{query}'\n")

# 2. Configure Gemini API
genai.configure(api_key="AQ.Ab8RN6LQ_D-ToDy3yvYKgqhwXyy9s1Z1w3abAX4qVe76QyjC8Q")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    # 3. Perform DuckDuckGo Search
    page.goto("https://duckduckgo.com/", wait_until="domcontentloaded", timeout=60000)
    print("DuckDuckGo opened...")

    search_box = page.locator("#searchbox_input")
    if search_box.count() == 0:
        search_box = page.get_by_role("combobox")

    search_box.fill(query)
    search_box.press("Enter")
    print("Search submitted...")

    # 4. Wait for and collect top 5 result links
    page.wait_for_selector("article[data-testid='result']", timeout=15000)
    result_elements = page.locator("article[data-testid='result'] h2 a").all()

    targets = []
    for el in result_elements[:5]:
        href = el.get_attribute("href")
        title = el.inner_text()
        if href and href.startswith("http"):
            targets.append({"title": title, "url": href})

    print(f"Collected {len(targets)} articles. Starting extraction...\n")

    # 5. Extract article body text
    notes_vault = []
    reader_tab = browser.new_page()

    for idx, item in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] Reading: {item['title'][:50]}...")
        try:
            reader_tab.goto(item["url"], wait_until="domcontentloaded", timeout=25000)
            paragraphs = reader_tab.locator("article p, main p, .post-content p, p").all_inner_texts()
            article_body = " ".join([p.strip() for p in paragraphs if len(p.strip()) > 50])

            if article_body:
                notes_vault.append({
                    "title": item["title"],
                    "url": item["url"],
                    "content": article_body[:3000]
                })
        except Exception as e:
            print(f"   Skipped ({e.__class__.__name__})")

    reader_tab.close()
    browser.close()

# 6. Format notes for Gemini synthesis
raw_research = ""
for i, note in enumerate(notes_vault, 1):
    raw_research += f"\nSource {i}: {note['title']} ({note['url']})\n{note['content']}\n---\n"

print("\nSynthesizing research with Gemini...")

prompt = f"""
You are an expert research analyst. The user requested deep research on the topic: "{query}".

Analyze the following gathered notes from recent web findings:
{raw_research}

Generate a comprehensive report containing:
1. **Topic Overview & Executive Summary**: High-level synthesis of what is happening in "{query}".
2. **Key Findings & Themes**: Notable breakthroughs, technical details, or recurring facts across the sources.
3. **Source Reliability & Trust Check**: Quick appraisal of the trustworthiness and origin of the cited sources.
"""

model = genai.GenerativeModel("gemini-flash-latest")
response = model.generate_content(prompt)
report_markdown = response.text

# 7. Save Markdown Report
with open("final_research_report.md", "w", encoding="utf-8") as f:
    f.write(report_markdown)
print("Saved `final_research_report.md`")

# 8. Convert to Styled HTML
html_body = markdown.markdown(report_markdown, extensions=["tables", "fenced_code"])
styled_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Research: {query}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            max-width: 850px;
            margin: 40px auto;
            padding: 0 20px;
            color: #24292e;
        }}
        h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
        code {{ background-color: #f6f8fa; padding: 0.2em 0.4em; border-radius: 3px; }}
        blockquote {{ border-left: 4px solid #dfe2e5; margin: 0; padding-left: 1em; color: #6a737d; }}
    </style>
</head>
<body>
    <h1>Research Report: {query.title()}</h1>
    {html_body}
</body>
</html>"""

with open("final_research_report.html", "w", encoding="utf-8") as f:
    f.write(styled_html)
print("Saved `final_research_report.html`")

# 9. Render PDF via Headless Chromium
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    pdf_page = browser.new_page()
    pdf_page.set_content(styled_html, wait_until="load")
    pdf_page.pdf(
        path="final_research_report.pdf",
        format="A4",
        margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
    )
    browser.close()

print("Saved `final_research_report.pdf` successfully!")