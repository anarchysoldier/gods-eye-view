#!/usr/bin/env python3
import json, re, sys, urllib.request, urllib.parse
from datetime import datetime, timezone
from html import unescape

START = "https://www.darko-golner.com/projekti/gdjesukamere/basicmap/"
UA = "Mozilla/5.0 (compatible; GodsEyeCroatia/1.0; +https://github.com/anarchysoldier/gods-eye-view)"

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/javascript,*/*"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")

html=get(START)
docs=[("page",START,html)]

# Follow same-site JS because the current map may keep marker data there.
for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',html,re.I):
    u=urllib.parse.urljoin(START,unescape(src))
    if "darko-golner.com" in urllib.parse.urlparse(u).netloc:
        try: docs.append(("js",u,get(u)))
        except Exception as e: print("WARN JS",u,e,file=sys.stderr)

found=[]

def add(lat,lon,name="",speed=None,direction="",source=""):
    try: lat=float(lat); lon=float(lon)
    except: return
    if not (42 <= lat <= 47 and 13 <= lon <= 20): return
    key=(round(lat,6),round(lon,6))
    found.append({
        "name": (name or "Kamera za nadzor brzine").strip()[:180],
        "latitude": lat, "longitude": lon,
        "speed_limit": speed,
        "direction": (direction or "").strip()[:120],
        "source": source
    })

for typ,url,t in docs:
    # Common Leaflet / Google Maps coordinate forms.
    for m in re.finditer(r'(?:L\.marker|L\.circleMarker)\s*\(\s*\[\s*([4][2-7]\.\d+)\s*,\s*(1[3-9]\.\d+)\s*\]',t,re.I):
        a,b=m.span(); ctx=t[max(0,a-350):min(len(t),b+700)]
        nm=re.search(r'(?:title|name|naziv)\s*[:=]\s*["\']([^"\']+)',ctx,re.I)
        sp=re.search(r'(?:speed|brzina|ogranicenje|ograničenje)\D{0,12}(\d{2,3})',ctx,re.I)
        add(m.group(1),m.group(2),nm.group(1) if nm else "",int(sp.group(1)) if sp else None,source=url)

    for m in re.finditer(r'(?:lat(?:itude)?\s*[:=]\s*)([4][2-7]\.\d+).{0,160}?(?:lng|lon(?:gitude)?\s*[:=]\s*)(1[3-9]\.\d+)',t,re.I|re.S):
        a,b=m.span(); ctx=t[max(0,a-300):min(len(t),b+500)]
        nm=re.search(r'(?:title|name|naziv)\s*[:=]\s*["\']([^"\']+)',ctx,re.I)
        sp=re.search(r'(?:speed|brzina|ogranicenje|ograničenje)\D{0,12}(\d{2,3})',ctx,re.I)
        add(m.group(1),m.group(2),nm.group(1) if nm else "",int(sp.group(1)) if sp else None,source=url)

    # Raw coordinate pairs used in marker arrays.
    for m in re.finditer(r'(?<![\d.])([4][2-7]\.\d{4,})\s*[,;]\s*(1[3-9]\.\d{4,})(?![\d.])',t):
        a,b=m.span(); ctx=t[max(0,a-250):min(len(t),b+400)]
        # Skip if this pair was already picked up by richer patterns; dedupe later.
        nm=re.search(r'["\']([^"\']{3,100})["\']',ctx)
        sp=re.search(r'(?:speed|brzina|ogranicenje|ograničenje)\D{0,12}(\d{2,3})',ctx,re.I)
        add(m.group(1),m.group(2),nm.group(1) if nm else "",int(sp.group(1)) if sp else None,source=url)

# Dedupe coordinates, preferring records with a non-generic name/speed.
best={}
for x in found:
    k=(round(x["latitude"],6),round(x["longitude"],6))
    score=(x["name"]!="Kamera za nadzor brzine")*2 + (x["speed_limit"] is not None)
    if k not in best or score > best[k][0]: best[k]=(score,x)
radars=[v[1] for v in best.values()]
radars.sort(key=lambda x:(x["latitude"],x["longitude"]))

# Guard against silently publishing a broken scrape.
if len(radars) < 10:
    raise SystemExit(f"Extraction found only {len(radars)} locations; refusing to overwrite radari.json")

out={
  "dataset":"GdjeSuKamere speed-camera locations",
  "source":START,
  "generated":datetime.now(timezone.utc).isoformat(),
  "count":len(radars),
  "radars":radars
}
with open("croatia/data/radari.json","w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print("Extracted",len(radars),"radar locations")
