"""Burak Arslan (b4thenews) yayınları: YouTube kanal akışı + video metinleri + site.
Çıktı: b4.json (herkese açık içerik; kişisel veri yok). Günlük özet bunu okur.
Kullanım: python scripts/b4.py <cikti.json> <onceki.json>"""
import json, re, sys, html, datetime as dt, requests
from pathlib import Path
CIKTI = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ek/b4.json")
ONCEKI = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/onceki/b4.json")
KANAL = "UC6uGQS8n9wReE-0JO1-jQJg"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9"}
try: eski = {v["id"]: v for v in json.loads(ONCEKI.read_text(encoding="utf-8")).get("videolar", [])}
except Exception: eski = {}
hata, videolar = [], []
def kanal_id():
    try:
        r = requests.get("https://www.youtube.com/@BurakArslanb4thenews", headers={**UA, "Cookie": "CONSENT=YES+1"}, timeout=30)
        for desen in (r'"externalId":"(UC[\w-]{22})"', r'"channelId":"(UC[\w-]{22})"', r'youtube\.com/channel/(UC[\w-]{22})'):
            m = re.search(desen, r.text)
            if m: return m.group(1)
    except Exception as e:
        hata.append(f"kanal: {e}")
    return KANAL
KANAL = kanal_id(); print("kanal id:", KANAL)
try:
    r = requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={KANAL}", headers=UA, timeout=30); r.raise_for_status()
    for e in re.findall(r"<entry>(.*?)</entry>", r.text, re.S)[:10]:
        g = lambda t: html.unescape((re.search(rf"<{t}[^>]*>(.*?)</{t}>", e, re.S) or [None, ""])[1]).strip()
        vid = g("yt:videoId")
        videolar.append({"id": vid, "baslik": g("title"), "tarih": g("published"), "link": f"https://www.youtube.com/watch?v={vid}", "aciklama": g("media:description")[:1500]})
except Exception as e:
    hata.append(f"rss: {e}")
if not videolar:   # yedek: b4thenews ana sayfasındaki gömülü videolar
    try:
        r = requests.get("https://www.b4thenews.com/", headers=UA, timeout=30)
        for vid in list(dict.fromkeys(re.findall(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", r.text)))[:6]:
            t = ""
            try: t = requests.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json", timeout=15).json().get("title", "")
            except Exception: pass
            videolar.append({"id": vid, "baslik": t, "tarih": "", "link": f"https://www.youtube.com/watch?v={vid}", "aciklama": ""})
    except Exception as e:
        hata.append(f"site video: {e}")
def metin(vid):
    if eski.get(vid, {}).get("metin"): return eski[vid]["metin"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        t = api.fetch(vid, languages=["tr", "en"])
        return " ".join(s.text for s in t)[:20000]
    except Exception as e:
        hata.append(f"metin {vid}: {type(e).__name__}"); return ""
simdi = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
for v in videolar:   # ilk görüldüğü an: günlük özet "son 24 saatte yeni" videoları buradan seçer
    v["ilk"] = eski.get(v["id"], {}).get("ilk") or simdi
    if not v.get("baslik") and eski.get(v["id"], {}).get("baslik"): v["baslik"] = eski[v["id"]]["baslik"]
sinir = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
for v in videolar:
    try: yeni = dt.datetime.fromisoformat(v["tarih"]) >= sinir
    except Exception: yeni = True
    v["metin"] = metin(v["id"]) if yeni else eski.get(v["id"], {}).get("metin", "")
site = []
try:
    r = requests.get("https://www.b4thenews.com/", headers=UA, timeout=30)
    for u, b in re.findall(r'<a[^>]+href="(https://www\.b4thenews\.com/[^"#?]+/)"[^>]*>([^<]{12,160})</a>', r.text):
        b = html.unescape(b).strip()
        if b and re.search(r"\d{2}-\d{2}-\d{4}", u) and all(s["link"] != u for s in site): site.append({"baslik": b, "link": u})   # yalnız tarihli analiz yazıları
except Exception as e:
    hata.append(f"site: {e}")
CIKTI.parent.mkdir(parents=True, exist_ok=True)
CIKTI.write_text(json.dumps({"guncel": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kanal": "https://www.youtube.com/@BurakArslanb4thenews",
    "x": "https://x.com/b4thenews", "site": "https://www.b4thenews.com/", "videolar": videolar, "siteYazilari": site[:15], "hata": hata}, ensure_ascii=False, indent=1), encoding="utf-8")
print("b4:", len(videolar), "video,", sum(1 for v in videolar if v["metin"]), "metinli,", len(site), "site;", hata[:4])
