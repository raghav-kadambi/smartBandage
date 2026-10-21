"""Run the web app with the mobile API mounted, reachable from a phone on the same Wi-Fi.

    python mobile_server.py

app.py is imported unchanged; this only adds the /api/m blueprint and listens on 0.0.0.0.
"""

from app import GROQ_MODEL, app, groq_client
from mobile_api import init_mobile_api
from rag_service import rag_service

init_mobile_api(app, groq_client, GROQ_MODEL, rag_service)

if __name__ == "__main__":
    # debug=False: the reloader would index the literature twice and Flask's debugger
    # must not be exposed on a LAN interface.
    app.run(host="0.0.0.0", port=5000, debug=False)
