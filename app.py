# streamlit_app.py
# -------------------------------------------
# Small Business Promotional Email Generator
#
# Install requirements:
#   pip install streamlit openai requests beautifulsoup4
#
# Run:
#   streamlit run streamlit_app.py
# -------------------------------------------

import re
from urllib.parse import urlparse

import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI


SYSTEM_PROMPT = (
    "You are a Senior CRM Professional with 10+ years of experience in high-end marketing. "
    "You write concise, persuasive, and professional email copy. "
    "You never use cheesy or spammy language. "
    "Use the provided business details to tailor the tone."
)


def normalize_url(url: str) -> str:
    """Ensure URL has a scheme and is reasonably valid."""
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return url


def scrape_website_text(url: str, timeout: int = 12) -> str:
    """
    Scrape visible text from a website using requests + BeautifulSoup.
    Raises an exception on failure so caller can handle gracefully.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "noscript", "svg", "img", "video", "audio", "canvas", "iframe"]):
        tag.decompose()

    # Prefer main content if present
    main = soup.find("main")
    content_root = main if main else soup.body if soup.body else soup

    text = content_root.get_text(separator="\n")
    # Clean up whitespace
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    cleaned = "\n".join(lines)

    # Light de-dup and length control
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def build_user_prompt(business_text: str, promo_details: str) -> str:
    return (
        "BUSINESS DETAILS (from website and/or user):\n"
        f"{business_text}\n\n"
        "PROMOTION DETAILS:\n"
        f"{promo_details}\n\n"
        "TASK:\n"
        "Write one promotional email suitable for a small business to send to customers.\n"
        "Requirements:\n"
        "- Subject line + email body.\n"
        "- Clear offer and timeframe.\n"
        "- Professional, concise, persuasive.\n"
        "- No spammy words (e.g., 'ACT NOW!!!', 'FREE MONEY', 'guaranteed').\n"
        "- Include a clear call-to-action.\n"
        "- If the business type is unclear, keep it broadly applicable.\n"
    )


def call_openai(api_key: str, business_text: str, promo_details: str) -> str:
    client = OpenAI(api_key=api_key)

    # Keep the prompt within a reasonable size for reliability
    max_chars = 7000
    business_text = (business_text or "").strip()
    promo_details = (promo_details or "").strip()
    if len(business_text) > max_chars:
        business_text = business_text[:max_chars] + "\n...(truncated)..."

    user_prompt = build_user_prompt(business_text, promo_details)

    # Use Responses API (recommended in newer OpenAI SDKs)
    resp = client.responses.create(
        model="gpt-4o",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (resp.output_text or "").strip()


# ----------------------------
# Streamlit UI
# ----------------------------
st.set_page_config(page_title="Promotional Email Generator", page_icon="✉️", layout="centered")

st.title("✉️ Promotional Email Generator")
st.caption("Paste your business website URL and promotion details. The app will draft a professional email you can copy.")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("OpenAI API Key", type="password", help="Your key stays in your browser session.")
    if not api_key:
        st.warning("Please enter your OpenAI API Key to generate emails.")

st.subheader("Inputs")
website_url_raw = st.text_input("Business Website URL", placeholder="e.g., https://yourbusiness.com")
promo_details = st.text_area(
    "Promotion Details",
    placeholder="e.g., 50% off in September for all new customers. Use code SEPT50 at checkout.",
    height=140,
)

# Always show a manual fallback (only required if scraping fails)
manual_description = st.text_area(
    "Business Description (fallback if scraping fails)",
    placeholder="If the website can't be scraped, briefly describe your business here (what you sell, audience, tone).",
    height=120,
)

generate = st.button("Generate Promotional Email", type="primary")

st.divider()

if generate:
    if not api_key:
        st.error("Missing API Key. Add your OpenAI API Key in the sidebar, then try again.")
        st.stop()

    website_url = normalize_url(website_url_raw)
    if not website_url:
        st.error("Please enter a valid Business Website URL (include a domain like example.com).")
        st.stop()

    if not promo_details.strip():
        st.error("Please enter Promotion Details.")
        st.stop()

    business_text = ""
    scrape_failed = False

    with st.spinner("Scraping website text..."):
        try:
            scraped = scrape_website_text(website_url)
            # If it's suspiciously short, treat as failure for better UX
            if len(scraped) < 300:
                scrape_failed = True
            else:
                business_text = scraped
        except Exception:
            scrape_failed = True

    if scrape_failed:
        st.warning(
            "I couldn't scrape enough text from that website (this can happen due to site protections or dynamic pages). "
            "Please use the 'Business Description' box above to describe your business, then click Generate again."
        )
        if not manual_description.strip():
            st.stop()
        business_text = manual_description.strip()

    with st.spinner("Generating email with OpenAI..."):
        try:
            email_text = call_openai(api_key, business_text, promo_details)
        except Exception as e:
            st.error(f"OpenAI request failed: {e}")
            st.stop()

    if not email_text:
        st.error("No email text was returned. Please try again (or simplify your promotion details).")
        st.stop()

    st.success("Email generated!")
    st.text_area("Generated Email (copy this)", value=email_text, height=320)

    st.download_button(
        label="Download as .txt",
        data=email_text,
        file_name="promotional_email.txt",
        mime="text/plain",
    )
else:
    st.info("Enter your details above, then click **Generate Promotional Email**.")
