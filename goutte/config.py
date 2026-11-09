import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv('GOUTTE_DB', str(ROOT / 'data/weather.sqlite')))
MODEL_PATH = Path(os.getenv('GOUTTE_MODEL', str(ROOT / 'artifacts/model.joblib')))
METRICS_PATH = ROOT / 'artifacts/metrics.json'
SOURCE_API = ('https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/'
              'donnees-synop-essentielles-omm')
STATIONS = {'07110': 'Brest Guipavas', '07130': 'Rennes Saint-Jacques'}
NUMERIC = ['temperature_c', 'humidity_pct', 'pressure_hpa', 'wind_ms',
           'rain_prev_mm', 'season_sin', 'season_cos']
FEATURES = ['station_id'] + NUMERIC
