import os
import sys
import time
import smtplib
from datetime import datetime
from email.message import EmailMessage
import feedparser
import requests
from xhtml2pdf import pisa
import google.generativeai as genai

# ----------------- Environment Configuration -----------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER)

TODAY_STR = datetime.now().strftime("%d %B %Y")
PDF_FILENAME = f"UP_TGT_Hindi_Notes_{datetime.now().strftime('%Y%m%d')}.pdf"
FONT_FILENAME = "NotoSansDevanagari-Regular.ttf"

# ----------------- Gemini Model Config -----------------
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3-flash-preview"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 20


def download_hindi_font():
    """Downloads a Devanagari TTF font so xhtml2pdf can render Hindi characters."""
    if not os.path.exists(FONT_FILENAME):
        font_url = "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
        response = requests.get(font_url)
        with open(FONT_FILENAME, "wb") as f:
            f.write(response.content)


def fetch_combined_feeds() -> str:
    """Scrapes raw data from both The Hindu and PIB."""
    hindu_urls = [
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://www.thehindu.com/opinion/editorial/feeder/default.rss"
    ]
    pib_urls = [
        "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"
    ]

    raw_articles = []

    for url in hindu_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:6]:
            raw_articles.append(f"[The Hindu] Title: {entry.title}\nSummary: {entry.get('summary', '')}\n")

    for url in pib_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            raw_articles.append(f"[PIB] Title: {entry.title}\nSummary: {entry.get('summary', '')}\n")

    return "\n---\n".join(raw_articles)


def generate_structured_notes(raw_content: str) -> str:
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is missing. Check your GitHub Secrets.")
        sys.exit(1)

    genai.configure(api_key=GEMINI_API_KEY)

    prompt = f"""
You are an expert UP TGT (Trained Graduate Teacher) exam mentor.
Analyze the following news items. Some are from The Hindu, and some are from PIB.
Compile a comprehensive daily study digest for {TODAY_STR} targeting the UP TGT exam.

CRITICAL REQUIREMENT 1: The entire output MUST be strictly in HINDI (Devanagari script).
CRITICAL REQUIREMENT 2: You MUST separate the content into two distinct sections: one for 'द हिंदू' and one for 'PIB'.

Format ONLY the content inside clean HTML using these exact rules:

<div class="section-pill">स्रोत: द हिंदू (The Hindu)</div>
  <div class="news-title">[Topic Headline in Hindi]</div>
  <ul>
    <li><strong>चर्चा में क्यों:</strong> [Summary in Hindi]</li>
    <li><strong>मुख्य बिंदु:</strong> [Key points in Hindi]</li>
    <li><strong>TGT परीक्षा दृष्टि:</strong> [Facts in Hindi]</li>
  </ul>

<div class="section-pill">स्रोत: पत्र सूचना कार्यालय (PIB)</div>
  <div class="news-title">[Topic Headline in Hindi]</div>
  <ul>
    <li><strong>चर्चा में क्यों:</strong> [Summary in Hindi]</li>
    <li><strong>मुख्य बिंदु:</strong> [Key points in Hindi]</li>
    <li><strong>TGT परीक्षा दृष्टि:</strong> [Facts in Hindi]</li>
  </ul>

Do not include <html>, <head>, or <body> tags. Output only the inner HTML.
Raw News:
{raw_content}
"""

    def try_generate(model_name: str):
        model = genai.GenerativeModel(model_name)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    wait = RETRY_DELAY_SECONDS * attempt
                    print(f"[{model_name}] Attempt {attempt}/{MAX_RETRIES} failed "
                          f"({err_str[:120]}...). Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"ERROR calling Gemini API ({model_name}): {err_str}")
                    return None
        return None

    print(f"Trying primary model: {PRIMARY_MODEL}")
    result = try_generate(PRIMARY_MODEL)

    if result is None:
        print(f"Primary model failed after {MAX_RETRIES} attempts. "
              f"Falling back to {FALLBACK_MODEL}...")
        result = try_generate(FALLBACK_MODEL)

    if result is None:
        print("ERROR: Both primary and fallback models failed.")
        sys.exit(1)

    return result


def build_full_html(body_content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <style>
    @font-face {{
        font-family: 'NotoDevanagari';
        src: url('{FONT_FILENAME}');
    }}
    @page {{ size: a4 portrait; margin: 1.5cm; }}
    body {{ font-family: 'NotoDevanagari', Helvetica, sans-serif; color: #1a1a1a; line-height: 1.5; font-size: 11pt; }}
    .header {{ border-bottom: 2px solid #00563F; padding-bottom: 5px; margin-bottom: 15px; }}
    .main-title {{ color: #00563F; font-size: 18pt; font-weight: bold; }}
    .subtext {{ font-size: 9pt; color: #555; margin-top: 4px; }}
    .section-pill {{ background-color: #00563F; color: #ffffff; font-size: 12pt; font-weight: bold; padding: 6px 10px; margin-top: 20px; margin-bottom: 10px; }}
    .news-title {{ font-size: 12pt; font-weight: bold; color: #111; margin-top: 10px; margin-bottom: 4px; }}
    ul {{ margin-top: 4px; margin-bottom: 10px; padding-left: 20px; }}
    li {{ font-size: 10pt; margin-bottom: 4px; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="main-title">UP TGT दैनिक करेंट अफेयर्स (The Hindu + PIB)</div>
    <div class="subtext">{TODAY_STR} • टीजीटी परीक्षा के लिए हिंदी में संकलित</div>
  </div>
  {body_content}
</body>
</html>"""


def generate_pdf(html_content: str, output_path: str):
    with open(output_path, "w+b") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file, encoding='utf-8')
        if pisa_status.err:
            raise Exception("PDF generation error")


def send_gmail(html_content: str, pdf_path: str):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD):
        print("ERROR: Gmail credentials missing. Check your GitHub Secrets.")
        sys.exit(1)

    msg = EmailMessage()
    msg["Subject"] = f"UP TGT दैनिक नोट्स - The Hindu & PIB ({TODAY_STR})"
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    msg.set_content("कृपया आज के UP TGT करेंट अफेयर्स पढ़ने के लिए HTML व्यू इनेबल करें या संलग्न PDF देखें।")
    msg.add_alternative(html_content, subtype="html")

    with open(pdf_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=PDF_FILENAME)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)
    print("Email sent successfully.")


def main():
    print("Downloading Hindi Font...")
    download_hindi_font()

    print("Fetching combined Hindu and PIB content...")
    raw_content = fetch_combined_feeds()

    print("Generating Hindi structured TGT notes via Gemini...")
    notes_body = generate_structured_notes(raw_content)
    full_html = build_full_html(notes_body)

    print("Generating PDF via xhtml2pdf...")
    generate_pdf(full_html, PDF_FILENAME)

    print("Dispatching via Gmail...")
    send_gmail(full_html, PDF_FILENAME)

    if os.path.exists(PDF_FILENAME):
        os.remove(PDF_FILENAME)
    print("Execution completed successfully.")


if __name__ == "__main__":
    main()