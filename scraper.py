import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

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
        return None  # Раздел не найден

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

    # Читаем старый файл, если он есть, чтобы не затереть очередь при случайном сбое сети
    try:
        with open("schedule.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
            if old_data.get("date") == kyiv_now.strftime("%Y-%m-%d"):
                result_queues = old_data.get("queues", {})
    except Exception:
        pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
            locale="uk-UA"
        )
        page = context.new_page()

        for q in QUEUES:
            url = f"{BASE_URL}/{q.replace('.', '-')}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)  # Ждём прогрузки текста
                body_text = page.evaluate("() => document.body ? document.body.innerText : ''")
                parsed = extract_outages(body_text)
                if parsed is not None:
                    result_queues[q] = parsed
                    print(f"[OK] Очередь {q}: найдено интервалов — {len(parsed)}")
                else:
                    print(f"[WARN] Очередь {q}: раздел отключений не найден")
            except Exception as e:
                print(f"[ERROR] Очередь {q}: {e}")

        browser.close()

    payload = {
        "updated_at": kyiv_now.strftime("%H:%M:%S"),
        "date": kyiv_now.strftime("%Y-%m-%d"),
        "queues": result_queues
    }

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
