"""Nettoyage, stockage SQLite et variables disponibles à l'émission seulement."""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from .config import DB_PATH, STATIONS

def clean_records(records):
    rows = []
    for r in records:
        station = str(r.get('numer_sta', '')).zfill(5)
        if station not in STATIONS or str(r.get('code_reg')) != '53':
            continue
        timestamp = pd.to_datetime(r.get('date'), utc=True, errors='coerce')
        if pd.isna(timestamp) or timestamp.hour != 6 or timestamp.minute != 0:
            continue
        def number(key, low, high, offset=0, factor=1):
            try:
                v = (float(r[key]) + offset) * factor
                return v if np.isfinite(v) and low <= v <= high else np.nan
            except (ValueError, TypeError, KeyError):
                return np.nan
        # Les précipitations négatives/codées restent manquantes, jamais « sec ».
        rows.append({'station_id': station, 'observed_at': timestamp.isoformat(),
                     'day': timestamp.date().isoformat(),
                     'temperature_c': number('t', -40, 55, -273.15),
                     'humidity_pct': number('u', 0, 100),
                     'pressure_hpa': number('pmer', 850, 1100, factor=.01),
                     'wind_ms': number('ff', 0, 80),
                     'rain_prev_mm': number('rr24', 0, 500)})
    if not rows:
        raise ValueError('Aucune observation admissible pour les deux stations bretonnes.')
    frame = pd.DataFrame(rows).sort_values(['station_id', 'day'])
    frame = frame.drop_duplicates(['station_id', 'day'], keep='last')
    return frame.reset_index(drop=True)

def save_frame(frame, path=DB_PATH):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA foreign_keys=ON')
        con.executescript('''
          CREATE TABLE IF NOT EXISTS stations(
            station_id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS observations(
            station_id TEXT NOT NULL REFERENCES stations(station_id),
            observed_at TEXT NOT NULL, day TEXT NOT NULL,
            temperature_c REAL, humidity_pct REAL CHECK(humidity_pct BETWEEN 0 AND 100),
            pressure_hpa REAL, wind_ms REAL CHECK(wind_ms >= 0),
            rain_prev_mm REAL CHECK(rain_prev_mm >= 0),
            PRIMARY KEY(station_id, day));
          CREATE INDEX IF NOT EXISTS idx_observations_day ON observations(day);
        ''')
        con.executemany('INSERT OR IGNORE INTO stations VALUES(?,?,?)',
                        [(s, n, 'Bretagne') for s, n in STATIONS.items()])
        values = frame.astype(object).where(pd.notna(frame), None)
        con.executemany('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?,?,?)',
                        values.itertuples(index=False, name=None))

def load_frame(path=DB_PATH):
    if not Path(path).is_file():
        raise FileNotFoundError('Base absente : exécuter python -m goutte.collect.')
    with sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro', uri=True) as con:
        return pd.read_sql_query('SELECT * FROM observations ORDER BY day,station_id', con)

def features_from_observations(frame):
    frame = frame.copy()
    frame['target_date'] = pd.to_datetime(frame['day']) + pd.Timedelta(days=1)
    angle = 2 * np.pi * frame['target_date'].dt.dayofyear / 365.25
    frame['season_sin'], frame['season_cos'] = np.sin(angle), np.cos(angle)
    frame['available_inputs'] = frame[['temperature_c', 'humidity_pct',
        'pressure_hpa', 'wind_ms', 'rain_prev_mm']].notna().sum(axis=1)
    return frame

def make_samples(frame):
    """Jointure sur J+1 exact, et non shift vers la prochaine ligne après un trou."""
    features = features_from_observations(frame)
    labels = frame[['station_id', 'day', 'rain_prev_mm']].rename(
        columns={'day': 'target_date', 'rain_prev_mm': 'target_rain_mm'})
    labels['target_date'] = pd.to_datetime(labels['target_date'])
    joined = features.merge(labels, on=['station_id', 'target_date'], how='inner')
    joined = joined[(joined['available_inputs'] >= 3) & joined['target_rain_mm'].notna()]
    joined['rain'] = (joined['target_rain_mm'] >= 1.0).astype(int)
    return joined.sort_values(['target_date', 'station_id']).reset_index(drop=True)
