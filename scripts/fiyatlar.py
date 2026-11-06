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
    out["endeks"] = {}
    hisseler(["XU100.IS", "XU030.IS", "^GSPC", "^IXIC", "^DJI"], "", out["endeks"])
except Exception as e:
    out["hata"].append(f"hisse: {e}")

# ---------- Gün içi mini grafik serileri (15 dk) ----------
SERI = {"XU100": "XU100.IS", "XU030": "XU030.IS", "GSPC": "^GSPC", "IXIC": "^IXIC",
        "USD": "USDTRY=X", "EUR": "EURTRY=X", "ONS": "GC=F", "AGONS": "SI=F", "BTCUSD": "BTC-USD"}
def seriler():
    import yfinance as yf
    out["seri"] = {}
    try:
        df = yf.download(list(SERI.values()), period="5d", interval="15m", group_by="ticker",
                         progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        out["hata"].append(f"seri: {e}"); return
    for k, t in SERI.items():
        try:
            c = df[t]["Close"].dropna()
            if c.empty: continue
            son_gun = c.index[-1].date()
            g = c[[i.date() == son_gun for i in c.index]]
            if len(g) < 4: g = c.iloc[-32:]
            out["seri"][k] = [round(float(x), 4) for x in g.tolist()][-60:]
        except Exception:
            pass
    usd, ons = out["seri"].get("USD"), out["seri"].get("ONS")
    if usd and ons:  # gram altın TL eğrisi ≈ ons($) × dolar / 31,1035
        n = min(len(usd), len(ons))
        out["seri"]["GRAM"] = [round(o * u / 31.1035, 2) for o, u in zip(ons[-n:], usd[-n:])]
    ag = out["seri"].get("AGONS")
    if usd and ag:
        n = min(len(usd), len(ag))
        out["seri"]["GUMUS"] = [round(o * u / 31.1035, 3) for o, u in zip(ag[-n:], usd[-n:])]
try:
    seriler()
except Exception as e:
    out["hata"].append(f"seri: {e}")

# ---------- TEFAS (yatırım + emeklilik + borsa yatırım fonları, günlük) ----------
# Eski /api/DB/* adresleri kapandı; yenisi JSON alır, tarih YYYYMMDD, satırlar "resultList" altında.
TEFAS_URLLER = ["https://www.tefas.gov.tr/api/funds/fonGnlBlgSiraliGetirDosya",
                "https://fonturkey.com.tr/api/funds/fonGnlBlgSiraliGetirDosya"]
def tefas():
    import requests
    h = {"Accept": "application/json, text/javascript, */*; q=0.01", "Content-Type": "application/json",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    bit = dt.date.today(); bas = bit - dt.timedelta(days=10)
    for tip in ("YAT", "EMK", "BYF"):
        govde = {"dil": "TR", "fonTipi": tip, "sfonTurKod": None, "fonKod": None, "fonGrup": None,
                 "basTarih": bas.strftime("%Y%m%d"), "bitTarih": bit.strftime("%Y%m%d"),
                 "fonTurKod": None, "fonUnvanTip": None, "kurucuKod": None, "fonTurAciklama": None}
        satirlar = []
        for url in TEFAS_URLLER:
            for deneme in range(3):
                time.sleep(2)
                try:
                    r = requests.post(url, json=govde, timeout=60, headers={**h, "Referer": url.split("/api/")[0] + "/"})
                    if r.status_code == 200:
                        satirlar = r.json().get("resultList") or []
                        if satirlar: break
                    else:
                        out["hata"].append(f"tefas {tip} {url.split('/')[2]}: HTTP {r.status_code}")
                except Exception as e:
                    out["hata"].append(f"tefas {tip} {url.split('/')[2]}: {type(e).__name__}")
                time.sleep(10)
            if satirlar: break
        if not satirlar:
            out["hata"].append(f"tefas {tip}: boş"); continue
        for d in satirlar:
            kod = str(d.get("fonKodu", "")).upper().strip()
            try: fiyat = float(d.get("fiyat") or 0)
            except Exception: fiyat = 0
            tarih = str(d.get("tarih", ""))[:10]
            if not kod or fiyat <= 0: continue
            onceki = out["fon"].get(kod)
            if onceki is None or tarih >= onceki["t"]:
                out["fon"][kod] = {"p": fiyat, "t": tarih, "ad": str(d.get("fonUnvan", ""))[:80], "tip": tip}

tefas()

out["say"] = {k: len(out[k]) for k in ("bist", "abd", "fon")}
Path(sys.argv[1] if len(sys.argv) > 1 else "prices.json").write_text(
    json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(out["say"], out["hata"])
