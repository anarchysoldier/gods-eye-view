#!/usr/bin/env python3
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URLS = [
    "https://www.darko-golner.com/projekti/gdjesukamere/load_locations_for_flutter.php",
    "https://www.darko-golner.com/projekti/gdjesukamere/basicmap/load_locations_for_flutter.php",
]
UA = "Mozilla/5.0 (compatible; GodsEyeCroatia/1.0)"

def download():
    errors = []
    for url in URLS:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.darko-golner.com/projekti/gdjesukamere/basicmap/",
            })
            with urllib.request.urlopen(req, timeout=40) as res:
                raw = res.read().decode("utf-8", "replace").strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get("radars") or data.get("locations") or data.get("data") or []
            if not isinstance(data, list) or not data:
                raise ValueError("Endpoint nije vratio neprazan JSON array.")
            return url, data
        except Exception as e:
            errors.append(f"{url}: {e}")
    raise RuntimeError("\n".join(errors))

def normalize(rows):
    out, seen = [], set()
    for r in rows:
        try:
            rid = int(r["id"])
            lat = float(r["latitude"])
            lon = float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append({
            "id": rid,
            "latitude": lat,
            "longitude": lon,
            "location_name": str(r.get("location_name") or f"Radar {rid}").strip(),
            "speed_limit": r.get("speed_limit"),
        })
    return out

url, rows = download()
radars = normalize(rows)
payload = {
    "dataset": "GdjeSuKamere radar locations",
    "source": url,
    "generated": datetime.now(timezone.utc).isoformat(),
    "count": len(radars),
    "radars": radars,
}
path = Path("data/radari.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"OK: {len(radars)} radara -> {path}")
