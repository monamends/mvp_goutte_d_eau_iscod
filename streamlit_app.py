"""L'interface appelle réellement FastAPI ; aucun deuxième modèle embarqué."""
import os
import httpx
import streamlit as st

API = os.getenv('GOUTTE_API_URL', 'http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title="Goutte d'eau", page_icon='🌧', layout='centered')
st.title("Goutte d’eau")
st.write('Estimer le risque de pluie en Bretagne — prototype pour les agriculteurs')
st.info('Démonstration sur observations SYNOP réelles. Les dates passées servent au rejeu historique. '
        'Le modèle estime la probabilité d’au moins 1 mm sur 24 h ; il ne prédit pas les quantités.')

@st.cache_data(ttl=60)
def get_json(endpoint, params=None):
    # Connexion serveur à serveur. trust_env=False pour ne pas proxifier localhost.
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.get(API + endpoint, params=params)
        response.raise_for_status()
        return response.json()

try:
    stations = get_json('/stations')
    labels = {s['station_id']: s['name'] for s in stations}
    station = st.selectbox('Station météo de référence', list(labels), format_func=labels.get)
    dates = get_json('/availability', {'station_id': station})['dates']
    if not dates:
        st.warning('Aucune date admissible. Collecter des observations puis entraîner le modèle.')
        st.stop()
    # Sélecteur borné aux jours admissibles : les trous de collecte ne sont pas masqués.
    target = st.selectbox('Date de fin de la période de pluie en UTC', dates,
                          index=len(dates)-1, help='Période : 06 h UTC la veille à 06 h UTC ce jour.')
    st.caption('Source : Météo-France SYNOP via Opendatasoft. Dernière observation de cette station : '
               + next(s['latest_observation'] for s in stations if s['station_id'] == station))
    if st.button('Estimer le risque de pluie', type='primary'):
        result = get_json('/predict', {'date': target, 'station_id': station})
        st.metric('Probabilité d’au moins 1 mm de pluie', f"{result['probability']:.1%}")
        st.write('**Décision au seuil du prototype :** ' +
                 ('pluie possible, vigilance dans la planification.' if result['rain_expected']
                  else 'risque sous le seuil ; la pluie reste possible.'))
        st.write('**Fenêtre évaluée :** ' + result['target_window_utc'])
        st.write('**Observations arrêtées à :** ' + result['observation_cutoff_utc'])
        st.write(f"**Seuil de décision :** {result['threshold']:.0%} — choisi sur la validation 2024.")
        if result['retrospective']:
            st.warning('Rejeu historique : ce résultat n’est pas une prévision du jour.')
        st.caption(result['warning'])
    with st.expander('Qualité mesurée sur la période de test'):
        m = get_json('/metrics')
        st.write('Modèle retenu : ' + m['selected_model'])
        st.write('Période de test : ' + m['splits']['test']['from'] + ' au ' + m['splits']['test']['to'])
        st.write({'Brier (plus bas = meilleur)': round(m['test']['brier'], 3),
                  'Brier référence saisonnière': round(m['baseline_seasonal_test']['brier'], 3),
                  'Rappel pluie': round(m['test']['recall'], 3),
                  'Précision pluie': round(m['test']['precision'], 3)})
except httpx.HTTPStatusError as exc:
    try:
        detail = exc.response.json().get('detail', 'Erreur API')
    except ValueError:
        detail = 'Réponse API invalide.'
    st.error(f'La demande ne peut pas être traitée : {detail}')
except (httpx.HTTPError, KeyError, ValueError):
    st.error('API indisponible. Démarrer FastAPI dans un premier terminal, puis relancer cette page.')
