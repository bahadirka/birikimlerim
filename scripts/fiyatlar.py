"""BIST, ABD hisse ve TEFAS fon fiyatlarını toplayıp prices.json yazar.
Kişisel veri yok: sadece genel piyasa fiyatları."""
import json, sys, time, datetime as dt
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
out = {"guncel": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
       "bist": {}, "abd": {}, "fon": {}, "hata": []}

def liste(dosya):
    p = KOK / "scripts" / dosya
    return sorted({l.strip().upper() for l in p.read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")})

# ---------- Hisseler (Yahoo, ~15 dk gecikmeli) ----------
def hisseler(semboller, ek, hedef):
    import yfinance as yf
    tick = [s + ek for s in semboller]
    for i in range(0, len(tick), 80):
        parca = tick[i:i+80]
        try:
            df = yf.download(parca, period="7d", interval="1d", group_by="ticker",
                             progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            out["hata"].append(f"yahoo: {e}"); continue
        for t in parca:
            try:
                c = (df[t] if len(parca) > 1 else df)["Close"].dropna()
                if c.empty: continue
                p = float(c.iloc[-1]); onceki = float(c.iloc[-2]) if len(c) > 1 else None
                hedef[t[:-len(ek)] if ek else t] = {
                    "p": round(p, 4),
                    "ch": round((p / onceki - 1) * 100, 2) if onceki else None,
                    "t": str(c.index[-1].date())}
            except Exception:
                pass
        time.sleep(1)

try:
    hisseler(liste("bist.txt"), ".IS", out["bist"])
    hisseler(liste("abd.txt"), "", out["abd"])
except Exception as e:
    out["hata"].append(f"hisse: {e}")

# ---------- TEFAS (yatırım + emeklilik fonları, günlük) ----------
def tefas():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                      "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
                      "X-Requested-With": "XMLHttpRequest", "Origin": "https://www.tefas.gov.tr"})
    try: s.get("https://www.tefas.gov.tr/TarihselVeriler.aspx", timeout=30)
    except Exception: pass
    bit = dt.date.today(); bas = bit - dt.timedelta(days=7)
    for tip in ("YAT", "EMK", "BYF"):
        try:
            r = s.post("https://www.tefas.gov.tr/api/DB/BindHistoryInfo", timeout=60, data={
                "fontip": tip, "sfontur": "", "fonkod": "", "fongrup": "",
                "bastarih": bas.strftime("%d.%m.%Y"), "bittarih": bit.strftime("%d.%m.%Y"),
                "fonturkod": "", "fonunvantip": "", "strperiod": "1,1,1,1,1,1,1", "islemdurum": "1"})
            out.setdefault("tefas_tani", []).append(f"{tip}: {r.status_code} {r.headers.get('content-type','')} {len(r.text)}b {r.text[:160]!r}")
            veri = r.json().get("data", [])
        except Exception as e:
            out["hata"].append(f"tefas {tip}: {type(e).__name__} {str(e)[:120]}"); continue
        for d in veri:
            kod = str(d.get("FONKODU", "")).upper(); fiyat = d.get("FIYAT")
            try: tarih = int(str(d.get("TARIH")))
            except Exception: tarih = 0
            if not kod or not fiyat: continue
            onceki = out["fon"].get(kod)
            if onceki is None or tarih >= onceki["_ts"]:
                out["fon"][kod] = {"p": float(fiyat), "_ts": tarih,
                                   "ad": str(d.get("FONUNVAN", ""))[:80], "tip": tip}
        time.sleep(1)
    for v in out["fon"].values():
        ts = v.pop("_ts", 0)
        if ts: v["t"] = dt.datetime.utcfromtimestamp(ts / 1000).date().isoformat()

tefas()

out["say"] = {k: len(out[k]) for k in ("bist", "abd", "fon")}
Path(sys.argv[1] if len(sys.argv) > 1 else "prices.json").write_text(
    json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(out["say"], out["hata"])
