#!/usr/bin/env python3
import json, re, sys, urllib.request, urllib.parse
from datetime import datetime, timezone
from html import unescape

STARTS = [
    "https://www.darko-golner.com/projekti/gdjesukamere/basicmap/",
    "https://www.darko-golner.com/projekti/gdjesukamere/GdjeSuKamere_karta.php",
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
seen=set()
docs=[]
queue=list(STARTS)

def fetch(url):
    req=urllib.request.Request(url,headers={
        "User-Agent":UA,
        "Accept":"text/html,application/json,application/javascript,text/javascript,*/*",
        "Referer":STARTS[0],
    })
    with urllib.request.urlopen(req,timeout=30) as r:
        ct=r.headers.get("Content-Type","")
        data=r.read()
    return data.decode("utf-8","replace"),ct

def same_site(url):
    h=urllib.parse.urlparse(url).hostname or ""
    return h=="darko-golner.com" or h.endswith(".darko-golner.com")

# Crawl page assets and likely data endpoints. Limit protects against crawling the whole site.
while queue and len(seen)<80:
    url=queue.pop(0)
    if url in seen or not same_site(url): continue
    seen.add(url)
    try:
        text,ct=fetch(url)
    except Exception as e:
        print("WARN fetch",url,e,file=sys.stderr); continue
    docs.append((url,ct,text))
    print("FETCH",url,ct,len(text),file=sys.stderr)

    candidates=[]
    # HTML/JS assets and iframe sources
    candidates += re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']',text,re.I)
    # quoted strings that look like local data/API files
    candidates += re.findall(r'["\']([^"\']+\.(?:php|json|xml|js|txt|csv)(?:\?[^"\']*)?)["\']',text,re.I)
    # fetch/ajax/XHR URLs
    candidates += re.findall(r'(?:fetch|ajax|open)\s*\(\s*["\']([^"\']+)["\']',text,re.I)

    for c in candidates:
        c=unescape(c).strip()
        if c.startswith(("javascript:","#","mailto:","tel:")): continue
        u=urllib.parse.urljoin(url,c)
        if same_site(u) and u not in seen and u not in queue:
            # Avoid images/fonts/styles; keep pages/scripts/data.
            path=urllib.parse.urlparse(u).path.lower()
            if path.endswith((".png",".jpg",".jpeg",".gif",".svg",".ico",".css",".woff",".woff2",".ttf")):
                continue
            queue.append(u)

found=[]

def clean_name(s):
    if not s: return "Kamera za nadzor brzine"
    s=re.sub(r'<[^>]+>',' ',s)
    s=unescape(s)
    s=re.sub(r'\s+',' ',s).strip(" \t\r\n,;:'\"")
    return s[:180] or "Kamera za nadzor brzine"

def add(lat,lon,ctx,source):
    try: lat=float(str(lat).replace(",",".")); lon=float(str(lon).replace(",","."))
    except: return
    if not (42.0<=lat<=47.0 and 13.0<=lon<=20.0): return

    name=""
    patterns=[
      r'(?:title|name|naziv|lokacija|location)\s*["\']?\s*[:=]\s*["\']([^"\']{2,180})',
      r'<(?:b|strong)[^>]*>([^<]{2,180})</(?:b|strong)>',
    ]
    for p in patterns:
        m=re.search(p,ctx,re.I)
        if m: name=clean_name(m.group(1)); break
    speed=None
    m=re.search(r'(?:speed|brzina|ograni[cč]enje|limit)\D{0,25}(\d{2,3})',ctx,re.I)
    if m:
        v=int(m.group(1))
        if 20<=v<=200: speed=v
    direction=""
    m=re.search(r'(?:direction|smjer)\s*["\']?\s*[:=]\s*["\']([^"\']{1,100})',ctx,re.I)
    if m: direction=clean_name(m.group(1))
    found.append({
      "name":name or "Kamera za nadzor brzine",
      "latitude":lat,"longitude":lon,
      "speed_limit":speed,"direction":direction,
      "source":source
    })

for url,ct,t in docs:
    # JSON objects / JS objects: latitude/longitude, lat/lng
    patterns=[
      r'(?:"?(?:latitude|lat)"?\s*:\s*"?)(4[2-7]\.\d+)"?.{0,500}?(?:"?(?:longitude|lon|lng)"?\s*:\s*"?)(1[3-9]\.\d+)',
      r'(?:"?(?:longitude|lon|lng)"?\s*:\s*"?)(1[3-9]\.\d+)"?.{0,500}?(?:"?(?:latitude|lat)"?\s*:\s*"?)(4[2-7]\.\d+)',
    ]
    for idx,p in enumerate(patterns):
        for m in re.finditer(p,t,re.I|re.S):
            a,b=m.span(); ctx=t[max(0,a-500):min(len(t),b+700)]
            if idx==0: add(m.group(1),m.group(2),ctx,url)
            else: add(m.group(2),m.group(1),ctx,url)

    # Leaflet/Google-style arrays and generic Croatia coordinate pairs
    for m in re.finditer(r'(?<![\d.])(4[2-7]\.\d{4,})\s*[,;]\s*(1[3-9]\.\d{4,})(?![\d.])',t):
        a,b=m.span(); add(m.group(1),m.group(2),t[max(0,a-500):min(len(t),b+700)],url)

# Deduplicate by coordinate; prefer richer records.
best={}
for x in found:
    k=(round(x["latitude"],6),round(x["longitude"],6))
    score=(x["name"]!="Kamera za nadzor brzine")*3+(x["speed_limit"] is not None)*2+bool(x["direction"])
    if k not in best or score>best[k][0]:
        best[k]=(score,x)
radars=[v[1] for v in best.values()]
radars.sort(key=lambda x:(x["latitude"],x["longitude"]))

# Save diagnostics as well; if extraction fails, Actions log shows every fetched endpoint.
print("Fetched documents:",len(docs),file=sys.stderr)
for u,ct,t in docs:
    print("DOC",u,ct,len(t),file=sys.stderr)
print("Unique radar candidates:",len(radars),file=sys.stderr)

if len(radars)<10:
    # Don't destroy an existing good database.
    raise SystemExit(
      f"Extraction found only {len(radars)} locations. "
      "The source format/API has changed; existing radari.json was preserved."
    )

out={
 "dataset":"GdjeSuKamere speed-camera locations",
 "source":STARTS[0],
 "generated":datetime.now(timezone.utc).isoformat(),
 "count":len(radars),
 "radars":radars
}
with open("croatia/data/radari.json","w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print("Extracted",len(radars),"radar locations")
