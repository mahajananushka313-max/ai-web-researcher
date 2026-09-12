import os
import sys
import time
import streamlit as st
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError

# --- Page Setup ---
st.set_page_config(
    page_title="Web Researcher AI",
    page_icon="🔬",
    layout="wide"
)

# --- API Key Initialization ---
# Prioritizes Streamlit Secrets (for Cloud), falls back to os.environ (local)
api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))

if not api_key:
    st.error("API Key not found. Please set `GEMINI_API_KEY` in `.streamlit/secrets.toml` or Streamlit Cloud Secrets.")
    st.stop()

genai.configure(api_key=api_key)

# --- Robust Synthesis Function with Exponential Backoff & Fallback ---
PRIMARY_MODEL = "gemini-1.5-flash"  # standard stable tier
FALLBACK_MODEL = "gemini-1.5-pro"

def generate_synthesis_with_retry(prompt: str, max_retries: int = 4) -> str:
    """
    Calls Gemini API with automatic exponential backoff to handle HTTP 429
    and switches to a fallback model if the primary model's quota is exhausted.
    """
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]

    for model_name in models_to_try:
        model = genai.GenerativeModel(model_name)
        for attempt in range(max_retries):
            try:
                with st.spinner(f"Synthesizing with {model_name}..."):
                    response = model.generate_content(prompt)
                    return response.text
            except ResourceExhausted as e:
                # Calculate backoff delay: 10s, 20s, 40s...
                wait_time = 10 * (2 ** attempt)
                st.warning(f"Quota reached on {model_name} (HTTP 429). Retrying in {wait_time} seconds (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            except GoogleAPIError as e:
                st.error(f"Google API error on {model_name}: {str(e)}")
                break  # Try the next model
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")
                return f"Synthesis failed: {str(e)}"
    
    return "Synthesis failed: All quota retries and fallback models were exhausted. Please check your AI Studio quota."

# --- Main App Interface ---
st.title("🔬 Web Researcher AI")
st.write("Autonomous search and multi-step research synthesis.")

user_query = st.text_input("Enter research topic or prompt:", placeholder="e.g., Comparative analysis of agentic workflows")

if st.button("Start Research", type="primary"):
    if not user_query.strip():
        st.warning("Please provide a search topic.")
    else:
        with st.container():
            st.info("Gathering and synthesizing research data...")
            
            # Formulate the prompt for your research report
            synthesis_prompt = f"""
            You are an expert research analyst. Produce a structured, comprehensive synthesis report on the following query:
            
            Query: {user_query}
            
            Format the response clearly with an Executive Summary, Key Findings, Comparative Breakdown, and Conclusion.
            """
            
            report = generate_synthesis_with_retry(synthesis_prompt)
            
            st.subheader("Research Report")
            st.markdown(report)
            
            # Download options
            st.download_button(
                label="Download Report (.md)",
                data=report,
                file_name="final_research_report.md",
                mime="text/markdown"
            )

# --- Programmatic Entrypoint (Run without `streamlit run`) ---
if __name__ == "__main__":
    if not os.environ.get("STREAMLIT_RUN_DIRECTLY"):
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())