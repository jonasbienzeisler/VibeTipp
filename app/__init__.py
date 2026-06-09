from datetime import timedelta
from flask import Flask
from app import config
from app.repositories.users import UserRepository
from app.repositories.matches import MatchRepository
from app.repositories.tips import TipRepository
from app.repositories.results import ResultRepository
from app.repositories.snapshots import SnapshotRepository
from app.repositories.audit import AuditLog
from app.repositories.adjustments import AdjustmentsRepository
from app.repositories.player_results import PlayerResultsWriter
from app.repositories.world_cup_picks import WorldCupPicksRepository


def create_app(data_dir=None, secret_key=None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    _data_dir = data_dir or config.DATA_DIR
    _data_dir.mkdir(parents=True, exist_ok=True)

    app.secret_key = secret_key or config.SECRET_KEY
    app.permanent_session_lifetime = timedelta(hours=config.SESSION_LIFETIME_HOURS)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    app.config["DATA_DIR"] = _data_dir
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Repositories stored on app
    app.user_repo = UserRepository(_data_dir)
    app.match_repo = MatchRepository(_data_dir)
    app.tip_repo = TipRepository(_data_dir)
    app.result_repo = ResultRepository(_data_dir)
    app.snapshot_repo = SnapshotRepository(_data_dir)
    app.audit = AuditLog(_data_dir)
    app.adj_repo = AdjustmentsRepository(_data_dir)
    app.player_results_writer = PlayerResultsWriter(_data_dir)
    app.wc_pick_repo = WorldCupPicksRepository(_data_dir)

    from app.routes.auth import bp as auth_bp
    from app.routes.main import bp as main_bp
    from app.routes.tips import bp as tips_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.api import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(tips_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    _MD_LABELS = {
        1: "VR1", 2: "VR2", 3: "VR3",
        4: "16EL", 5: "AF", 6: "VF", 7: "HF", 8: "P3", 9: "F",
    }
    _MD_FULLNAMES = {
        1: "Vorrunde 1", 2: "Vorrunde 2", 3: "Vorrunde 3",
        4: "Sechzehntelfinale", 5: "Achtelfinale", 6: "Viertelfinale",
        7: "Halbfinale", 8: "Spiel um Platz 3", 9: "Finale",
    }

    @app.context_processor
    def inject_nav():
        from flask import request as _req
        matchdays = app.match_repo.matchdays()
        current = app.match_repo.current_matchday()
        # 3 nearest: current-1, current, current+1
        if matchdays:
            idx = matchdays.index(current) if current in matchdays else 0
            start = max(0, idx - 1)
            end = min(len(matchdays), start + 3)
            start = max(0, end - 3)
            visible = matchdays[start:end]
        else:
            visible = []
        return {
            "matchdays": matchdays,
            "current_matchday_num": current,
            "nav_visible_matchdays": visible,
        }

    @app.template_filter("matchday_label")
    def matchday_label_filter(md: int) -> str:
        return _MD_LABELS.get(md, f"ST{md}")

    @app.template_filter("matchday_fullname")
    def matchday_fullname_filter(md: int) -> str:
        return _MD_FULLNAMES.get(md, f"Spieltag {md}")

    @app.template_filter("tendenz_label")
    def tendenz_label(t: str) -> str:
        return {"home": "Heimsieg", "draw": "Unentschieden", "away": "Auswärtssieg"}.get(t, t)

    @app.template_filter("pts_fmt")
    def pts_fmt(v) -> str:
        try:
            f = float(v)
            return f"{f:+.1f}" if f != 0 else "0"
        except (TypeError, ValueError):
            return str(v)

    return app
