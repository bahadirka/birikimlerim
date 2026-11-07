"""Durum kartı, enflasyon ve haber verisi.
Çıktılar (hepsi genel piyasa verisi, kişisel veri yok):
  analiz.json        — TÜFE aylık serisi, her hisse için dönem getirileri + teknik göstergeler + analist hedefleri
  haber/{bist|abd}/KOD.json — hisse başına son haberler (Google Haberler)
Kullanım: python scripts/analiz.py <cikti_klasoru> <onceki_yayin_klasoru>
"""
import json, re, sys, time, html, shutil, calendar, datetime as dt
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
import requests

KOK = Path(__file__).resolve().parent.parent
CIKTI = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/yayin_ek")
ONCEKI = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/onceki")
CIKTI.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SIMDI = dt.datetime.now(dt.timezone.utc)
hata = []

def liste(dosya):
    kod = {}
    for l in (KOK / "scripts" / dosya).read_text(encoding="utf-8").splitlines():
        if not l.strip() or l.startswith("#"): continue
        k, _, ad = l.partition("|"); kod[k.strip().upper()] = ad.strip()
    return kod
LISTE = {"bist": liste("bist.txt"), "abd": liste("abd.txt")}
YAHOO = {"ALTIN": "ALTINS1"}
EK = {"bist": ".IS", "abd": ""}

def oku(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return None
onceki = oku(ONCEKI / "analiz.json") or {}

def ay_once(d, n):
    y, m = d.year, d.month - n
    while m <= 0: m += 12; y -= 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

# ---------- TÜFE (TCMB tablosu: ay, yıllık %, aylık %) ----------
def tufe():
    u = "https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari"
    r = requests.get(u, headers=UA, timeout=40); r.raise_for_status()
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
    satir = re.findall(r"\b(\d{2})-(\d{4}) (-?\d+[.,]\d+) (-?\d+[.,]\d+)", t)
    seri = {}
    for ay, yil, yillik, aylik in satir:
        seri[f"{yil}-{ay}"] = [float(yillik.replace(",", ".")), float(aylik.replace(",", "."))]
    if len(seri) < 24: raise ValueError(f"TÜFE tablosu okunamadı ({len(seri)} satır)")
    return [[k, *v] for k, v in sorted(seri.items())][-84:]   # son 7 yıl: [ay, yıllık %, aylık %]
try:
    TUFE = tufe()
except Exception as e:
    hata.append(f"tufe: {e}"); TUFE = onceki.get("tufe") or []

# ---------- Hisse dönem getirileri + teknik göstergeler (her çalışmada) ----------
def rsi(c, n=14):
    d = c.diff().dropna()
    if len(d) < n + 1: return None
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean().iloc[-1]
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean().iloc[-1]
    return 100.0 if dn == 0 else round(100 - 100 / (1 + up / dn), 1)

def teknik():
    import yfinance as yf
    sonuc = {}
    for grup in ("bist", "abd"):
        sonuc[grup] = {}
        kodlar = sorted(LISTE[grup]); tick = [YAHOO.get(k, k) + EK[grup] for k in kodlar]
        try:
            df = yf.download(tick, period="13mo", interval="1d", group_by="ticker", progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            hata.append(f"teknik {grup}: {e}"); continue
        for k, t in zip(kodlar, tick):
            try:
                c = (df[t] if len(tick) > 1 else df)["Close"].dropna()
                if len(c) < 30: continue
                son = float(c.iloc[-1]); ref = c.index[-1].date()
                yil = c[c.index.date > ay_once(ref, 12)]
                donem = {"1A": ay_once(ref, 1), "3A": ay_once(ref, 3), "6A": ay_once(ref, 6), "BY": dt.date(ref.year - 1, 12, 31), "1Y": ay_once(ref, 12)}
                g = {}
                for ad, d in donem.items():
                    e = c[c.index.date <= d]
                    if len(e): g[ad] = round((son / float(e.iloc[-1]) - 1) * 100, 2)
                sonuc[grup][k] = {
                    "son": round(son, 4), "t": str(ref), "g": g,
                    "h52": round(float(yil.max()), 4), "l52": round(float(yil.min()), 4),
                    "ma50": round(float(c.tail(50).mean()), 4) if len(c) >= 50 else None,
                    "ma200": round(float(c.tail(200).mean()), 4) if len(c) >= 200 else None,
                    "rsi": rsi(c.tail(120)),
                }
            except Exception:
                pass
    return sonuc
try:
    HISSE = teknik()
except Exception as e:
    hata.append(f"teknik: {e}"); HISSE = onceki.get("hisse") or {}

# ---------- Analist hedefleri (Yahoo, günde bir) ----------
ONERI = {"strong_buy": "Güçlü al", "buy": "Al", "hold": "Tut", "underperform": "Endeks altı", "sell": "Sat", "strong_sell": "Güçlü sat"}
def hedefler():
    if onceki.get("hedefTarih") == SIMDI.date().isoformat() and onceki.get("hedef"):
        return onceki["hedef"], onceki["hedefTarih"]
    import yfinance as yf
    sonuc = {}
    for grup in ("bist", "abd"):
        sonuc[grup] = {}
        for k in sorted(LISTE[grup]):
            try:
                i = yf.Ticker(YAHOO.get(k, k) + EK[grup]).info or {}
                n = i.get("numberOfAnalystOpinions") or 0
                if n and i.get("targetMeanPrice"):
                    sonuc[grup][k] = {"ort": round(float(i["targetMeanPrice"]), 4), "yuk": i.get("targetHighPrice"), "dus": i.get("targetLowPrice"),
                                      "n": int(n), "oneri": ONERI.get(i.get("recommendationKey") or "", None)}
            except Exception:
                pass
            time.sleep(0.25)
    return sonuc, SIMDI.date().isoformat()
try:
    HEDEF, HEDEF_T = hedefler()
except Exception as e:
    hata.append(f"hedef: {e}"); HEDEF, HEDEF_T = onceki.get("hedef") or {}, onceki.get("hedefTarih")

(CIKTI / "analiz.json").write_text(json.dumps({
    "guncel": SIMDI.isoformat(timespec="seconds"), "tufe": TUFE, "hisse": HISSE, "hedef": HEDEF, "hedefTarih": HEDEF_T, "hata": hata,
}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# ---------- Haberler (Google Haberler RSS; en fazla saatte bir yenilenir) ----------
def haber_ara(q, dil):
    hl, gl, ce = ("tr", "TR", "TR:tr") if dil == "tr" else ("en-US", "US", "US:en")
    r = requests.get(f"https://news.google.com/rss/search?q={quote_plus(q)}+when:30d&hl={hl}&gl={gl}&ceid={ce}", headers=UA, timeout=20)
    if r.status_code != 200: raise RuntimeError(f"HTTP {r.status_code}")
    sonuc = []
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        bul = lambda tag: (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1]
        baslik, kaynak = html.unescape(bul("title")).strip(), html.unescape(bul("source")).strip()
        if kaynak and baslik.endswith(" - " + kaynak): baslik = baslik[: -len(kaynak) - 3]
        try: zaman = int(parsedate_to_datetime(bul("pubDate")).timestamp())
        except Exception: zaman = 0
        if baslik: sonuc.append({"b": baslik, "k": kaynak, "u": bul("link").strip(), "z": zaman, "d": dil})
    return sonuc

def haberler():
    hedef = CIKTI / "haber"
    eski_t = (onceki.get("haberGuncel") or "")
    try: yas = (SIMDI - dt.datetime.fromisoformat(eski_t)).total_seconds() / 60
    except Exception: yas = 1e9
    if yas < 50 and (ONCEKI / "haber").exists():
        shutil.copytree(ONCEKI / "haber", hedef, dirs_exist_ok=True); return eski_t
    say = 0
    for grup in ("bist", "abd"):
        (hedef / grup).mkdir(parents=True, exist_ok=True)
        for k, ad in sorted(LISTE[grup].items()):
            try:
                if grup == "bist":
                    l = haber_ara(f'"{k}" hisse', "tr")
                else:
                    isim = re.sub(r"\s*\(.*?\)", "", ad).strip() or k
                    l = haber_ara(f'"{isim}" hisse', "tr")
                    if len(l) < 4: l += haber_ara(f'"{k}" stock', "en")
                tek, gor = [], set()
                for h in sorted(l, key=lambda x: -x["z"]):
                    anah = re.sub(r"\W+", "", h["b"].lower())[:60]
                    if anah in gor: continue
                    gor.add(anah); tek.append(h)
                (hedef / grup / f"{k}.json").write_text(json.dumps(tek[:8], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                say += 1
            except Exception as e:
                eski = ONCEKI / "haber" / grup / f"{k}.json"
                if eski.exists(): shutil.copy(eski, hedef / grup / f"{k}.json")
                if "429" in str(e): time.sleep(20)
            time.sleep(0.6)
    print("haber:", say)
    return SIMDI.isoformat(timespec="seconds")
try:
    HABER_T = haberler()
except Exception as e:
    hata.append(f"haber: {e}"); HABER_T = onceki.get("haberGuncel")
    if (ONCEKI / "haber").exists(): shutil.copytree(ONCEKI / "haber", CIKTI / "haber", dirs_exist_ok=True)

d = oku(CIKTI / "analiz.json"); d["haberGuncel"] = HABER_T; d["hata"] = hata
(CIKTI / "analiz.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("analiz:", {g: len(v) for g, v in HISSE.items()}, {g: len(v) for g, v in HEDEF.items()}, "tufe", len(TUFE), hata)
