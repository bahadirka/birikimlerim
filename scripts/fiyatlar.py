"""BIST, ABD hisse ve TEFAS fon fiyatlarını toplayıp prices.json yazar.
Kişisel veri yok: sadece genel piyasa fiyatları."""
import json, sys, time, datetime as dt
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
out = {"guncel": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
       "bist": {}, "abd": {}, "fon": {}, "hata": []}

out["adlar"] = {}
def liste(dosya):
    p = KOK / "scripts" / dosya
    kodlar, adlar = set(), {}
    for l in p.read_text(encoding="utf-8").splitlines():
        if not l.strip() or l.startswith("#"): continue
        kod, _, ad = l.partition("|")
        kod = kod.strip().upper(); kodlar.add(kod)
        if ad.strip(): adlar[kod] = ad.strip()
    out["adlar"][dosya.split(".")[0]] = adlar
    return sorted(kodlar)

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

# ---------- Dokununca açılan grafikler: gün / hafta / yıl ----------
def grafikler():
    import yfinance as yf
    g = out["grafik"] = {}
    def tv(c, adim=1):
        c = c.dropna()
        if adim > 1: c = c.iloc[::adim].combine_first(c.iloc[-1:]) if len(c) else c
        return {"t": [int(i.timestamp()) for i in c.index], "v": [round(float(x), 4) for x in c.tolist()]}
    try:
        h = yf.download(list(SERI.values()), period="5d", interval="15m", group_by="ticker", progress=False, threads=True, auto_adjust=False)
        y = yf.download(list(SERI.values()), period="1y", interval="1d", group_by="ticker", progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        out["hata"].append(f"grafik: {e}"); return
    for k, t in SERI.items():
        try:
            ch, cy = h[t]["Close"].dropna(), y[t]["Close"].dropna()
            son = ch.index[-1].date() if len(ch) else None
            gun = ch[[i.date() == son for i in ch.index]] if son else ch
            if len(gun) < 4: gun = ch.iloc[-32:]
            g[k] = {"gun": tv(gun), "hafta": tv(ch, 2), "yil": tv(cy)}
        except Exception:
            pass
    def bilesik(ad, a, b, bol):
        if a not in g or b not in g: return
        g[ad] = {}
        for r in ("gun", "hafta", "yil"):
            A, B = g[a][r], g[b][r]
            bmap = dict(zip(B["t"], B["v"]))
            tt, vv, son_b = [], [], None
            for ts, v in zip(A["t"], A["v"]):
                son_b = bmap.get(ts, son_b)
                if son_b is None:  # en yakın önceki kur
                    oncekiler = [bv for bt, bv in zip(B["t"], B["v"]) if bt <= ts]
                    son_b = oncekiler[-1] if oncekiler else (B["v"][0] if B["v"] else None)
                if son_b: tt.append(ts); vv.append(round(v * son_b / bol, 3))
            g[ad][r] = {"t": tt, "v": vv}
    bilesik("GRAM", "ONS", "USD", 31.1035)
    bilesik("GUMUS", "AGONS", "USD", 31.1035)
try:
    grafikler()
except Exception as e:
    out["hata"].append(f"grafik: {e}")

# ---------- TEFAS (yatırım + emeklilik + borsa yatırım fonları, günlük) ----------
# Eski /api/DB/* adresleri kapandı; yenisi JSON alır, tarih YYYYMMDD, satırlar "resultList" altında.
TEFAS_URLLER = ["https://www.tefas.gov.tr/api/funds/fonGnlBlgSiraliGetirDosya",
                "https://fonturkey.com.tr/api/funds/fonGnlBlgSiraliGetirDosya"]
gecmis = {}
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
            gecmis.setdefault(kod, {})[tarih] = fiyat
            onceki = out["fon"].get(kod)
            if onceki is None or tarih >= onceki["t"]:
                out["fon"][kod] = {"p": fiyat, "t": tarih, "ad": str(d.get("fonUnvan", ""))[:80], "tip": tip}

tefas()
for kod, g in gecmis.items():  # günlük değişim: son iki fiyat günü
    tarihler = sorted(g)
    if len(tarihler) >= 2 and kod in out["fon"] and g[tarihler[-2]]:
        out["fon"][kod]["ch"] = round((g[tarihler[-1]] / g[tarihler[-2]] - 1) * 100, 4)

# ---------- TCMB döviz kurları (fon fiyatlaması bu kurlarla yapılır) ----------
def tcmb():
    import requests, xml.etree.ElementTree as ET
    out["tcmb"] = {}
    gun = dt.date.today()
    for _ in range(14):
        url = ("https://www.tcmb.gov.tr/kurlar/today.xml" if gun == dt.date.today()
               else f"https://www.tcmb.gov.tr/kurlar/{gun:%Y%m}/{gun:%d%m%Y}.xml")
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and b"<Tarih_Date" in r.content:
                kok = ET.fromstring(r.content)
                tarih = kok.get("Date")  # MM/DD/YYYY
                ay, g, yil = tarih.split("/")
                kayit = {}
                for c in kok.findall("Currency"):
                    kod = c.get("CurrencyCode")
                    if kod in ("USD", "EUR", "GBP"):
                        def f(tag):
                            try: return float(c.findtext(tag))
                            except Exception: return None
                        kayit[kod] = {"da": f("ForexBuying"), "ds": f("ForexSelling"), "ea": f("BanknoteBuying"), "es": f("BanknoteSelling")}
                out["tcmb"][f"{yil}-{ay}-{g}"] = kayit
        except Exception as e:
            out["hata"].append(f"tcmb {gun}: {type(e).__name__}")
        gun -= dt.timedelta(days=1)
        if len(out["tcmb"]) >= 7: break
try:
    tcmb()
except Exception as e:
    out["hata"].append(f"tcmb: {e}")

out["say"] = {k: len(out[k]) for k in ("bist", "abd", "fon")}
Path(sys.argv[1] if len(sys.argv) > 1 else "prices.json").write_text(
    json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(out["say"], out["hata"])
