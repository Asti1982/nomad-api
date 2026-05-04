"""Entry point for hosts that default to `python app.py` (e.g. some Render setups).

The canonical Nomad HTTP server lives in `nomad_api.py`; this module only delegates.
"""

from nomad_api import serve

if __name__ == "__main__":
    serve()
