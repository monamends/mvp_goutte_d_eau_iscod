from datetime import date, timedelta
import sqlite3
import pandas as pd
from fastapi.testclient import TestClient
from goutte.api import app
from goutte.config import DB_PATH, FEATURES
from goutte.data import clean_records, save_frame, load_frame, make_samples

def test_next_day_is_exact_not_next_available():
    f = pd.DataFrame([{'station_id':'07110','day':d, 'observed_at':d+'T06:00:00+00:00',
        'temperature_c':10, 'humidity_pct':80, 'pressure_hpa':1010, 'wind_ms':3,
        'rain_prev_mm':r} for d,r in [('2025-01-01',0),('2025-01-03',5),('2025-01-04',0)]])
    samples = make_samples(f)
    assert len(samples) == 1
    assert samples.iloc[0].day == '2025-01-03'
    assert samples.iloc[0].rain_prev_mm == 5
    assert samples.iloc[0].rain == 0
    assert 'target_rain_mm' not in FEATURES

def test_clean_region_units_negative_rain_and_upsert(tmp_path):
    record = {'numer_sta':'07110','date':'2025-01-01T06:00:00+00:00',
              'code_reg':'53','t':283.15,'u':80,'pmer':101200,'ff':3,'rr24':-0.1}
    frame = clean_records([record,record,dict(record,code_reg='11')])
    assert len(frame) == 1
    assert abs(frame.temperature_c.iloc[0]-10) < .001
    assert frame.pressure_hpa.iloc[0] == 1012
    assert pd.isna(frame.rain_prev_mm.iloc[0])
    path = tmp_path/'weather.sqlite'
    save_frame(frame,path);save_frame(frame,path)
    assert len(load_frame(path)) == 1

def test_database_is_genuine_regional_and_unique():
    frame = load_frame()
    assert set(frame.station_id) == {'07110','07130'}
    assert len(frame) > 2000
    assert not frame.duplicated(['station_id','day']).any()
    samples = make_samples(frame)
    assert (pd.to_datetime(samples.day) < samples.target_date).all()

def test_api_success_and_error_contracts():
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        dates = client.get('/availability',params={'station_id':'07110'}).json()['dates']
        response = client.get('/predict',params={'station_id':'07110','date':dates[-1]})
        assert response.status_code == 200
        body=response.json()
        assert 0 <= body['probability'] <= 1
        assert body['observation_cutoff_utc'][:10] < body['target_date']
        assert client.get('/predict?date=2035-01-01').status_code == 422
        assert client.get('/predict?date=2023-01-01').status_code == 422
        assert client.get('/predict?date=invalide').status_code == 422
        assert client.get('/predict?date=2025-01-01&station_id=99999').status_code == 404

def test_evaluation_has_ordered_dates():
    import json
    from goutte.config import METRICS_PATH
    m=json.loads(METRICS_PATH.read_text())
    s=m['splits']
    assert s['train']['to'] < s['validation']['from']
    assert s['validation']['to'] < s['test']['from']
    assert m['selected_model'] == min(m['validation_candidates'],
        key=lambda n:m['validation_candidates'][n]['brier'])
