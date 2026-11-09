"""Test réel de Streamlit et FastAPI dans le même environnement réseau."""
import threading
import time
from pathlib import Path
import uvicorn
from streamlit.testing.v1 import AppTest
from goutte.api import app

def test_streamlit_calls_real_api(monkeypatch):
    monkeypatch.setenv('GOUTTE_API_URL', 'http://127.0.0.1:18765')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18765, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        assert server.started
        at = AppTest.from_file(Path(__file__).resolve().parents[1] / 'streamlit_app.py', default_timeout=20).run()
        assert not at.exception and not at.error
        at.button[0].click().run()
        assert not at.exception and len(at.metric) == 1
        at.selectbox[0].set_value('07130').run()
        at.button[0].click().run()
        assert not at.exception and len(at.metric) == 1
        # Même résultat retrouvé après changement de station et nouvelle requête.
        assert any('Probabilité' in item.label for item in at.metric)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
