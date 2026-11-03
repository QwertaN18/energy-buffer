import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_URL = "https://energy-ua.info/cherga"

QUEUES = [
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2",
    "6.1", "6.2"
]

HEADING = "Періоди відключень на сьогодні"
END_MARKERS = ["Черги відключень", "Допомогти проекту"]
PATTERN = re.compile(r"З\s*(\d{1,2}):(\d{2})\s+до\s+(\d{1,2}):(\d{2})", re.IGNORECASE)

def extract_outages(page_text: str):
    start_idx = page_text.lower().find(HEADING.lower())
    if start_idx < 0:
        return None

    after_heading = page_text[start_idx + len(HEADING):]
    end_idx = len(after_heading)
    for marker in END_MARKERS:
        m_idx = after_heading.lower().find(marker.lower())
        if 0 <= m_idx < end_idx:
            end_idx = m_idx

    section = after_heading[:end_idx]
    intervals = []

    for match in PATTERN.finditer(section):
        sh, sm, eh, em = map(int, match.groups())
        start = sh * 60 + sm
        end = eh * 60 + em
        if end <= start:
            end += 24 * 60
        intervals.append({"start": start, "end": end})

    intervals.sort(key=lambda x: x["start"])
    return intervals

def wait_for_cloudflare(page: ChromiumPage):
    for _ in range(15):
        title = page.title or ""
        if "Just a moment" not in title and "Attention Required" not in title:
            return True
        try:
            iframe = page.get_frame('@src^https://challenges.cloudflare.com')
            if iframe:
                cb = iframe.ele('tag:input', timeout=1)
                if cb:
                    cb.click()
        except Exception:
            pass
        time.sleep(2)
    return False

def main():
    kyiv_now = datetime.now(ZoneInfo("Europe/Kyiv"))
    result_queues = {}

    try:
        with open("schedule.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
            if old_data.get("date") == kyiv_now.strftime("%Y-%m-%d"):
                result_queues = old_data.get("queues", {})
    except Exception:
        pass

    co = ChromiumOptions()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=uk-UA')

    page = ChromiumPage(co)

    try:
        for q in QUEUES:
            url = f"{BASE_URL}/{q.replace('.', '-')}"
            try:
                page.get(url, timeout=25)
                wait_for_cloudflare(page)
                time.sleep(1)

                html = page.html
                soup = BeautifulSoup(html, "html.parser")
                page_title = soup.title.string.strip() if soup.title and soup.title.string else "No Title"
                body_text = soup.get_text(separator="\n")

                print(f"[{q}] URL: {url} | Title: {page_title}")

                parsed = extract_outages(body_text)
                if parsed is not None:
                    result_queues[q] = parsed
                    print(f"  -> [OK] Найдено отключений: {len(parsed)} -> {parsed}")
                else:
                    snippet = " ".join(body_text.split())[:200]
                    print(f"  -> [WARN] Заголовок '{HEADING}' не найден! Текст: {snippet}")
            except Exception as e:
                print(f"[{q}] ERROR: {e}")
    finally:
        page.quit()

    payload = {
        "updated_at": kyiv_now.strftime("%H:%M:%S"),
        "date": kyiv_now.strftime("%Y-%m-%d"),
        "queues": result_queues
    }

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
