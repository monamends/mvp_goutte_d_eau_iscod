# Fiche modèle

Usage : démonstration pédagogique d’un risque de pluie pour Brest et Rennes. Événement positif : cumul SYNOP rr24 ≥ 1 mm à 06 h UTC du jour cible. Variables : météo de la veille à 06 h, station et saisonnalité sin/cos du jour cible. L’historique de disponibilité des mesures n’est pas connu ; il s’agit d’une évaluation rétrospective.

Choix : régression logistique et forêt aléatoire limitées comparées sur validation 2024 selon Brier. Seuil fixé sur F2 de validation. Test 2025+ réservé à l’évaluation finale. Pas de recherche massive d’hyperparamètres, pas de deep learning. Le modèle servi n’est pas réentraîné sur le test après publication des scores.

Limites : deux stations, données manquantes, décalage possible de régime climatique, dépendance entre jours et stations, granularité insuffisante pour une parcelle, pas de modèle d’intensité ni d’extrêmes. Les mêmes observations appartiennent au même découpage temporel quelle que soit la station. Le score ne permet pas de généraliser aux stations jamais vues.

Le seuil de 20 % retenu sur cette validation favorise fortement le rappel et augmente les fausses alertes. Une probabilité de 21 % n’est pas une certitude qu’il pleuvra. La courbe de calibration est fournie dans les métriques ; Brier ne mesure pas à lui seul la calibration. Une réévaluation par saison et un pilote métier sont requis avant usage agricole réel.

Exploitation : dérive de performance à comparer à la référence saisonnière, présence des deux classes, fraîcheur des données, taux de trous calendaires, latence API et taille du modèle. Réentraînement trimestriel à confirmer selon la dérive, validation chronologique préalable et version précédente conservée. Aucune mesure carbone n’est déduite du seul temps d’entraînement.
