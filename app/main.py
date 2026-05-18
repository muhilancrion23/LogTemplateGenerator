from flask import Flask
from flask_cors import CORS

from app.config import Config
from app.routes.upload_routes import upload_blueprint
from app.utils.logging_utils import setup_logging


def create_app() -> Flask:
    """Application factory — creates and configures Flask."""

    # Logging first so everything below is captured
    setup_logging(debug=Config.DEBUG)

    Config.ensure_directories()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    # Core config
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = (
        Config.MAX_CONTENT_LENGTH
    )
    app.config["DEBUG"] = Config.DEBUG

    # CORS (restrict origins in production)
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Blueprints
    app.register_blueprint(upload_blueprint)

    return app