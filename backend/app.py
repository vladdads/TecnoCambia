import os
import re
import ssl
import smtplib
import uuid
import sqlite3
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import timedelta
from datetime import datetime, timezone, timedelta as td

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    send_from_directory,
    send_file,
    jsonify,
    abort,
)
from urllib.parse import quote
from email.message import EmailMessage
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename, safe_join


BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", encoding="utf-8")
except ImportError:
    pass

# En la nube: monta un disco persistente y define DATA_DIR=/var/data (Render, etc.)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
DB_PATH = DATA_DIR / "db" / "tecnocambia.sqlite"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
UPLOADS_DIR = DATA_DIR / "uploads"

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_DOC_TYPES = ALLOWED_TYPES.union({"application/pdf"})
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

PRESET_CATEGORIES = [
    "Celulares",
    "Computadoras",
    "Tablets",
    "Consolas y videojuegos",
    "Audio y bocinas",
    "Monitores",
    "Accesorios",
    "Componentes (PC)",
    "Impresoras",
    "Cámaras",
    "Redes (routers)",
    "Smartwatch y wearables",
    "TV y streaming",
    "Otros",
]


app = Flask(__name__, static_folder="public", static_url_path="/")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.permanent_session_lifetime = timedelta(days=14)
app.config["MAX_CONTENT_LENGTH"] = 6 * MAX_FILE_SIZE  # up to ~6 images
session_cookie_samesite = (os.environ.get("SESSION_COOKIE_SAMESITE") or "Lax").strip()
if session_cookie_samesite.lower() == "none":
    session_cookie_samesite = "None"
app.config["SESSION_COOKIE_SAMESITE"] = session_cookie_samesite
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_cors_allowed_origins = {
    o.strip().rstrip("/")
    for o in (os.environ.get("CORS_ALLOWED_ORIGINS") or "").split(",")
    if o.strip()
}
if not _cors_allowed_origins:
    frontend_origin = (os.environ.get("FRONTEND_ORIGIN") or "").strip().rstrip("/")
    if frontend_origin:
        _cors_allowed_origins.add(frontend_origin)

DEBUG = os.environ.get("FLASK_DEBUG", "1").strip() == "1"

if os.environ.get("TRUST_PROXY", "true").strip().lower() in ("1", "true", "yes", "on"):
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=500_000, backupCount=3, encoding="utf-8")
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# simple in-memory rate limits (dev-friendly)
_RATE = {}


@app.after_request
def apply_cors_headers(resp):
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    if origin and origin in _cors_allowed_origins:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        resp.headers["Vary"] = "Origin"
    return resp


def rate_limit(key: str, limit: int, window_sec: int) -> bool:
    now = time.time()
    bucket = _RATE.get(key)
    if not bucket or now - bucket["start"] > window_sec:
        _RATE[key] = {"start": now, "count": 1}
        return True
    if bucket["count"] >= limit:
        return False
    bucket["count"] += 1
    return True


def _mail_env_settings():
    return {
        "server": (os.environ.get("MAIL_SERVER") or "").strip(),
        "port": int(os.environ.get("MAIL_PORT", "587") or "587"),
        "username": (os.environ.get("MAIL_USERNAME") or "").strip(),
        "password": os.environ.get("MAIL_PASSWORD") or "",
        "sender": (os.environ.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_FROM") or "").strip(),
        "use_tls": os.environ.get("MAIL_USE_TLS", "true").strip().lower() in ("1", "true", "yes", "on"),
        "use_ssl": os.environ.get("MAIL_USE_SSL", "false").strip().lower() in ("1", "true", "yes", "on"),
    }


def mail_is_configured() -> bool:
    s = _mail_env_settings()
    return bool(s["server"] and s["sender"])


def mail_debug_mode() -> bool:
    """Solo desarrollo: sin SMTP, muestra el enlace de recuperación en la respuesta (MAIL_DEBUG=1)."""
    return os.environ.get("MAIL_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def public_reset_base_url() -> str:
    """URL pública del sitio (sin barra final). Enlace de recuperación: {base}/auth/reset/{token}"""
    explicit = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    return request.host_url.rstrip("/")


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    """Envía el correo con enlace de restablecimiento. Lanza excepción si falla SMTP."""
    s = _mail_env_settings()
    if not mail_is_configured():
        raise RuntimeError("SMTP no configurado.")
    msg = EmailMessage()
    msg["Subject"] = "Tecnocambia — restablecer contraseña"
    msg["From"] = s["sender"]
    msg["To"] = to_email
    msg.set_content(
        "Hola,\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta en Tecnocambia.\n\n"
        f"Abre este enlace (válido aproximadamente 30 minutos):\n{reset_url}\n\n"
        "Si tú no pediste este cambio, puedes ignorar este correo.\n\n"
        "— Tecnocambia\n"
    )
    app.logger.info("SMTP: enviando recuperación de contraseña a %s", to_email)
    if s["use_ssl"]:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(s["server"], s["port"], context=ctx) as smtp:
            if s["username"]:
                smtp.login(s["username"], s["password"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s["server"], s["port"]) as smtp:
            if s["use_tls"]:
                smtp.starttls(context=ssl.create_default_context())
            if s["username"]:
                smtp.login(s["username"], s["password"])
            smtp.send_message(msg)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        apply_migrations(db)


def _has_column(db: sqlite3.Connection, table: str, column: str) -> bool:
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _has_table(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return bool(row)


def apply_migrations(db: sqlite3.Connection) -> None:
    # Columns added after initial release
    if _has_table(db, "users") and not _has_column(db, "users", "is_admin"):
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    if _has_table(db, "products"):
        if not _has_column(db, "products", "brand"):
            db.execute("ALTER TABLE products ADD COLUMN brand TEXT")
        if not _has_column(db, "products", "model"):
            db.execute("ALTER TABLE products ADD COLUMN model TEXT")
        if not _has_column(db, "products", "year"):
            db.execute("ALTER TABLE products ADD COLUMN year INTEGER")
        if not _has_column(db, "products", "accessories"):
            db.execute("ALTER TABLE products ADD COLUMN accessories TEXT")
        if not _has_column(db, "products", "reserved_by"):
            db.execute("ALTER TABLE products ADD COLUMN reserved_by INTEGER")
        if not _has_column(db, "products", "reserved_at"):
            db.execute("ALTER TABLE products ADD COLUMN reserved_at TEXT")

    if _has_table(db, "product_images") and not _has_column(db, "product_images", "is_cover"):
        db.execute("ALTER TABLE product_images ADD COLUMN is_cover INTEGER NOT NULL DEFAULT 0")

    if _has_table(db, "users"):
        if not _has_column(db, "users", "identity_verification_status"):
            db.execute(
                "ALTER TABLE users ADD COLUMN identity_verification_status TEXT NOT NULL DEFAULT 'verified'"
            )
        if not _has_column(db, "users", "curp"):
            db.execute("ALTER TABLE users ADD COLUMN curp TEXT")
        if not _has_column(db, "users", "ine_image_filename"):
            db.execute("ALTER TABLE users ADD COLUMN ine_image_filename TEXT")
        if not _has_column(db, "users", "curp_document_filename"):
            db.execute("ALTER TABLE users ADD COLUMN curp_document_filename TEXT")

    # Tables created after initial release (for pre-existing DBs)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_reads (
          conversation_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          last_read_message_id INTEGER,
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY (conversation_id, user_id),
          FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS message_images (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          message_id INTEGER NOT NULL,
          filename TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
          user_id INTEGER NOT NULL,
          product_id INTEGER NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY (user_id, product_id),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_searches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          query_string TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS viewed_products (
          user_id INTEGER NOT NULL,
          product_id INTEGER NOT NULL,
          last_viewed_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY (user_id, product_id),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          reporter_id INTEGER NOT NULL,
          product_id INTEGER,
          reported_user_id INTEGER,
          reason TEXT NOT NULL,
          details TEXT,
          status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','reviewed','closed')),
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
          FOREIGN KEY (reported_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS blocks (
          blocker_id INTEGER NOT NULL,
          blocked_id INTEGER NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY (blocker_id, blocked_id),
          FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          reviewer_id INTEGER NOT NULL,
          reviewed_id INTEGER NOT NULL,
          product_id INTEGER NOT NULL,
          rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
          comment TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE (reviewer_id, reviewed_id, product_id),
          FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (reviewed_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          token TEXT NOT NULL UNIQUE,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )


def ensure_seed_data() -> None:
    with get_db() as db:
        c = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if c:
            return
        db.execute(
            """
            INSERT INTO users (name, email, password_hash, identity_verification_status)
            VALUES (?, ?, ?, 'verified')
            """,
            ("Tecnocambia Demo", "demo@tecnocambia.local", generate_password_hash("demo1234")),
        )
        db.execute("UPDATE users SET is_admin = 1 WHERE email = ?", ("demo@tecnocambia.local",))
        user_id = db.execute("SELECT id FROM users WHERE email = ?", ("demo@tecnocambia.local",)).fetchone()["id"]
        db.executemany(
            """
            INSERT INTO products
              (user_id, title, description, listing_type, price_cents, category, item_condition, location)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    user_id,
                    "Laptop Lenovo ThinkPad (para intercambio)",
                    "Funciona bien. Ideal para oficina/estudio. Busco intercambiar por una tablet o monitor. Incluye cargador.",
                    "exchange",
                    None,
                    "Computadoras",
                    "good",
                    "CDMX",
                ),
                (
                    user_id,
                    "iPhone 11 64GB",
                    "Buen estado, batería 82%. Incluye funda. Entrego en punto medio.",
                    "sale",
                    520000,
                    "Celulares",
                    "good",
                    "Guadalajara",
                ),
                (
                    user_id,
                    "Teclado mecánico (donación)",
                    "Le faltan dos keycaps, pero funciona. Lo dono para quien lo necesite.",
                    "donation",
                    0,
                    "Accesorios",
                    "fair",
                    "Monterrey",
                ),
            ],
        )


def money_from_cents(cents):
    if cents is None:
        return None
    mxn = cents / 100.0
    # lightweight formatting (avoid babel dependency)
    return f"${mxn:,.2f} MXN".replace(",", "X").replace(".", ",").replace("X", ".")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_curp(curp: str) -> str:
    return re.sub(r"\s+", "", (curp or "")).upper()


CURP_PATTERN = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]{2}$")


def curp_is_valid(curp: str) -> bool:
    c = normalize_curp(curp)
    if len(c) != 18:
        return False
    return bool(CURP_PATTERN.match(c))


def safe_next(next_url: str) -> str:
    if not next_url:
        return "/app/products"
    if isinstance(next_url, str) and next_url.startswith("/"):
        return next_url
    return "/app/products"


def require_auth():
    if not session.get("user_id"):
        return redirect(url_for("login", next=request.path))
    return None


def require_auth_next(next_url: str):
    if not session.get("user_id"):
        return redirect(url_for("login", next=next_url))
    return None


def current_user_row():
    return app.jinja_env.globals.get("current_user")


def is_admin():
    u = current_user_row()
    try:
        return bool(u and int(u["is_admin"]) == 1)
    except Exception:
        return False


def require_admin():
    r = require_auth()
    if r:
        return r
    if not is_admin():
        return render_template("404.html"), 404
    return None


def backup_db_path():
    bdir = BASE_DIR / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return bdir / f"tecnocambia-{ts}.sqlite"


@app.before_request
def load_current_user():
    app.jinja_env.globals["current_user"] = None
    uid = session.get("user_id")
    if not uid:
        return
    with get_db() as db:
        user = db.execute(
            "SELECT id, name, email, is_admin, created_at, identity_verification_status FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
        if user:
            app.jinja_env.globals["current_user"] = user


@app.context_processor
def inject_helpers():
    return {"money_from_cents": money_from_cents, "preset_categories": PRESET_CATEGORIES}


@app.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOADS_DIR, filename)


def _frontend_app_url(path: str = "/app/products") -> str | None:
    origin = (os.environ.get("FRONTEND_ORIGIN") or "").strip().rstrip("/")
    if not origin:
        return None
    if not path.startswith("/"):
        path = "/" + path
    return f"{origin}{path}"


@app.get("/")
def home():
    external = _frontend_app_url("/app/products")
    if external:
        return redirect(external)
    return jsonify({"ok": True, "service": "tecnocambia-api"}), 200


@app.get("/products")
def products():
    qs = request.query_string.decode()
    path = "/app/products" + ("?" + qs if qs else "")
    external = _frontend_app_url(path)
    if external:
        return redirect(external)
    return redirect(path)


@app.get("/products/<int:product_id>")
def product_detail_redirect(product_id: int):
    path = f"/app/products/{product_id}"
    external = _frontend_app_url(path)
    if external:
        return redirect(external)
    return redirect(path)


@app.get("/report")
def report():
    r = require_auth()
    if r:
        return r
    product_id = (request.args.get("product_id") or "").strip()
    user_id = (request.args.get("user_id") or "").strip()
    return render_template("report.html", error=None, productId=product_id, userId=user_id)


@app.post("/report")
def report_post():
    r = require_auth()
    if r:
        return r
    reason = (request.form.get("reason") or "").strip()
    details = (request.form.get("details") or "").strip()
    product_id = request.form.get("product_id") or None
    user_id = request.form.get("user_id") or None

    if not reason:
        return render_template("report.html", error="Escribe un motivo.", productId=product_id, userId=user_id), 400

    def to_int(x):
        try:
            return int(x)
        except Exception:
            return None

    pid = to_int(product_id)
    uid = to_int(user_id)

    with get_db() as db:
        db.execute(
            """
            INSERT INTO reports (reporter_id, product_id, reported_user_id, reason, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session["user_id"], pid, uid, reason[:120], details[:1000] or None),
        )
    return redirect("/app/products")


@app.post("/block/<int:user_id>")
def block_user(user_id: int):
    r = require_auth()
    if r:
        return r
    if user_id == session["user_id"]:
        return redirect("/app/products")
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO blocks (blocker_id, blocked_id) VALUES (?, ?)", (session["user_id"], user_id))
    return redirect("/app/products")


@app.post("/unblock/<int:user_id>")
def unblock_user(user_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        db.execute("DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?", (session["user_id"], user_id))
    return redirect("/app/products")


@app.get("/review/<int:product_id>")
def review(product_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        p = db.execute("SELECT id, user_id, title, status, reserved_by FROM products WHERE id = ?", (product_id,)).fetchone()
        if not p:
            return render_template("404.html"), 404
        uid = session["user_id"]
        if p["status"] != "completed":
            return render_template("404.html"), 404
        # allow only seller or reserved buyer to review each other
        if uid != p["user_id"] and uid != p["reserved_by"]:
            return render_template("404.html"), 404
        other = p["reserved_by"] if uid == p["user_id"] else p["user_id"]
        existing = db.execute(
            "SELECT 1 FROM reviews WHERE reviewer_id = ? AND reviewed_id = ? AND product_id = ?",
            (uid, other, product_id),
        ).fetchone()
        if existing:
            return redirect("/app/products")
    return render_template("review.html", error=None, product=p, reviewedId=other)


@app.post("/review/<int:product_id>")
def review_post(product_id: int):
    r = require_auth()
    if r:
        return r
    rating = (request.form.get("rating") or "").strip()
    comment = (request.form.get("comment") or "").strip()
    try:
        rating_i = int(rating)
    except Exception:
        rating_i = 0
    if rating_i < 1 or rating_i > 5:
        return render_template("review.html", error="Calificación inválida (1-5).", product={"id": product_id, "title": ""}, reviewedId=None), 400

    with get_db() as db:
        p = db.execute("SELECT id, user_id, title, status, reserved_by FROM products WHERE id = ?", (product_id,)).fetchone()
        if not p or p["status"] != "completed":
            return render_template("404.html"), 404
        uid = session["user_id"]
        if uid != p["user_id"] and uid != p["reserved_by"]:
            return render_template("404.html"), 404
        other = p["reserved_by"] if uid == p["user_id"] else p["user_id"]
        db.execute(
            """
            INSERT OR IGNORE INTO reviews (reviewer_id, reviewed_id, product_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uid, other, product_id, rating_i, comment[:600] or None),
        )
    return redirect("/app/products")


@app.post("/products/<int:product_id>/favorite")
def favorite_toggle(product_id: int):
    r = require_auth_next(f"/products/{product_id}")
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        exists = db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
            (uid, product_id),
        ).fetchone()
        if exists:
            db.execute("DELETE FROM favorites WHERE user_id = ? AND product_id = ?", (uid, product_id))
        else:
            db.execute("INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)", (uid, product_id))
    return redirect(f"/app/products/{product_id}")


@app.get("/me/favorites")
def my_favorites():
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        items = db.execute(
            """
            SELECT
              p.*,
              u.name AS seller_name,
              (
                SELECT filename FROM product_images
                WHERE product_id = p.id
                ORDER BY is_cover DESC, id ASC
                LIMIT 1
              ) AS cover_image
            FROM favorites f
            JOIN products p ON p.id = f.product_id
            JOIN users u ON u.id = p.user_id
            WHERE f.user_id = ? AND p.status = 'active'
            ORDER BY datetime(f.created_at) DESC
            """,
            (uid,),
        ).fetchall()
    return render_template("my_favorites.html", products=items)


@app.get("/me/viewed")
def my_viewed():
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        items = db.execute(
            """
            SELECT
              p.*,
              u.name AS seller_name,
              v.last_viewed_at,
              (
                SELECT filename FROM product_images
                WHERE product_id = p.id
                ORDER BY is_cover DESC, id ASC
                LIMIT 1
              ) AS cover_image
            FROM viewed_products v
            JOIN products p ON p.id = v.product_id
            JOIN users u ON u.id = p.user_id
            WHERE v.user_id = ?
            ORDER BY datetime(v.last_viewed_at) DESC
            LIMIT 80
            """,
            (uid,),
        ).fetchall()
    return render_template("my_viewed.html", products=items)


@app.post("/me/saved-searches")
def save_search():
    r = require_auth()
    if r:
        return r
    name = (request.form.get("name") or "").strip() or "Mi búsqueda"
    qs = (request.form.get("query_string") or "").strip()
    if not qs.startswith("q=") and not qs.startswith("type=") and not qs.startswith("category=") and not qs.startswith("sort="):
        # allow empty too
        qs = qs.lstrip("?")
    with get_db() as db:
        db.execute(
            "INSERT INTO saved_searches (user_id, name, query_string) VALUES (?, ?, ?)",
            (session["user_id"], name[:60], qs[:500]),
        )
    return redirect("/me/saved-searches")


@app.get("/me/saved-searches")
def my_saved_searches():
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM saved_searches WHERE user_id = ? ORDER BY datetime(created_at) DESC",
            (uid,),
        ).fetchall()
    return render_template("saved_searches.html", searches=rows)


@app.post("/me/saved-searches/<int:search_id>/delete")
def delete_saved_search(search_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        db.execute("DELETE FROM saved_searches WHERE id = ? AND user_id = ?", (search_id, session["user_id"]))
    return redirect("/me/saved-searches")


@app.post("/products/<int:product_id>/buy")
def buy_product(product_id: int):
    r = require_auth_next(f"/products/{product_id}")
    if r:
        return r

    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id = ? AND status='active'", (product_id,)).fetchone()
        if not product:
            return render_template("404.html"), 404
        if product["listing_type"] != "sale":
            return redirect(f"/app/products/{product_id}")
        if product["user_id"] == session["user_id"]:
            return redirect(f"/app/products/{product_id}")

        db.execute(
            """
            INSERT INTO offers (product_id, buyer_id, offer_type, amount_cents, status)
            VALUES (?, ?, 'buy', ?, 'pending')
            """,
            (product_id, session["user_id"], product["price_cents"]),
        )
    return redirect("/me/purchases")


@app.post("/products/<int:product_id>/offer")
def make_offer(product_id: int):
    r = require_auth_next(f"/products/{product_id}")
    if r:
        return r

    raw = (request.form.get("amount") or "").strip()
    try:
        norm = re.sub(r"[^0-9.,]", "", raw).replace(",", ".")
        value = float(norm) if norm else 0.0
        amount_cents = int(round(value * 100))
    except Exception:
        amount_cents = -1

    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id = ? AND status='active'", (product_id,)).fetchone()
        if not product:
            return render_template("404.html"), 404
        if product["listing_type"] != "sale":
            return redirect(f"/app/products/{product_id}")
        if product["user_id"] == session["user_id"]:
            return redirect(f"/app/products/{product_id}")
        if amount_cents <= 0:
            return redirect(f"/app/products/{product_id}")

        db.execute(
            """
            INSERT INTO offers (product_id, buyer_id, offer_type, amount_cents, status)
            VALUES (?, ?, 'offer', ?, 'pending')
            """,
            (product_id, session["user_id"], amount_cents),
        )

    return redirect("/me/purchases")


@app.get("/messages")
def messages():
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
              c.*,
              p.title AS product_title,
              (
                SELECT filename FROM product_images
                WHERE product_id = p.id
                ORDER BY is_cover DESC, id ASC
                LIMIT 1
              ) AS cover_image,
              bu.name AS buyer_name,
              su.name AS seller_name,
              (SELECT body FROM messages m WHERE m.conversation_id = c.id ORDER BY datetime(m.created_at) DESC, m.id DESC LIMIT 1) AS last_message,
              (SELECT created_at FROM messages m WHERE m.conversation_id = c.id ORDER BY datetime(m.created_at) DESC, m.id DESC LIMIT 1) AS last_message_at,
              (SELECT MAX(id) FROM messages m WHERE m.conversation_id = c.id) AS last_message_id,
              (SELECT last_read_message_id FROM conversation_reads cr WHERE cr.conversation_id = c.id AND cr.user_id = ?) AS last_read_message_id
            FROM conversations c
            JOIN products p ON p.id = c.product_id
            JOIN users bu ON bu.id = c.buyer_id
            JOIN users su ON su.id = c.seller_id
            WHERE c.buyer_id = ? OR c.seller_id = ?
            ORDER BY datetime(COALESCE(last_message_at, c.created_at)) DESC
            """,
            (uid, uid, uid),
        ).fetchall()
    return render_template("messages.html", conversations=rows)


@app.get("/messages/new/<int:product_id>")
def new_message(product_id: int):
    r = require_auth_next(f"/products/{product_id}")
    if r:
        return r

    uid = session["user_id"]
    with get_db() as db:
        product = db.execute("SELECT id, user_id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            return render_template("404.html"), 404
        if product["user_id"] == uid:
            return redirect(f"/app/products/{product_id}")

        seller_id = product["user_id"]
        conv = db.execute(
            """
            SELECT id FROM conversations
            WHERE product_id = ? AND buyer_id = ? AND seller_id = ?
            """,
            (product_id, uid, seller_id),
        ).fetchone()
        if conv:
            conv_id = conv["id"]
        else:
            cur = db.execute(
                """
                INSERT INTO conversations (product_id, buyer_id, seller_id)
                VALUES (?, ?, ?)
                """,
                (product_id, uid, seller_id),
            )
            conv_id = cur.lastrowid

    return redirect(f"/messages/{conv_id}")


@app.get("/messages/<int:conversation_id>")
def conversation(conversation_id: int):
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        conv = db.execute(
            """
            SELECT
              c.*,
              p.title AS product_title,
              (
                SELECT filename FROM product_images
                WHERE product_id = p.id
                ORDER BY is_cover DESC, id ASC
                LIMIT 1
              ) AS cover_image,
              bu.name AS buyer_name,
              su.name AS seller_name
            FROM conversations c
            JOIN products p ON p.id = c.product_id
            JOIN users bu ON bu.id = c.buyer_id
            JOIN users su ON su.id = c.seller_id
            WHERE c.id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if not conv or (conv["buyer_id"] != uid and conv["seller_id"] != uid):
            return render_template("404.html"), 404

        msgs = db.execute(
            """
            SELECT m.*, u.name AS sender_name
            FROM messages m
            JOIN users u ON u.id = m.sender_id
            WHERE m.conversation_id = ?
            ORDER BY datetime(m.created_at) ASC, m.id ASC
            """,
            (conversation_id,),
        ).fetchall()

        msg_ids = [m["id"] for m in msgs]
        images_by_msg = {}
        if msg_ids:
            qmarks = ",".join(["?"] * len(msg_ids))
            rows = db.execute(
                f"SELECT message_id, filename FROM message_images WHERE message_id IN ({qmarks}) ORDER BY id ASC",
                msg_ids,
            ).fetchall()
            for r in rows:
                images_by_msg.setdefault(r["message_id"], []).append(r["filename"])

        # mark read up to latest message
        last_id = msgs[-1]["id"] if msgs else None
        if last_id:
            db.execute(
                """
                INSERT INTO conversation_reads (conversation_id, user_id, last_read_message_id)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id, user_id) DO UPDATE SET
                  last_read_message_id=excluded.last_read_message_id,
                  updated_at=datetime('now')
                """,
                (conversation_id, uid, last_id),
            )

    return render_template("conversation.html", conv=conv, messages=msgs, imagesByMsg=images_by_msg)


@app.post("/messages/<int:conversation_id>")
def conversation_post(conversation_id: int):
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    body = (request.form.get("body") or "").strip()
    if not body:
        return redirect(f"/messages/{conversation_id}")

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"chat:{ip}", limit=20, window_sec=60):
        return redirect(f"/messages/{conversation_id}")

    with get_db() as db:
        conv = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not conv or (conv["buyer_id"] != uid and conv["seller_id"] != uid):
            return render_template("404.html"), 404
        cur = db.execute(
            "INSERT INTO messages (conversation_id, sender_id, body) VALUES (?, ?, ?)",
            (conversation_id, uid, body),
        )
        msg_id = cur.lastrowid

        files = request.files.getlist("images") if request.files else []
        try:
            imgs = _save_images(files[:3]) if files else []
        except Exception:
            imgs = []
        for fn in imgs:
            db.execute("INSERT INTO message_images (message_id, filename) VALUES (?, ?)", (msg_id, fn))

        db.execute(
            """
            INSERT INTO conversation_reads (conversation_id, user_id, last_read_message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(conversation_id, user_id) DO UPDATE SET
              last_read_message_id=excluded.last_read_message_id,
              updated_at=datetime('now')
            """,
            (conversation_id, uid, msg_id),
        )
    return redirect(f"/messages/{conversation_id}")


@app.get("/auth/login")
def login():
    n = request.args.get("next", "")
    return redirect("/app/login" + ("?next=" + quote(n, safe="") if n else ""))


@app.post("/auth/login")
def login_post():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"login:{ip}", limit=8, window_sec=60):
        return (
            render_template(
                "auth_login.html",
                error="Demasiados intentos. Intenta en 1 minuto.",
                next=safe_next(request.form.get("next", "")),
            ),
            429,
        )

    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    next_url = safe_next(request.form.get("next", ""))

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("auth_login.html", error="Credenciales inválidas.", next=next_url), 401

    session["user_id"] = user["id"]
    session.permanent = True
    return redirect(next_url)


@app.get("/auth/register")
def register():
    n = request.args.get("next", "")
    return redirect("/app/register" + ("?next=" + quote(n, safe="") if n else ""))


@app.post("/auth/register")
def register_post():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"register:{ip}", limit=6, window_sec=60):
        return (
            render_template(
                "auth_register.html",
                error="Demasiados intentos. Intenta en 1 minuto.",
                next=safe_next(request.form.get("next", "")),
            ),
            429,
        )

    name = (request.form.get("name") or "").strip()
    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    curp_raw = request.form.get("curp", "")
    curp_norm = normalize_curp(curp_raw)
    next_url = safe_next(request.form.get("next", ""))

    if not name or not email or len(password) < 6:
        return (
            render_template(
                "auth_register.html",
                error="Completa nombre, email y una contraseña de al menos 6 caracteres.",
                next=next_url,
            ),
            400,
        )
    if not curp_is_valid(curp_norm):
        return (
            render_template(
                "auth_register.html",
                error="CURP inválida. Verifica los 18 caracteres.",
                next=next_url,
            ),
            400,
        )

    ine_f = request.files.get("ine_photo")
    try:
        ine_fn = _save_verification_image(ine_f, "credencial INE (frente)")
    except ValueError as e:
        return render_template("auth_register.html", error=str(e), next=next_url), 400

    with get_db() as db:
        exists = db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            return render_template("auth_register.html", error="Ese email ya está registrado.", next=next_url), 409
        dup_curp = db.execute(
            "SELECT 1 FROM users WHERE curp = ? AND curp IS NOT NULL",
            (curp_norm,),
        ).fetchone()
        if dup_curp:
            try:
                (UPLOADS_DIR / ine_fn).unlink(missing_ok=True)
            except Exception:
                pass
            return render_template("auth_register.html", error="Esa CURP ya está registrada.", next=next_url), 409
        db.execute(
            """
            INSERT INTO users
              (name, email, password_hash, curp, ine_image_filename, curp_document_filename, identity_verification_status)
            VALUES (?, ?, ?, ?, ?, NULL, 'pending')
            """,
            (name, email, generate_password_hash(password), curp_norm, ine_fn),
        )
        user_id = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]

    session["user_id"] = user_id
    session.permanent = True
    return redirect(next_url)


@app.post("/auth/logout")
def logout():
    session.clear()
    return redirect("/app/products")


@app.get("/auth/forgot")
def forgot_password():
    return render_template(
        "auth_forgot.html",
        error=None,
        info=None,
        mail_configured=mail_is_configured(),
        mail_debug=mail_debug_mode(),
    )


@app.post("/auth/forgot")
def forgot_password_post():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"forgot:{ip}", limit=5, window_sec=60):
        return (
            render_template(
                "auth_forgot.html",
                error="Demasiados intentos. Intenta en 1 minuto.",
                info=None,
                mail_configured=mail_is_configured(),
                mail_debug=mail_debug_mode(),
            ),
            429,
        )

    email = normalize_email(request.form.get("email", ""))
    if not email:
        return (
            render_template(
                "auth_forgot.html",
                error="Escribe tu email.",
                info=None,
                mail_configured=mail_is_configured(),
                mail_debug=mail_debug_mode(),
            ),
            400,
        )

    token = uuid.uuid4().hex
    expires_at = (datetime.now(timezone.utc) + td(minutes=30)).isoformat(timespec="seconds")
    reset_url = f"{public_reset_base_url()}/auth/reset/{token}"

    with get_db() as db:
        user = db.execute("SELECT id, email FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            cur = db.execute(
                "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user["id"], token, expires_at),
            )
            reset_row_id = cur.lastrowid

            if not mail_is_configured():
                if mail_debug_mode():
                    app.logger.warning("MAIL_DEBUG: enlace de recuperación para %s: %s", email, reset_url)
                    return (
                        render_template(
                            "auth_forgot.html",
                            error=None,
                            info=(
                                "Modo desarrollo (MAIL_DEBUG=1): no se envía correo. "
                                "Abre este enlace para restablecer tu contraseña (válido unos 30 minutos):\n\n"
                                f"{reset_url}\n\n"
                                "En producción usa SMTP (variables MAIL_*) y desactiva MAIL_DEBUG."
                            ),
                            mail_configured=False,
                            mail_debug=True,
                        ),
                        200,
                    )
                db.execute("DELETE FROM password_resets WHERE id = ?", (reset_row_id,))
                app.logger.warning(
                    "Recuperación de contraseña sin SMTP configurado. Enlace que se habría enviado a %s: %s",
                    email,
                    reset_url,
                )
                return (
                    render_template(
                        "auth_forgot.html",
                        error=(
                            "El servidor no tiene configurado el envío de correos. "
                            "Define las variables de entorno MAIL_SERVER y MAIL_DEFAULT_SENDER (o MAIL_FROM), "
                            "y según tu proveedor MAIL_USERNAME, MAIL_PASSWORD, MAIL_PORT, MAIL_USE_TLS o MAIL_USE_SSL. "
                            "Opcional: PUBLIC_BASE_URL con la URL pública del sitio (por ejemplo https://tudominio.com). "
                            "En local puedes poner MAIL_DEBUG=1 en .env para ver el enlace en esta página sin correo. "
                            "Consulta el README o env.example."
                        ),
                        info=None,
                        mail_configured=False,
                        mail_debug=False,
                    ),
                    503,
                )

            try:
                send_password_reset_email(user["email"], reset_url)
            except Exception:
                app.logger.exception("Fallo SMTP al enviar recuperación de contraseña a %s", email)
                db.execute("DELETE FROM password_resets WHERE id = ?", (reset_row_id,))
                return (
                    render_template(
                        "auth_forgot.html",
                        error=(
                            "No pudimos enviar el correo. Revisa usuario, contraseña y puerto del SMTP, "
                            "o intenta de nuevo más tarde."
                        ),
                        info=None,
                        mail_configured=True,
                        mail_debug=mail_debug_mode(),
                    ),
                    500,
                )

    return (
        render_template(
            "auth_forgot.html",
            error=None,
            info=(
                "Si tu correo está registrado en Tecnocambia, te enviamos un email con un enlace "
                "para restablecer la contraseña (válido unos 30 minutos). Revisa también la carpeta de spam."
            ),
            mail_configured=mail_is_configured(),
            mail_debug=mail_debug_mode(),
        ),
        200,
    )


@app.get("/auth/reset/<token>")
def reset_password(token: str):
    with get_db() as db:
        row = db.execute(
            """
            SELECT pr.*, u.email
            FROM password_resets pr
            JOIN users u ON u.id = pr.user_id
            WHERE pr.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        return render_template("auth_reset.html", error="Enlace inválido.", token=token), 400
    if row["used_at"]:
        return render_template("auth_reset.html", error="Este enlace ya fue usado.", token=token), 400
    return render_template("auth_reset.html", error=None, token=token)


@app.post("/auth/reset/<token>")
def reset_password_post(token: str):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"reset:{ip}", limit=8, window_sec=60):
        return render_template("auth_reset.html", error="Demasiados intentos. Intenta en 1 minuto.", token=token), 429

    password = request.form.get("password", "")
    if len(password) < 6:
        return render_template("auth_reset.html", error="La contraseña debe tener al menos 6 caracteres.", token=token), 400

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_db() as db:
        row = db.execute("SELECT * FROM password_resets WHERE token = ?", (token,)).fetchone()
        if not row or row["used_at"]:
            return render_template("auth_reset.html", error="Enlace inválido o usado.", token=token), 400

        try:
            exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                return render_template("auth_reset.html", error="Enlace expirado.", token=token), 400
        except Exception:
            pass

        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), row["user_id"]),
        )
        db.execute("UPDATE password_resets SET used_at = ? WHERE id = ?", (now, row["id"]))

    return redirect("/app/login")


def _save_images(files):
    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        if f.mimetype not in ALLOWED_TYPES:
            raise ValueError("Solo se permiten imágenes (JPG/PNG/WebP/GIF).")
        ext = Path(secure_filename(f.filename)).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        out_path = UPLOADS_DIR / filename
        f.save(out_path)
        if out_path.stat().st_size > MAX_FILE_SIZE:
            out_path.unlink(missing_ok=True)
            raise ValueError("Una imagen supera el tamaño máximo (5MB).")
        saved.append(filename)
    return saved


def _save_verification_image(f, label: str) -> str:
    if not f or not f.filename:
        raise ValueError(f"Falta la imagen: {label}.")
    if f.mimetype not in ALLOWED_TYPES:
        raise ValueError("Solo se permiten imágenes (JPG/PNG/WebP/GIF).")
    ext = Path(secure_filename(f.filename)).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    out_path = UPLOADS_DIR / filename
    f.save(out_path)
    if out_path.stat().st_size > MAX_FILE_SIZE:
        out_path.unlink(missing_ok=True)
        raise ValueError("La imagen supera el tamaño máximo (5MB).")
    return filename


def _user_identity_verified(uid: int) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT identity_verification_status FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
    return bool(row and str(row["identity_verification_status"] or "") == "verified")


@app.get("/sell")
def sell():
    r = require_auth()
    if r:
        return r
    return redirect("/app/sell")


@app.post("/sell")
def sell_post():
    r = require_auth()
    if r:
        return r

    if not _user_identity_verified(int(session["user_id"])):
        return (
            render_template(
                "sell.html",
                error="Tu identidad está en revisión o fue rechazada. Espera la verificación del equipo para publicar.",
                form=request.form,
            ),
            403,
        )

    try:
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        listing_type = (request.form.get("listing_type") or "").strip()
        category = (request.form.get("category") or "").strip()
        item_condition = (request.form.get("item_condition") or "").strip()
        location = (request.form.get("location") or "").strip()
        price = (request.form.get("price") or "").strip()

        if listing_type not in {"sale", "exchange", "donation"}:
            raise ValueError("Tipo de publicación inválido.")
        if item_condition not in {"new", "like_new", "good", "fair", "for_parts"}:
            raise ValueError("Condición inválida.")
        if not title or not description or not category or not location:
            raise ValueError("Revisa los campos requeridos.")

        price_cents = None
        if listing_type == "sale":
            norm = re.sub(r"[^0-9.,]", "", price).replace(",", ".")
            value = float(norm) if norm else 0.0
            price_cents = int(round(value * 100))
            if price_cents < 0:
                raise ValueError("Precio inválido.")
        elif listing_type == "donation":
            price_cents = 0

        image_files = request.files.getlist("images")[:6]
        if not any(f and f.filename for f in image_files):
            raise ValueError("Debes subir al menos una foto del producto.")
        images = _save_images(image_files)

        with get_db() as db:
            cur = db.execute(
                """
                INSERT INTO products
                  (user_id, title, description, listing_type, price_cents, category, brand, model, year, accessories, item_condition, location)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    title,
                    description,
                    listing_type,
                    price_cents,
                    category,
                    (request.form.get("brand") or "").strip() or None,
                    (request.form.get("model") or "").strip() or None,
                    int(request.form.get("year")) if (request.form.get("year") or "").strip().isdigit() else None,
                    (request.form.get("accessories") or "").strip() or None,
                    item_condition,
                    location,
                ),
            )
            product_id = cur.lastrowid
            for i, fn in enumerate(images):
                is_cover = 1 if i == 0 else 0
                db.execute(
                    "INSERT INTO product_images (product_id, filename, is_cover) VALUES (?, ?, ?)",
                    (product_id, fn, is_cover),
                )

        return redirect(f"/app/products/{product_id}")
    except Exception as e:
        return render_template("sell.html", error=str(e) or "Error al publicar.", form=request.form), 400


@app.get("/me/listings")
def my_listings():
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        products = db.execute(
            """
            SELECT
              p.*,
              (
                SELECT filename FROM product_images
                WHERE product_id = p.id
                ORDER BY is_cover DESC, id ASC
                LIMIT 1
              ) AS cover_image
            FROM products p
            WHERE p.user_id = ?
            ORDER BY datetime(p.created_at) DESC
            """,
            (session["user_id"],),
        ).fetchall()
    return render_template("my_listings.html", products=products)


@app.get("/me/offers")
def my_offers():
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        offers = db.execute(
            """
            SELECT
              o.*,
              p.title AS product_title,
              p.location,
              p.listing_type,
              u.name AS buyer_name
            FROM offers o
            JOIN products p ON p.id = o.product_id
            JOIN users u ON u.id = o.buyer_id
            WHERE p.user_id = ?
            ORDER BY datetime(o.created_at) DESC
            """,
            (uid,),
        ).fetchall()
    return render_template("my_offers.html", offers=offers)


@app.post("/me/offers/<int:offer_id>/<action>")
def offer_action(offer_id: int, action: str):
    r = require_auth()
    if r:
        return r
    if action not in {"accept", "reject"}:
        return redirect("/me/offers")
    uid = session["user_id"]
    new_status = "accepted" if action == "accept" else "rejected"
    with get_db() as db:
        offer = db.execute(
            """
            SELECT o.*, p.user_id AS seller_id
            FROM offers o
            JOIN products p ON p.id = o.product_id
            WHERE o.id = ?
            """,
            (offer_id,),
        ).fetchone()
        if not offer or offer["seller_id"] != uid:
            return render_template("404.html"), 404
        if new_status == "accepted":
            # lock: only one accepted offer per product
            already = db.execute(
                "SELECT 1 FROM offers WHERE product_id = ? AND status='accepted' LIMIT 1",
                (offer["product_id"],),
            ).fetchone()
            if already:
                return redirect("/me/offers")

            db.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))
            db.execute("UPDATE offers SET status = 'rejected' WHERE product_id = ? AND id != ? AND status='pending'", (offer["product_id"], offer_id))
            db.execute(
                """
                UPDATE products
                SET status='reserved', reserved_by=?, reserved_at=datetime('now'), updated_at=datetime('now')
                WHERE id = ?
                """,
                (offer["buyer_id"], offer["product_id"]),
            )
        else:
            db.execute("UPDATE offers SET status = 'rejected' WHERE id = ?", (offer_id,))
    return redirect("/me/offers")


@app.post("/me/offers/<int:offer_id>/counter")
def counter_offer(offer_id: int):
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    raw = (request.form.get("amount") or "").strip()
    try:
        norm = re.sub(r"[^0-9.,]", "", raw).replace(",", ".")
        value = float(norm) if norm else 0.0
        amount_cents = int(round(value * 100))
    except Exception:
        amount_cents = -1
    if amount_cents <= 0:
        return redirect("/me/offers")

    with get_db() as db:
        offer = db.execute(
            """
            SELECT o.*, p.user_id AS seller_id
            FROM offers o
            JOIN products p ON p.id = o.product_id
            WHERE o.id = ?
            """,
            (offer_id,),
        ).fetchone()
        if not offer or offer["seller_id"] != uid:
            return render_template("404.html"), 404
        if offer["status"] != "pending":
            return redirect("/me/offers")

        # create a new offer record as counter (still stored under buyer)
        db.execute(
            "INSERT INTO offers (product_id, buyer_id, offer_type, amount_cents, status) VALUES (?, ?, 'offer', ?, 'pending')",
            (offer["product_id"], offer["buyer_id"], amount_cents),
        )
        # reject the original pending offer to keep one thread
        db.execute("UPDATE offers SET status='rejected' WHERE id = ?", (offer_id,))

    return redirect("/me/offers")


@app.get("/me/purchases")
def my_purchases():
    r = require_auth()
    if r:
        return r
    uid = session["user_id"]
    with get_db() as db:
        offers = db.execute(
            """
            SELECT
              o.*,
              p.title AS product_title,
              p.location,
              p.listing_type,
              su.name AS seller_name
            FROM offers o
            JOIN products p ON p.id = o.product_id
            JOIN users su ON su.id = p.user_id
            WHERE o.buyer_id = ?
            ORDER BY datetime(o.created_at) DESC
            """,
            (uid,),
        ).fetchall()
    return render_template("my_purchases.html", offers=offers)


@app.get("/admin")
def admin_home():
    r = require_admin()
    if r:
        return r
    with get_db() as db:
        counts = {
            "users": db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"],
            "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
            "reports_open": db.execute("SELECT COUNT(*) AS c FROM reports WHERE status='open'").fetchone()["c"],
        }
        recent_reports = db.execute(
            """
            SELECT r.*, u.name AS reporter_name
            FROM reports r
            JOIN users u ON u.id = r.reporter_id
            ORDER BY datetime(r.created_at) DESC
            LIMIT 20
            """
        ).fetchall()
        pending_identity = db.execute(
            """
            SELECT id, name, email, curp, ine_image_filename, created_at
            FROM users
            WHERE identity_verification_status = 'pending'
              AND ine_image_filename IS NOT NULL
            ORDER BY datetime(created_at) DESC
            LIMIT 50
            """
        ).fetchall()
    return render_template(
        "admin.html",
        counts=counts,
        reports=recent_reports,
        pendingIdentity=pending_identity,
    )


@app.post("/admin/reports/<int:report_id>/<action>")
def admin_report_action(report_id: int, action: str):
    r = require_admin()
    if r:
        return r
    if action not in {"reviewed", "closed"}:
        return redirect("/admin")
    with get_db() as db:
        db.execute("UPDATE reports SET status = ? WHERE id = ?", (action, report_id))
    return redirect("/admin")


@app.post("/admin/identity/<int:user_id>/<action>")
def admin_identity_action(user_id: int, action: str):
    r = require_admin()
    if r:
        return r
    if action not in {"approve", "reject"}:
        return redirect("/admin")
    status = "verified" if action == "approve" else "rejected"
    with get_db() as db:
        db.execute(
            "UPDATE users SET identity_verification_status = ? WHERE id = ?",
            (status, user_id),
        )
    return redirect("/admin")


@app.get("/admin/backup")
def admin_backup():
    r = require_admin()
    if r:
        return r
    dest = backup_db_path()
    # safest portable backup for SQLite
    src = sqlite3.connect(DB_PATH)
    try:
        dst = sqlite3.connect(dest)
        with dst:
            src.backup(dst)
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass
    return send_file(dest, as_attachment=True, download_name=dest.name)


@app.get("/me/listings/<int:product_id>/edit")
def edit_listing(product_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        product = db.execute(
            "SELECT * FROM products WHERE id = ? AND user_id = ?",
            (product_id, session["user_id"]),
        ).fetchone()
        images = db.execute(
            "SELECT id, filename, is_cover FROM product_images WHERE product_id = ? ORDER BY is_cover DESC, id ASC",
            (product_id,),
        ).fetchall()
    if not product:
        return render_template("404.html"), 404
    return render_template("edit_listing.html", error=None, product=product, images=images)


@app.post("/me/listings/<int:product_id>/edit")
def edit_listing_post(product_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        product = db.execute(
            "SELECT * FROM products WHERE id = ? AND user_id = ?",
            (product_id, session["user_id"]),
        ).fetchone()
        if not product:
            return render_template("404.html"), 404

        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        status = (request.form.get("status") or "").strip()
        location = (request.form.get("location") or "").strip()

        if not title or not description or not location or status not in {"active", "paused", "completed"}:
            merged = dict(product)
            merged.update(request.form)
            images = db.execute(
                "SELECT id, filename, is_cover FROM product_images WHERE product_id = ? ORDER BY is_cover DESC, id ASC",
                (product_id,),
            ).fetchall()
            return render_template("edit_listing.html", error="Revisa los campos.", product=merged, images=images), 400

        db.execute(
            """
            UPDATE products
            SET title = ?, description = ?, status = ?, location = ?, updated_at = datetime('now')
            WHERE id = ? AND user_id = ?
            """,
            (title, description, status, location, product_id, session["user_id"]),
        )

    return redirect("/me/listings")


@app.post("/me/listings/<int:product_id>/images/add")
def add_listing_images(product_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        product = db.execute(
            "SELECT id FROM products WHERE id = ? AND user_id = ?",
            (product_id, session["user_id"]),
        ).fetchone()
        if not product:
            return render_template("404.html"), 404

        files = request.files.getlist("images") if request.files else []
        imgs = _save_images(files[:6])

        has_cover = db.execute(
            "SELECT 1 FROM product_images WHERE product_id = ? AND is_cover = 1 LIMIT 1",
            (product_id,),
        ).fetchone()
        for i, fn in enumerate(imgs):
            is_cover = 1 if (not has_cover and i == 0) else 0
            db.execute(
                "INSERT INTO product_images (product_id, filename, is_cover) VALUES (?, ?, ?)",
                (product_id, fn, is_cover),
            )
            has_cover = True
    return redirect(f"/me/listings/{product_id}/edit")


@app.post("/me/listings/<int:product_id>/images/<int:image_id>/cover")
def set_listing_cover(product_id: int, image_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        ok = db.execute(
            """
            SELECT 1
            FROM product_images pi
            JOIN products p ON p.id = pi.product_id
            WHERE pi.id = ? AND pi.product_id = ? AND p.user_id = ?
            """,
            (image_id, product_id, session["user_id"]),
        ).fetchone()
        if not ok:
            return render_template("404.html"), 404
        db.execute("UPDATE product_images SET is_cover = 0 WHERE product_id = ?", (product_id,))
        db.execute("UPDATE product_images SET is_cover = 1 WHERE id = ? AND product_id = ?", (image_id, product_id))
    return redirect(f"/me/listings/{product_id}/edit")


@app.post("/me/listings/<int:product_id>/images/<int:image_id>/delete")
def delete_listing_image(product_id: int, image_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        row = db.execute(
            """
            SELECT pi.filename, pi.is_cover
            FROM product_images pi
            JOIN products p ON p.id = pi.product_id
            WHERE pi.id = ? AND pi.product_id = ? AND p.user_id = ?
            """,
            (image_id, product_id, session["user_id"]),
        ).fetchone()
        if not row:
            return render_template("404.html"), 404
        db.execute("DELETE FROM product_images WHERE id = ? AND product_id = ?", (image_id, product_id))

        if int(row["is_cover"]) == 1:
            nxt = db.execute(
                "SELECT id FROM product_images WHERE product_id = ? ORDER BY id ASC LIMIT 1",
                (product_id,),
            ).fetchone()
            if nxt:
                db.execute("UPDATE product_images SET is_cover = 1 WHERE id = ?", (nxt["id"],))

    try:
        (UPLOADS_DIR / row["filename"]).unlink(missing_ok=True)
    except Exception:
        pass

    return redirect(f"/me/listings/{product_id}/edit")


@app.post("/me/listings/<int:product_id>/delete")
def delete_listing(product_id: int):
    r = require_auth()
    if r:
        return r

    with get_db() as db:
        imgs = db.execute(
            "SELECT filename FROM product_images WHERE product_id = ?",
            (product_id,),
        ).fetchall()
        db.execute(
            "DELETE FROM products WHERE id = ? AND user_id = ?",
            (product_id, session["user_id"]),
        )

    for row in imgs:
        try:
            (UPLOADS_DIR / row["filename"]).unlink(missing_ok=True)
        except Exception:
            pass

    return redirect("/me/listings")


@app.post("/me/listings/<int:product_id>/complete")
def complete_listing(product_id: int):
    r = require_auth()
    if r:
        return r
    with get_db() as db:
        product = db.execute(
            "SELECT * FROM products WHERE id = ? AND user_id = ?",
            (product_id, session["user_id"]),
        ).fetchone()
        if not product:
            return render_template("404.html"), 404
        db.execute(
            "UPDATE products SET status='completed', updated_at=datetime('now') WHERE id = ? AND user_id = ?",
            (product_id, session["user_id"]),
        )
        db.execute("UPDATE offers SET status='cancelled' WHERE product_id = ? AND status='pending'", (product_id,))
    return redirect("/me/listings")


def _row_dict(row):
    return {k: row[k] for k in row.keys()}


def _products_filter_from_request():
    q = (request.args.get("q") or "").strip()
    listing_type = (request.args.get("type") or "").strip()
    category = (request.args.get("category") or "").strip()
    item_condition = (request.args.get("condition") or "").strip()
    sort = (request.args.get("sort") or "recent").strip()
    min_price = (request.args.get("min_price") or "").strip()
    max_price = (request.args.get("max_price") or "").strip()
    location = (request.args.get("location") or "").strip()
    with_photos = (request.args.get("photos") or "").strip()
    page = request.args.get("page") or "1"
    try:
        page_i = max(1, int(page))
    except Exception:
        page_i = 1
    per_page = 24

    where = ["p.status = 'active'"]
    params = {}

    if q:
        where.append(
            "(p.title LIKE :q OR p.description LIKE :q OR p.category LIKE :q OR p.location LIKE :q)"
        )
        params["q"] = f"%{q}%"
    if listing_type in {"sale", "exchange", "donation"}:
        where.append("p.listing_type = :listing_type")
        params["listing_type"] = listing_type
    if category:
        where.append("p.category = :category")
        params["category"] = category
    if item_condition in {"new", "like_new", "good", "fair", "for_parts"}:
        where.append("p.item_condition = :item_condition")
        params["item_condition"] = item_condition

    if location:
        where.append("p.location LIKE :loc")
        params["loc"] = f"%{location}%"

    if min_price:
        try:
            cents = int(round(float(min_price.replace(",", ".")) * 100))
            where.append("p.price_cents IS NOT NULL AND p.price_cents >= :minc")
            params["minc"] = cents
        except Exception:
            pass
    if max_price:
        try:
            cents = int(round(float(max_price.replace(",", ".")) * 100))
            where.append("p.price_cents IS NOT NULL AND p.price_cents <= :maxc")
            params["maxc"] = cents
        except Exception:
            pass

    if with_photos == "1":
        where.append("EXISTS (SELECT 1 FROM product_images pi WHERE pi.product_id = p.id)")

    if sort == "price_asc":
        order_by = "CASE WHEN p.price_cents IS NULL THEN 1 ELSE 0 END, p.price_cents ASC, datetime(p.created_at) DESC"
    elif sort == "price_desc":
        order_by = "CASE WHEN p.price_cents IS NULL THEN 1 ELSE 0 END, p.price_cents DESC, datetime(p.created_at) DESC"
    else:
        sort = "recent"
        order_by = "datetime(p.created_at) DESC"

    params["limit"] = per_page
    params["offset"] = (page_i - 1) * per_page

    sql = f"""
      SELECT
        p.*,
        u.name AS seller_name,
        (
          SELECT filename FROM product_images
          WHERE product_id = p.id
          ORDER BY is_cover DESC, id ASC
          LIMIT 1
        ) AS cover_image
      FROM products p
      JOIN users u ON u.id = p.user_id
      WHERE {' AND '.join(where)}
      ORDER BY {order_by}
      LIMIT :limit OFFSET :offset
    """
    count_sql = f"""
      SELECT COUNT(*) AS c
      FROM products p
      WHERE {' AND '.join(where)}
    """
    return {
        "q": q,
        "listing_type": listing_type,
        "category": category,
        "item_condition": item_condition,
        "sort": sort,
        "min_price": min_price,
        "max_price": max_price,
        "location": location,
        "with_photos": with_photos,
        "page_i": page_i,
        "per_page": per_page,
        "where": where,
        "params": params,
        "sql": sql,
        "count_sql": count_sql,
        "order_by": order_by,
    }


@app.get("/api/session")
def api_session():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None})
    with get_db() as db:
        u = db.execute(
            "SELECT id, name, email, is_admin, identity_verification_status FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
    if not u:
        session.clear()
        return jsonify({"user": None})
    return jsonify(
        {
            "user": {
                "id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "isAdmin": bool(u["is_admin"]),
                "verificationStatus": u["identity_verification_status"],
            }
        }
    )


@app.get("/api/meta")
def api_meta():
    return jsonify(
        {
            "categories": PRESET_CATEGORIES,
            "listingTypes": ["sale", "exchange", "donation"],
            "conditions": ["new", "like_new", "good", "fair", "for_parts"],
        }
    )


@app.get("/api/products")
def api_products_list():
    b = _products_filter_from_request()
    params = dict(b["params"])
    with get_db() as db:
        total = db.execute(b["count_sql"], params).fetchone()["c"]
        items = db.execute(b["sql"], params).fetchall()
        cats = db.execute(
            "SELECT DISTINCT category FROM products WHERE status='active' ORDER BY category ASC"
        ).fetchall()
        locs = db.execute(
            "SELECT DISTINCT location FROM products WHERE status='active' ORDER BY location ASC"
        ).fetchall()

    per_page = b["per_page"]
    page_i = b["page_i"]
    total_pages = max(1, (total + per_page - 1) // per_page)
    page_i = min(page_i, total_pages)

    out_items = []
    for r in items:
        d = _row_dict(r)
        if d.get("cover_image"):
            d["coverImageUrl"] = f"/uploads/{d['cover_image']}"
        out_items.append(d)

    return jsonify(
        {
            "page": page_i,
            "totalPages": total_pages,
            "totalResults": total,
            "products": out_items,
            "filters": {
                "q": b["q"],
                "type": b["listing_type"],
                "category": b["category"],
                "condition": b["item_condition"],
                "sort": b["sort"],
                "minPrice": b["min_price"],
                "maxPrice": b["max_price"],
                "location": b["location"],
                "photos": b["with_photos"],
            },
            "categories": [x["category"] for x in cats],
            "locations": [x["location"] for x in locs],
        }
    )


@app.get("/api/products/<int:product_id>")
def api_product_detail(product_id: int):
    with get_db() as db:
        product = db.execute(
            """
            SELECT p.*, u.name AS seller_name, u.email AS seller_email
            FROM products p
            JOIN users u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (product_id,),
        ).fetchone()
        if not product:
            return jsonify({"error": "not_found"}), 404

        viewer = session.get("user_id")
        if viewer:
            blocked = db.execute(
                "SELECT 1 FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
                (viewer, product["user_id"]),
            ).fetchone()
            if blocked:
                return jsonify({"error": "not_found"}), 404

        uid = session.get("user_id")
        if uid:
            db.execute(
                """
                INSERT INTO viewed_products (user_id, product_id, last_viewed_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(user_id, product_id) DO UPDATE SET
                  last_viewed_at=datetime('now')
                """,
                (uid, product_id),
            )

        images = db.execute(
            "SELECT id, filename FROM product_images WHERE product_id = ? ORDER BY id ASC",
            (product_id,),
        ).fetchall()

    pd = _row_dict(product)
    pd["images"] = [{"id": im["id"], "url": f"/uploads/{im['filename']}"} for im in images]
    return jsonify({"product": pd})


@app.post("/api/auth/login")
def api_auth_login():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"login:{ip}", limit=8, window_sec=60):
        return jsonify({"ok": False, "error": "Demasiados intentos. Intenta en 1 minuto."}), 429

    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get("email", ""))
    password = data.get("password") or ""
    next_url = safe_next(data.get("next", ""))

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"ok": False, "error": "Credenciales inválidas."}), 401

    session["user_id"] = user["id"]
    session.permanent = True
    return jsonify({"ok": True, "next": next_url})


@app.post("/api/auth/logout")
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/auth/register")
def api_auth_register():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not rate_limit(f"register:{ip}", limit=6, window_sec=60):
        return jsonify({"ok": False, "error": "Demasiados intentos. Intenta en 1 minuto."}), 429

    name = (request.form.get("name") or "").strip()
    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    curp_norm = normalize_curp(request.form.get("curp", ""))
    next_url = safe_next(request.form.get("next", ""))

    if not name or not email or len(password) < 6:
        return jsonify({"ok": False, "error": "Completa nombre, email y contraseña (mín. 6)."}), 400
    if not curp_is_valid(curp_norm):
        return jsonify({"ok": False, "error": "CURP inválida."}), 400

    ine_f = request.files.get("ine_photo")
    try:
        ine_fn = _save_verification_image(ine_f, "credencial INE (frente)")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_db() as db:
        exists = db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            try:
                (UPLOADS_DIR / ine_fn).unlink(missing_ok=True)
            except Exception:
                pass
            return jsonify({"ok": False, "error": "Ese email ya está registrado."}), 409
        dup_curp = db.execute(
            "SELECT 1 FROM users WHERE curp = ? AND curp IS NOT NULL",
            (curp_norm,),
        ).fetchone()
        if dup_curp:
            try:
                (UPLOADS_DIR / ine_fn).unlink(missing_ok=True)
            except Exception:
                pass
            return jsonify({"ok": False, "error": "Esa CURP ya está registrada."}), 409
        db.execute(
            """
            INSERT INTO users
              (name, email, password_hash, curp, ine_image_filename, curp_document_filename, identity_verification_status)
            VALUES (?, ?, ?, ?, ?, NULL, 'pending')
            """,
            (name, email, generate_password_hash(password), curp_norm, ine_fn),
        )
        user_id = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]

    session["user_id"] = user_id
    session.permanent = True
    return jsonify({"ok": True, "next": next_url})


@app.post("/api/sell")
def api_sell():
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "auth"}), 401
    if not _user_identity_verified(int(session["user_id"])):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Tu identidad debe estar verificada para publicar. Espera la revisión del equipo.",
                }
            ),
            403,
        )

    try:
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        listing_type = (request.form.get("listing_type") or "").strip()
        category = (request.form.get("category") or "").strip()
        item_condition = (request.form.get("item_condition") or "").strip()
        location = (request.form.get("location") or "").strip()
        price = (request.form.get("price") or "").strip()

        if listing_type not in {"sale", "exchange", "donation"}:
            raise ValueError("Tipo de publicación inválido.")
        if item_condition not in {"new", "like_new", "good", "fair", "for_parts"}:
            raise ValueError("Condición inválida.")
        if not title or not description or not category or not location:
            raise ValueError("Revisa los campos requeridos.")

        price_cents = None
        if listing_type == "sale":
            norm = re.sub(r"[^0-9.,]", "", price).replace(",", ".")
            value = float(norm) if norm else 0.0
            price_cents = int(round(value * 100))
            if price_cents < 0:
                raise ValueError("Precio inválido.")
        elif listing_type == "donation":
            price_cents = 0

        image_files = request.files.getlist("images")[:6]
        if not any(f and f.filename for f in image_files):
            raise ValueError("Debes subir al menos una foto del producto.")
        images = _save_images(image_files)

        with get_db() as db:
            cur = db.execute(
                """
                INSERT INTO products
                  (user_id, title, description, listing_type, price_cents, category, brand, model, year, accessories, item_condition, location)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    title,
                    description,
                    listing_type,
                    price_cents,
                    category,
                    (request.form.get("brand") or "").strip() or None,
                    (request.form.get("model") or "").strip() or None,
                    int(request.form.get("year")) if (request.form.get("year") or "").strip().isdigit() else None,
                    (request.form.get("accessories") or "").strip() or None,
                    item_condition,
                    location,
                ),
            )
            product_id = cur.lastrowid
            for i, fn in enumerate(images):
                is_cover = 1 if i == 0 else 0
                db.execute(
                    "INSERT INTO product_images (product_id, filename, is_cover) VALUES (?, ?, ?)",
                    (product_id, fn, is_cover),
                )

        return jsonify({"ok": True, "productId": product_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e) or "Error al publicar."}), 400


def _api_uid_or_401():
    uid = session.get("user_id")
    if not uid:
        return None
    return int(uid)


def _save_upload(file_storage, allowed_types):
    if not file_storage:
        raise RuntimeError("No file provided.")
    filename = file_storage.filename or ''
    if not filename:
        raise RuntimeError("Nombre de archivo inválido.")
    content_type = file_storage.content_type or ''
    if content_type not in allowed_types:
        raise RuntimeError("Tipo de archivo no permitido.")
    data = file_storage.read()
    if len(data) > MAX_FILE_SIZE:
        raise RuntimeError("Archivo demasiado grande.")
    safe = secure_filename(filename)
    out_name = f"{uuid.uuid4().hex}_{safe}"
    out_path = UPLOADS_DIR / out_name
    with open(out_path, 'wb') as f:
        f.write(data)
    return out_name


@app.get("/api/me")
def api_me_profile():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"error": "auth"}), 401
    with get_db() as db:
        u = db.execute(
            """
            SELECT id, name, email, curp, ine_image_filename, curp_document_filename, identity_verification_status, created_at, is_admin
            FROM users WHERE id = ?
            """,
            (uid,),
        ).fetchone()
    if not u:
        session.clear()
        return jsonify({"error": "auth"}), 401
    d = _row_dict(u)
    if d.get("ine_image_filename"):
        d["ineImageUrl"] = f"/uploads/{d['ine_image_filename']}"
    if d.get("curp_document_filename"):
        d["curpDocumentUrl"] = f"/uploads/{d['curp_document_filename']}"
    d["isAdmin"] = bool(d.pop("is_admin", 0))
    d["verificationStatus"] = d.pop("identity_verification_status")
    return jsonify({"user": d})


@app.patch("/api/me")
def api_me_update():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) < 2:
        return jsonify({"ok": False, "error": "El nombre debe tener al menos 2 caracteres."}), 400
    with get_db() as db:
        db.execute("UPDATE users SET name = ? WHERE id = ?", (name, uid))
    return jsonify({"ok": True})


@app.post("/api/me/ine")
def api_me_upload_ine():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401
    if "ine" not in request.files:
        return jsonify({"ok": False, "error": "Falta archivo INE (campo 'ine')."}), 400
    f = request.files["ine"]
    try:
        fname = _save_upload(f, ALLOWED_TYPES)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    with get_db() as db:
        db.execute(
            "UPDATE users SET ine_image_filename = ?, identity_verification_status = 'pending' WHERE id = ?",
            (fname, uid),
        )
    return jsonify({"ok": True, "url": f"/uploads/{fname}"})


@app.post("/api/me/curp-doc")
def api_me_upload_curp_doc():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401
    if "curp_doc" not in request.files:
        return jsonify({"ok": False, "error": "Falta archivo (campo 'curp_doc')."}), 400
    f = request.files["curp_doc"]
    try:
        fname = _save_upload(f, ALLOWED_DOC_TYPES)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    with get_db() as db:
        db.execute(
            "UPDATE users SET curp_document_filename = ?, identity_verification_status = 'pending' WHERE id = ?",
            (fname, uid),
        )
    return jsonify({"ok": True, "url": f"/uploads/{fname}"})


@app.patch("/api/me/curp")
def api_me_update_curp():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401
    data = request.get_json(silent=True) or {}
    curp = (data.get("curp") or "").strip().upper()
    if curp and len(curp) != 18:
        return jsonify({"ok": False, "error": "CURP inválida (debe tener 18 caracteres)."}), 400
    with get_db() as db:
        db.execute("UPDATE users SET curp = ?, identity_verification_status = 'pending' WHERE id = ?", (curp or None, uid))
    return jsonify({"ok": True})


@app.get("/api/me/listings")
def api_me_listings():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"error": "auth"}), 401
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
              p.*,
              (
                SELECT filename FROM product_images
                WHERE product_id = p.id
                ORDER BY is_cover DESC, id ASC
                LIMIT 1
              ) AS cover_image,
              (SELECT COUNT(*) FROM product_images WHERE product_id = p.id) AS image_count
            FROM products p
            WHERE p.user_id = ?
            ORDER BY datetime(p.created_at) DESC
            """,
            (uid,),
        ).fetchall()
    products = []
    for r in rows:
        d = _row_dict(r)
        if d.get("cover_image"):
            d["coverImageUrl"] = f"/uploads/{d['cover_image']}"
        products.append(d)
    return jsonify({"products": products})


@app.get("/api/admin/overview")
def api_admin_overview():
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"error": "auth"}), 401
    with get_db() as db:
        u = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
        if not u or not int(u["is_admin"]):
            return jsonify({"error": "forbidden"}), 403
        counts = {
            "users": db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"],
            "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
            "reportsOpen": db.execute("SELECT COUNT(*) AS c FROM reports WHERE status='open'").fetchone()["c"],
            "pendingIdentity": db.execute(
                "SELECT COUNT(*) AS c FROM users WHERE identity_verification_status='pending' AND ine_image_filename IS NOT NULL"
            ).fetchone()["c"],
        }
        pending = db.execute(
            """
            SELECT id, name, email, curp, ine_image_filename, created_at, identity_verification_status
            FROM users
            WHERE identity_verification_status = 'pending'
              AND ine_image_filename IS NOT NULL
            ORDER BY datetime(created_at) DESC
            LIMIT 50
            """
        ).fetchall()
    out_pending = []
    for row in pending:
        d = _row_dict(row)
        d["ineImageUrl"] = f"/uploads/{d['ine_image_filename']}"
        d["verificationStatus"] = d.pop("identity_verification_status")
        out_pending.append(d)
    return jsonify({"counts": counts, "pendingUsers": out_pending})


@app.post("/api/admin/identity/<int:user_id>")
def api_admin_identity(user_id: int):
    uid = _api_uid_or_401()
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()
    if action not in {"approve", "reject"}:
        return jsonify({"ok": False, "error": "Acción inválida."}), 400
    with get_db() as db:
        admin = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
        if not admin or not int(admin["is_admin"]):
            return jsonify({"ok": False, "error": "forbidden"}), 403
        status = "verified" if action == "approve" else "rejected"
        cur = db.execute(
            "UPDATE users SET identity_verification_status = ? WHERE id = ?",
            (status, user_id),
        )
        if cur.rowcount == 0:
            return jsonify({"ok": False, "error": "Usuario no encontrado."}), 404
    return jsonify({"ok": True, "status": status})


@app.get("/app/")
@app.get("/app/<path:fname>")
def spa_redirect_to_frontend(fname: str = ""):
    path = "/app/" + fname if fname else "/app/products"
    external = _frontend_app_url(path)
    if external:
        return redirect(external)
    return (
        "<p>El frontend está en Vercel. Define <code>FRONTEND_ORIGIN</code> en el backend.</p>",
        503,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


def bootstrap_app() -> None:
    init_db()
    ensure_seed_data()


bootstrap_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")), debug=DEBUG)

