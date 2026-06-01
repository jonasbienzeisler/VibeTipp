from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app import config as cfg

app = create_app()

if __name__ == '__main__':
    debug = cfg.SECRET_KEY == "change-me-in-production-please"
    app.run(debug=debug, host='0.0.0.0', port=cfg.PORT)
