#!/usr/bin/env python3
"""Fetch the point feed used by HAK's mobile traffic map. Python 3.11+, stdlib only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SOURCE = 'https://m.hak.hr/poi.asp?t=8987&tko=0'
MAP = 'https://m.hak.hr/map.asp?t=8987&g=0'
TYPES = {'closed': 'Zatvorena cesta', 'roadworks': 'Radovi na cesti'}

def fetch():
    for attempt in range(3):
        try:
            with urlopen(Request(SOURCE, headers={'User-Agent': 'GodsEyeView-HAK/1.0', 'Accept': 'application/xml,text/xml'}), timeout=45) as r:
                data = r.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError('HAK odgovor je prevelik')
                return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def convert(data):
    root = ET.fromstring(data)
    if root.tag != 'markers':
        raise ValueError('Nepoznat format HAK izvora; postojeći podaci ostaju sačuvani')
    features, seen, counts = [], set(), Counter()
    for m in root:
        if m.tag != 'marker' or m.get('message') is not None:
            raise ValueError('Neočekivan HAK odgovor; postojeći podaci ostaju sačuvani')
        category = m.get('c')
        counts[category or 'unknown'] += 1
        if category not in TYPES:
            continue
        event_id = m.get('id', '')
        x, y = float(m.get('x', 'nan')), float(m.get('y', 'nan'))
        if not event_id.isdigit() or not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
            raise ValueError('Neispravan ID ili koordinata HAK događaja')
        if event_id in seen:
            raise ValueError('Ponovljen ID HAK događaja')
        seen.add(event_id)
        features.append({'type': 'Feature', 'id': event_id,
            'geometry': {'type': 'Point', 'coordinates': [x, y]},
            'properties': {'id': event_id, 'category': category, 'title': TYPES[category],
                'period_text': m.get('l', ''), 'urgent': m.get('del') is not None,
                'has_source_line': m.get('o') is not None, 'source': 'HAK', 'source_url': MAP}})
    # A sudden empty result may be an outage/schema change. Do not erase a working feed.
    if not features:
        raise ValueError('Nema radova ni zatvaranja; provjeriti izvor prije zamjene postojećih podataka')
    features.sort(key=lambda f: f['id'])
    return {'type': 'FeatureCollection', 'schema_version': 1,
        'fetched_at': datetime.now(timezone.utc).isoformat(), 'source': SOURCE,
        'source_map': MAP, 'source_category_counts': dict(counts),
        'counts': dict(Counter(f['properties']['category'] for f in features)),
        'features': features}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='croatia/data/hak-promet.geojson')
    args = parser.parse_args()
    result = convert(fetch())
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=dest.parent, delete=False) as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        tmp = Path(f.name)
    tmp.replace(dest)
    print(f"HAK: {result['counts']}; dohvaćeno {result['fetched_at']}")

if __name__ == '__main__':
    main()
