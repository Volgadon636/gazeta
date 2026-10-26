"""Собирает посты публичных Telegram-каналов за вчерашний день (МСК) в posts/<дата>.md и latest.md."""
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

MSK = timezone(timedelta(hours=3))
MAX_PAGES = 15
MAX_CHARS = 1200
ROOT = Path(__file__).parent


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (gazeta)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"retry {url}: {e}", file=sys.stderr)
            time.sleep(3)
    return ""


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".tgme_channel_info_header_title")
    posts = []
    for m in soup.select("div.tgme_widget_message[data-post]"):
        t = m.select_one("a.tgme_widget_message_date time[datetime]")
        if not t:
            continue
        dt = datetime.fromisoformat(t["datetime"]).astimezone(MSK)
        pid = int(m["data-post"].split("/")[-1])
        txt_el = m.select_one(".tgme_widget_message_text")
        text = txt_el.get_text("\n", strip=True) if txt_el else ""
        if not text:
            doc = m.select_one(".tgme_widget_message_document_title, .link_preview_title")
            text = f"[медиа] {doc.get_text(strip=True)}" if doc else "[медиа без текста]"
        fwd = m.select_one(".tgme_widget_message_forwarded_from_name")
        if fwd:
            text = f"(репост из {fwd.get_text(strip=True)}) {text}"
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "…"
        posts.append((pid, dt, text))
    return (title.get_text(strip=True) if title else None), posts


def collect(channel: str, start: datetime, end: datetime):
    url = f"https://t.me/s/{channel}"
    name, found = None, {}
    for _ in range(MAX_PAGES):
        title, posts = parse(fetch(url))
        name = name or title
        if not posts:
            break
        for pid, dt, text in posts:
            if start <= dt < end:
                found[pid] = (dt, text)
        oldest = min(posts, key=lambda p: p[0])
        if oldest[1] < start:
            break
        url = f"https://t.me/s/{channel}?before={oldest[0]}"
        time.sleep(1)
    return name or channel, sorted(found.items())


def main():
    today = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    start, end = today - timedelta(days=1), today
    day = start.strftime("%Y-%m-%d")
    channels = [
        c.strip().lstrip("@")
        for c in (ROOT / "channels.txt").read_text(encoding="utf-8").splitlines()
        if c.strip() and not c.startswith("#")
    ]
    out = [f"# Посты за {day} (МСК)\n"]
    total = 0
    for ch in channels:
        try:
            name, posts = collect(ch, start, end)
        except Exception as e:  # noqa: BLE001
            out.append(f"\n## {ch}\nОШИБКА загрузки: {e}\n")
            continue
        total += len(posts)
        out.append(f"\n## {name} (@{ch}) — {len(posts)} постов\n")
        for pid, (dt, text) in posts:
            out.append(f"\n### t.me/{ch}/{pid} · {dt:%H:%M}\n{text}\n")
    out.append(f"\n---\nВсего постов: {total}\n")
    md = "".join(out)
    (ROOT / "posts").mkdir(exist_ok=True)
    (ROOT / "posts" / f"{day}.md").write_text(md, encoding="utf-8")
    (ROOT / "latest.md").write_text(md, encoding="utf-8")
    print(f"{day}: {total} posts")


if __name__ == "__main__":
    main()
