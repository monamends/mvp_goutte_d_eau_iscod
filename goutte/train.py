"""Sélection sur 2024, test final 2025+ ; jamais de séparation aléatoire."""
import hashlib
import json
import time
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
    confusion_matrix, f1_score, fbeta_score, precision_score, recall_score, roc_auc_score)
from sklearn.calibration import calibration_curve
from .config import ROOT, FEATURES, NUMERIC, MODEL_PATH, METRICS_PATH
from .data import load_frame, make_samples

def build_pipeline(estimator):
    numerical = Pipeline([('impute', SimpleImputer(strategy='median')),
                          ('scale', StandardScaler())])
    preprocessor = ColumnTransformer([('numeric', numerical, NUMERIC),
        ('station', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['station_id'])])
    return Pipeline([('prepare', preprocessor), ('classifier', estimator)])

def scores(y, prob, threshold=.5):
    pred = np.asarray(prob) >= threshold
    return {'brier': float(brier_score_loss(y, prob)),
        'roc_auc': float(roc_auc_score(y, prob)),
        'average_precision': float(average_precision_score(y, prob)),
        'accuracy': float(accuracy_score(y, pred)),
        'precision': float(precision_score(y, pred, zero_division=0)),
        'recall': float(recall_score(y, pred, zero_division=0)),
        'f1': float(f1_score(y, pred, zero_division=0)),
        'f2': float(fbeta_score(y, pred, beta=2, zero_division=0)),
        'confusion_matrix': confusion_matrix(y, pred, labels=[0, 1]).tolist()}

def train():
    started = time.perf_counter()
    data = make_samples(load_frame())
    train = data[data.target_date < '2024-01-01'].copy()
    valid = data[(data.target_date >= '2024-01-01') & (data.target_date < '2025-01-01')].copy()
    test = data[data.target_date >= '2025-01-01'].copy()
    for name, split in [('train', train), ('validation', valid), ('test', test)]:
        if len(split) < 100 or split.rain.nunique() != 2:
            raise ValueError(f'Jeu {name} insuffisant ou une seule classe : {len(split)} lignes.')
    candidates = {
      'logistic_regression': LogisticRegression(C=1, max_iter=1000, random_state=42),
      'random_forest': RandomForestClassifier(n_estimators=150, max_depth=8,
          min_samples_leaf=15, random_state=42, n_jobs=1)}
    fitted, validation = {}, {}
    for name, estimator in candidates.items():
        model = build_pipeline(estimator).fit(train[FEATURES], train.rain)
        prob = model.predict_proba(valid[FEATURES])[:, 1]
        fitted[name] = model
        validation[name] = scores(valid.rain, prob)
    selected = min(validation, key=lambda n: validation[n]['brier'])
    model = fitted[selected]
    valid_prob = model.predict_proba(valid[FEATURES])[:, 1]
    # Coût des pluies manquées prioritaire : F2 choisi AVANT examen du test.
    thresholds = np.arange(.2, .71, .05)
    threshold = float(max(thresholds, key=lambda t: fbeta_score(
        valid.rain, valid_prob >= t, beta=2, zero_division=0)))
    test_prob = model.predict_proba(test[FEATURES])[:, 1]
    train['month'] = train.target_date.dt.month
    climate = train.groupby(['station_id', 'month']).rain.mean().to_dict()
    global_rate = float(train.rain.mean())
    baseline = np.array([climate.get((r.station_id, r.target_date.month), global_rate)
                         for r in test.itertuples()])
    persistence = np.clip((test.rain_prev_mm >= 1).astype(float).to_numpy(), .01, .99)
    per_station = {}
    for station, part in test.groupby('station_id'):
        per_station[station] = scores(part.rain, model.predict_proba(part[FEATURES])[:, 1], threshold)
    observed, predicted = calibration_curve(test.rain, test_prob, n_bins=8, strategy='quantile')
    provenance = json.loads((ROOT/'data/provenance.json').read_text(encoding='utf-8'))
    artifact = {'pipeline': model, 'name': selected, 'threshold': threshold,
        'train_until': train.target_date.max().date().isoformat(),
        'validation_until': valid.target_date.max().date().isoformat(),
        'earliest_target': '2025-01-01', 'sklearn_version': sklearn.__version__,
        'rain_definition': 'Précipitations >= 1 mm entre 06:00 UTC la veille et 06:00 UTC à la date demandée',
        'created_at_utc': datetime.now(timezone.utc).isoformat()}
    MODEL_PATH.parent.mkdir(exist_ok=True, parents=True)
    joblib.dump(artifact, MODEL_PATH)
    metrics = {'selected_model': selected, 'threshold': threshold,
        'rain_event_mm': 1., 'training_seconds': round(time.perf_counter()-started, 3),
        'sklearn_version': sklearn.__version__,
        'splits': {name: {'n': len(part), 'from': part.target_date.min().date().isoformat(),
            'to': part.target_date.max().date().isoformat(), 'rain_rate': float(part.rain.mean())}
            for name, part in [('train',train), ('validation',valid), ('test',test)]},
        'validation_candidates': validation, 'test': scores(test.rain, test_prob, threshold),
        'baseline_seasonal_test': scores(test.rain, baseline, threshold),
        'baseline_persistence_test': scores(test.rain, persistence, .5),
        'per_station_test': per_station,
        'calibration': {'predicted_mean': predicted.tolist(), 'observed_frequency': observed.tolist()},
        'data_sha256': hashlib.sha256((ROOT/'data/observations_clean.csv').read_bytes()).hexdigest(),
        'model_sha256': hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        'source_latest_day': provenance['max_day']}
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    result = test[['station_id','target_date','target_rain_mm','rain']].copy()
    result['probability'], result['seasonal_probability'] = test_prob, baseline
    result['predicted_rain'] = (test_prob >= threshold).astype(int)
    result.to_csv(ROOT/'artifacts/test_predictions.csv', index=False)
    print(json.dumps(metrics, indent=2))
    return metrics

if __name__ == '__main__':
    train()
