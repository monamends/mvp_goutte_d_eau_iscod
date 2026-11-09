from contextlib import asynccontextmanager
from datetime import date, timedelta
import json
import time
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .config import MODEL_PATH, METRICS_PATH, STATIONS, FEATURES
from .data import load_frame, features_from_observations

@asynccontextmanager
async def lifespan(app):
    app.state.artifact = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
    yield

app = FastAPI(title="Goutte d'eau — risque de pluie en Bretagne", version='1.0.0', lifespan=lifespan)

class Forecast(BaseModel):
    station_id: str
    station: str
    target_date: date
    observation_cutoff_utc: str
    target_window_utc: str
    probability: float = Field(ge=0, le=1)
    threshold: float
    rain_expected: bool
    model: str
    model_train_until: str
    retrospective: bool
    warning: str
    latency_ms: float

def artifact():
    a = getattr(app.state, 'artifact', None)
    if a is None:
        raise HTTPException(503, 'Modèle absent. Exécuter python -m goutte.train puis redémarrer API.')
    return a

def observations():
    try:
        return load_frame()
    except (FileNotFoundError, OSError):
        raise HTTPException(503, 'Base de données absente ou indisponible.')

@app.get('/health')
def health():
    artifact()
    observations()
    return {'status': 'ok', 'region': 'Bretagne', 'purpose': 'MVP pédagogique'}

@app.get('/stations')
def stations():
    frame = observations()
    return [{'station_id': key, 'name': name,
        'latest_observation': frame.loc[frame.station_id == key, 'day'].max()}
        for key, name in STATIONS.items()]

@app.get('/availability')
def availability(station_id: str):
    if station_id not in STATIONS:
        raise HTTPException(404, 'Station non couverte par le MVP.')
    a = artifact()
    frame = features_from_observations(observations())
    frame = frame[(frame.station_id == station_id) & (frame.available_inputs >= 3)
                  & (frame.target_date >= a['earliest_target'])]
    return {'station_id': station_id, 'dates': frame.target_date.dt.strftime('%Y-%m-%d').tolist()}

@app.get('/metrics')
def metrics():
    if not METRICS_PATH.exists():
        raise HTTPException(503, 'Évaluation non disponible.')
    return json.loads(METRICS_PATH.read_text(encoding='utf-8'))

@app.get('/predict', response_model=Forecast)
def predict(date: date, station_id: str = '07110'):
    start = time.perf_counter()
    if station_id not in STATIONS:
        raise HTTPException(404, 'Station non couverte par le MVP.')
    a = artifact()
    if date.isoformat() < a['earliest_target']:
        raise HTTPException(422, 'Choisir une date à partir de 2025, hors entraînement et sélection.')
    frame = observations()
    issue_day = (date - timedelta(days=1)).isoformat()
    row = frame[(frame.station_id == station_id) & (frame.day == issue_day)]
    if row.empty:
        raise HTTPException(422, 'Observation de la veille à 06 h UTC absente : aucune extrapolation.')
    features = features_from_observations(row)
    if features.available_inputs.iloc[0] < 3:
        raise HTTPException(422, 'Moins de trois variables météo disponibles : estimation refusée.')
    probability = float(a['pipeline'].predict_proba(features[FEATURES])[0, 1])
    return Forecast(station_id=station_id, station=STATIONS[station_id], target_date=date,
        observation_cutoff_utc=issue_day+'T06:00:00+00:00',
        target_window_utc=f'{issue_day} 06:00 → {date.isoformat()} 06:00 UTC',
        probability=round(probability, 6), threshold=a['threshold'],
        rain_expected=probability >= a['threshold'], model=a['name'],
        model_train_until=a['train_until'], retrospective=date < pd.Timestamp.now(tz='UTC').date(),
        warning='MVP expérimental ; estimation stationnelle, pas une alerte officielle ni une prévision à 1 km.',
        latency_ms=round((time.perf_counter()-start)*1000, 3))
