"""Collecte API SYNOP authentique ; cache par année et reprise sans appel inutile."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import time
import httpx
from .config import ROOT, SOURCE_API, STATIONS
from .data import clean_records, save_frame

def collect(start='2020-01-01', end='2026-11-04', refresh=False):
    begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    if begin >= finish:
        raise ValueError('La date de fin exclusive doit suivre le début.')
    cache = ROOT / 'data/raw'
    cache.mkdir(parents=True, exist_ok=True)
    records, manifest = [], []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for year in range(begin.year, finish.year + 1):
            a, b = max(begin, date(year, 1, 1)), min(finish, date(year + 1, 1, 1))
            if a >= b:
                continue
            path = cache / f'synop_{a}_{b}.json'
            where = ("numer_sta in ('07110','07130') AND code_reg='53' "
                     f"AND date >= date'{a}' AND date < date'{b}' AND hour(date)=6")
            params = {'select': 'numer_sta,date,t,u,pmer,ff,rr24,code_reg',
                      'where': where, 'order_by': 'date,numer_sta', 'limit': -1}
            if refresh or not path.exists():
                for attempt in range(3):
                    try:
                        response = client.get(SOURCE_API + '/exports/json', params=params)
                        response.raise_for_status()
                        content = response.json()
                        if not isinstance(content, list):
                            raise ValueError('Schéma de réponse SYNOP inattendu.')
                        temporary = path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(content), encoding='utf-8')
                        temporary.replace(path)
                        break
                    except (httpx.HTTPError, ValueError):
                        if attempt == 2:
                            raise
                        time.sleep(1 + attempt)
                time.sleep(.3)
            content = json.loads(path.read_text(encoding='utf-8'))
            records.extend(content)
            manifest.append({'file': path.name, 'records': len(content),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'endpoint': SOURCE_API + '/exports/json', 'params': params})
            print(f'{a} → {b}: {len(content)} observations', flush=True)
    frame = clean_records(records)
    save_frame(frame)
    frame.to_csv(ROOT / 'data/observations_clean.csv', index=False)
    quality = {'processed_at_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'Météo-France SYNOP via API publique Opendatasoft',
        'licence': 'Licence Ouverte Etalab — vérifier la fiche producteur lors de la réutilisation',
        'stations': STATIONS, 'raw_records': len(records), 'clean_rows': len(frame),
        'min_day': frame.day.min(), 'max_day': frame.day.max(),
        'missing_fraction': frame.isna().mean().to_dict(), 'files': manifest}
    (ROOT / 'data/provenance.json').write_text(json.dumps(quality, indent=2), encoding='utf-8')
    print(f'SQLite : {len(frame)} lignes nettoyées, région Bretagne.')
    return quality

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--start', default='2020-01-01')
    p.add_argument('--end', default='2026-11-04', help='Fin exclusive ISO, borne figée reproductible.')
    p.add_argument('--refresh', action='store_true')
    args = p.parse_args()
    collect(args.start, args.end, args.refresh)
