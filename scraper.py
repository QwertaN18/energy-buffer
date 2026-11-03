import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from camoufox.sync_api import Camoufox

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

    print("Запускаем антидетект-браузер Camoufox...")
    with Camoufox(headless="virtual", humanize=True) as browser:
        page = browser.new_page()

        for q in QUEUES:
            url = f"{BASE_URL}/{q.replace('.', '-')}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                
                # Ждём до 10 секунд, если появилась страница проверки Cloudflare
                for _ in range(5):
                    title = page.title()
                    if "Just a moment" not in title:
                        break
                    time.sleep(2)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                page_title = soup.title.string.strip() if soup.title and soup.title.string else "No Title"
                body_text = soup.get_text(separator="\n")

                print(f"[{q}] Title: {page_title}")

                parsed = extract_outages(body_text)
                if parsed is not None:
                    result_queues[q] = parsed
                    print(f"  -> [OK] Найдено отключений: {len(parsed)} -> {parsed}")
                else:
                    snippet = " ".join(body_text.split())[:150]
                    print(f"  -> [WARN] Раздел не найден. Текст: {snippet}")
                    if "Just a moment" in page_title:
                        print("[STOP] Cloudflare всё ещё держит оборону. Останавливаемся, чтобы не ждать.")
                        break
            except Exception as e:
                print(f"[{q}] ERROR: {e}")

    payload = {
        "updated_at": kyiv_now.strftime("%H:%M:%S"),
        "date": kyiv_now.strftime("%Y-%m-%d"),
        "queues": result_queues
    }

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
