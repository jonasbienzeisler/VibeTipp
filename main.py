from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app import config as cfg

app = create_app()

if __name__ == '__main__':
    debug = cfg.SECRET_KEY == "change-me-in-production-please"
    if debug:
        # Local development: Flask reloader + debugger.
        app.run(debug=True, host='0.0.0.0', port=cfg.PORT)
    else:
        # Production: a real WSGI server. The werkzeug dev server speaks HTTP/1.0
        # and closes every connection (Connection: close), so each htmx poll opens a
        # fresh TCP socket — under the knockout-stage polling load that exhausts the
        # client's ephemeral ports (net::ERR_ADDRESS_IN_USE). waitress keeps
        # connections alive (HTTP/1.1) and serves requests from a bounded thread pool.
        from waitress import serve
        print(f" * VibeTipp serving via waitress on 0.0.0.0:{cfg.PORT}", flush=True)
        serve(app, host='0.0.0.0', port=cfg.PORT, threads=8, channel_timeout=120)
