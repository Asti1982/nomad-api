"""Entry point for hosts that default to `python app.py` (e.g. Render).

The HTTP server implementation lives in `nomad_api.py`; this module delegates to it.
On Render, prefer deploying the web service with `runtime: docker` so `Dockerfile`
runs `pip install -r requirements.txt` during the image build.
"""

from nomad_api import serve

if __name__ == "__main__":
    serve()
