import requests, re, json, yfinance as yf
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def dene(ad, f):
    try: print("=====", ad); f()
    except Exception as e: print("HATA", ad, repr(e)[:300])
def gn():
    r=requests.get("https://news.google.com/rss/search?q=THYAO+hisse&hl=tr&gl=TR&ceid=TR:tr",headers=UA,timeout=20)
    print(r.status_code, len(r.text)); print(re.findall(r"<item>.*?</item>", r.text, re.S)[:2])
def kap1():
    r=requests.post("https://www.kap.org.tr/tr/api/memberDisclosureQuery",json={"fromDate":"2026-11-01","toDate":"2026-11-07","memberType":"IGS","mkkMemberOidList":[],"inactiveMkkMemberOidList":[],"disclosureClass":"","subjectList":[],"isLate":"","mainSector":"","sector":"","subSector":"","marketOidList":[],"index":"","bdkReview":"","bdkMemberOidList":[],"year":"","term":"","ruleType":"","period":"","fromSrc":False,"srcCategory":"","discIndex":[]},headers=UA,timeout=20)
    print(r.status_code, r.text[:600])
def kap2():
    for u in ["https://www.kap.org.tr/tr/api/disclosure/list/main","https://www.kap.org.tr/tr/bildirim-sorgu","https://www.kap.org.tr/tr/api/home-disclosures"]:
        r=requests.get(u,headers=UA,timeout=20); print(u, r.status_code, r.headers.get("content-type"), r.text[:300].replace("\n"," "))
def tcmb():
    u="https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari"
    r=requests.get(u,headers=UA,timeout=30); print(r.status_code, len(r.text))
    t=re.sub(r"<[^>]+>"," ",r.text); t=re.sub(r"\s+"," ",t); i=t.find("2026"); print(t[i-200:i+1500])
def yfn():
    n=yf.Ticker("NVDA").news; print(len(n)); print(json.dumps(n[:1],ensure_ascii=False)[:800])
    n=yf.Ticker("THYAO.IS").news; print("THYAO", len(n)); print(json.dumps(n[:1],ensure_ascii=False)[:500])
def yfi():
    i=yf.Ticker("NVDA").info; print({k:i.get(k) for k in ["targetMeanPrice","targetHighPrice","targetLowPrice","recommendationKey","numberOfAnalystOpinions","fiftyTwoWeekHigh","exDividendDate","dividendRate","dividendYield"]})
    i=yf.Ticker("THYAO.IS").info; print({k:i.get(k) for k in ["targetMeanPrice","recommendationKey","numberOfAnalystOpinions","exDividendDate","dividendRate","dividendYield"]})
    print(yf.Ticker("TUPRS.IS").dividends.tail(3)); print(yf.Ticker("AAPL").calendar)
for a,f in [("gnews",gn),("kap1",kap1),("kap2",kap2),("tcmb",tcmb),("yfnews",yfn),("yfinfo",yfi)]: dene(a,f)
