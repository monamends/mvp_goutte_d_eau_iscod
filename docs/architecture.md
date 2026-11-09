# Architecture et composants

## Architecture de déploiement du MVP

```mermaid
flowchart TD
  S[API publique SYNOP] -->|HTTPS export JSON| C[Collecteur Python à la demande]
  C -->|Cache de provenance| R[Fichiers bruts et manifeste]
  C -->|Nettoyage et upsert| D[(SQLite)]
  D --> T[Entraînement hors requête]
  T --> M[Modèle joblib et métriques]
  D --> A[FastAPI]
  M --> A
  U[Agriculteur dans son navigateur] --> I[Interface Streamlit]
  I -->|HTTP JSON local| A
```

En production, seul le reverse proxy HTTPS est exposé ; API, base et entraînement restent privés. SQLite convient à ce prototype à faible concurrence. PostgreSQL est l’extension envisagée si plusieurs collecteurs ou réplicas écrivent simultanément. La collecte IoT directe n’est pas développée dans ce MVP : l’adaptateur d’observations pourra la recevoir à condition d’ajouter qualité, identité et horodatage de réception.

## Diagramme de composants

```mermaid
flowchart TD
  UI[streamlit_app.py] -->|GET stations et availability| API[goutte.api]
  UI -->|GET predict et metrics| API
  API -->|features et lecture| DATA[goutte.data]
  API -->|predict_proba| MOD[Pipeline scikit learn]
  COL[goutte.collect] -->|clean_records et save_frame| DATA
  TRAIN[goutte.train] -->|make_samples| DATA
  TRAIN -->|Écrit modèle et scores| MOD
  DATA --> DB[(SQLite stations et observations)]
```

## Modèle de données

`stations(station_id PK, name, region)` est parent de `observations(station_id FK, day, observed_at, temperature_c, humidity_pct, pressure_hpa, wind_ms, rain_prev_mm)`. Clé primaire de l’observation : `(station_id, day)`. Une station a 0..N observations ; chaque observation appartient à une seule station. L’index sur `day` facilite les filtres temporels. Aucune donnée personnelle d’agriculteur n’est nécessaire.
