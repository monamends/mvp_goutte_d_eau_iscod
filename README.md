# Projet Goutte d’eau — MVP Bretagne

MVP Python complet : collecte d’observations SYNOP réelles par API, nettoyage et stockage SQLite, entraînement scikit-learn, évaluation chronologique, API FastAPI et interface Streamlit.

Ce prototype estime la probabilité d’un cumul **≥ 1 mm sur 24 h**, pour **Brest (07110)** ou **Rennes (07130)**. La date demandée est la **fin de la période à 06 h UTC** ; les variables proviennent de la veille à 06 h UTC. Il ne prévoit ni la quantité de pluie, ni les orages, ni un risque à l’échelle d’une parcelle. Aucun jeu synthétique n’est utilisé pour les scores livrés.

## Démarrer sur Windows avec Anaconda

1. Extraire tout le ZIP dans un dossier, par exemple `Documents\GoutteEau`. Ne pas lancer depuis l’archive.
2. Ouvrir **Anaconda Prompt**, se placer dans le dossier contenant ce README et créer l’environnement :

```bat
conda create -n goutte-eau python=3.12 -y
conda activate goutte-eau
python -m pip install -r requirements.txt
python -m pytest -q
```

3. Les données SQLite et le modèle entraîné sont inclus. La première démonstration ne nécessite aucun téléchargement météo ni nouvelle phase d’entraînement. Dans ce premier terminal :

```bat
python -m uvicorn goutte.api:app --host 127.0.0.1 --port 8000
```

4. Ouvrir un **second Anaconda Prompt**, revenir dans le même dossier, puis :

```bat
conda activate goutte-eau
python -m streamlit run streamlit_app.py
```

5. Ouvrir `http://localhost:8501`, choisir une station et une date, puis cliquer sur **Estimer le risque de pluie**. La documentation interactive FastAPI est disponible sur `http://127.0.0.1:8000/docs`.

Pour arrêter : `Ctrl+C` dans chacun des deux terminaux. Les deux fichiers `.bat` fournis lancent les services si le bon environnement Python est déjà activé.

## Reproduire la collecte et l’entraînement

```bat
python -m goutte.collect --start 2020-01-01 --end 2026-11-04
python -m goutte.train
python -m pytest -q
```

La fin est **exclusive**. Les exports par année sont mis en cache. Ajouter `--refresh` uniquement pour recontacter la source sur les mêmes périodes. Une erreur de réseau n’est jamais remplacée silencieusement par de fausses données. Lancer la collecte avant le service ou dans une fenêtre de maintenance, puis redémarrer l’API après changement de modèle. Le modèle est chargé une fois au démarrage.

La dernière observation incluse est datée du **3 novembre 2026**. La démonstration permet donc au plus d’estimer la fenêtre se terminant le **4 novembre 2026**. Une demande au 9 novembre 2026 est refusée si les observations du 8 sont absentes. Les dates antérieures à 2025 sont également refusées par l’API, pour réserver la démonstration à une période hors entraînement et sélection.

**Important sur l’horaire :** 06 h UTC est l’horodatage des mesures. L’archive ne fournit pas l’historique de leur disponibilité réelle. Le rejeu ne reproduit donc pas la latence de publication. Une exploitation opérationnelle devra enregistrer `received_at`, attendre les observations publiées et définir une fenêtre de prévision compatible avec ce délai.

## Données et traçabilité

- Région : Bretagne, code 53 ; deux stations officielles SYNOP, pas toute la région maillée.
- Producteur : Météo-France ; diffusion via l’API publique du jeu Opendatasoft `donnees-synop-essentielles-omm`.
- Le lien Infoclimat de l’énoncé a été analysé : les requêtes automatiques exigent un compte/une clé et les licences dépendent des stations. Le MVP utilise un autre accès public au **même réseau SYNOP**, sans inventer de clé Infoclimat.
- Attribution : Météo-France, observations SYNOP ; redistribution selon la licence indiquée dans `data/source_metadata.json` et la fiche du producteur. L’extrait de données est distinct du code du projet.
- Provenance : `data/provenance.json`, requêtes, empreintes SHA-256, fichiers bruts et données nettoyées.
- Base : `data/weather.sqlite` ; `stations` et `observations` avec clé composite `(station_id, day)`, FK et contrôles de valeurs.
- Température K → °C ; pression Pa → hPa ; pluie en mm ; vent en m/s ; humidité en %.
- Valeurs invalides ou négatives de pluie : manquantes, jamais transformées en jour sec. Pas d’imputation de cible. Au moins trois variables météo observées pour entraîner/prédire.
- Les précipitations `rr24` du jour cible servent **seulement à la cible**, jamais aux variables explicatives de ce même jour cible.

## Évaluation et résultats

Entraînement 2020–2023 ; validation 2024 pour choisir entre régression logistique et forêt aléatoire puis fixer le seuil ; test final 2025–novembre 2026. Toutes les stations sont séparées selon les mêmes dates. L’imputation, l’encodage et la normalisation sont appris uniquement sur l’entraînement.

La forêt aléatoire retenue comporte 150 arbres, profondeur maximale 8, au moins 15 observations par feuille et un seul cœur. Le seuil est choisi sur la validation pour maximiser F2 (poids plus fort aux pluies manquées). Cette règle est une hypothèse métier à discuter avec les agriculteurs.

Résultats exacts et datés : `artifacts/metrics.json`. Prédictions du test : `artifacts/test_predictions.csv`. Les scores des références sont fournis. Les conclusions sont limitées à deux stations et à un rejeu historique. Les probabilités ne sont pas une garantie individuelle ni une mesure de gravité d’un événement.

## API

| Route | Usage |
|---|---|
| `GET /health` | Vérifie la présence de la base et du modèle |
| `GET /stations` | Stations couvertes et dernière observation |
| `GET /availability?station_id=07110` | Dates réellement calculables |
| `GET /predict?date=2026-11-04&station_id=07110` | Probabilité et contexte temporel |
| `GET /metrics` | Résultats d’évaluation figés |
| `GET /docs` | Documentation OpenAPI |

Erreurs : 404 station inconnue ; 422 date incorrecte, période hors périmètre, observation absente ou données insuffisantes ; 503 base/modèle absent. L’API n’entraîne pas le modèle pendant une requête.

Exemple PowerShell :

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/predict?date=2026-11-04&station_id=07110'
```

Les paramètres sont validés ; aucun nom de table ni requête SQL n’est accepté depuis l’utilisateur. Le prototype est lié à `127.0.0.1`, pour une démonstration locale. Avant exposition : TLS/reverse proxy, authentification si nécessaire, quotas, supervision, sauvegardes, gestion des secrets et revue de sécurité. Ne charger que des fichiers `joblib` de confiance.

## Structure et documentation

`goutte/collect.py` collecte ; `data.py` nettoie et stocke ; `train.py` entraîne et évalue ; `api.py` sert les prévisions ; `streamlit_app.py` appelle FastAPI. `tests/` couvre les contrats API, l’idempotence, les conversions, les trous calendaires et la séparation temporelle. `docs/` contient les diagrammes, la fiche modèle et le rapport explicatif Word.


## Accessibilité et sobriété

Interface en une colonne, champs nommés, résultat chiffré et textuel, aucun sens porté par la seule couleur, composants standards et thème contrasté. Tester avant une production le clavier, le lecteur d’écran, le zoom à 200 % et les erreurs annoncées. L’AppTest valide le comportement fonctionnel, pas une conformité RGAA complète.

Un seul petit modèle CPU, sept fichiers annuels en cache, huit champs sources et deux stations. Pas de deep learning, GPU, carte animée ni entraînement à chaque clic. Démonstration locale sans hébergement permanent ; étude comparée des hébergeurs et recommandations de production dans le rapport.

