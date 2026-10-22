"""Lista filmów do obejrzenia – prosta aplikacja CRUD (Flask + PostgreSQL)."""
import os
import socket
import time

import psycopg
from flask import Flask, abort, flash, redirect, render_template, request, url_for

app = Flask(__name__)

# Klucz sesji (potrzebny do komunikatów flash) – w Kubernetes pochodzi z Secret.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

# Wersja aplikacji – wpisywana do obrazu przy budowaniu (docker build --build-arg APP_VERSION=v2).
APP_VERSION = os.environ.get("APP_VERSION", "dev")
HOSTNAME = socket.gethostname()  # w Kubernetes = nazwa poda

SERVICES = ["Netflix", "HBO Max", "Disney+", "Prime Video", "SkyShowtime", "Apple TV+", "Inny"]


def db_conninfo():
    """Parametry połączenia ze zmiennych środowiskowych (ConfigMap + Secret)."""
    return (
        f"host={os.environ.get('DB_HOST', 'localhost')} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"dbname={os.environ.get('DB_NAME', 'filmy')} "
        f"user={os.environ.get('DB_USER', 'filmy')} "
        f"password={os.environ.get('DB_PASSWORD', '')} "
        "connect_timeout=5"
    )


def get_conn():
    return psycopg.connect(db_conninfo())


def init_db(retries=30, delay=2):
    """Tworzy tabelę przy starcie. Czeka na bazę, bo w klastrze może wstać później niż aplikacja."""
    for attempt in range(1, retries + 1):
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS movies (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        genre VARCHAR(100),
                        year INTEGER,
                        service VARCHAR(50) NOT NULL,
                        watched BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
            app.logger.info("Baza gotowa")
            return
        except psycopg.OperationalError as exc:
            app.logger.warning("Baza niedostępna (próba %s/%s): %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError("Nie udało się połączyć z bazą danych")


def parse_form(form):
    """Waliduje dane z formularza. Zwraca (dane, błąd)."""
    title = form.get("title", "").strip()
    genre = form.get("genre", "").strip() or None
    service = form.get("service", "")
    year_raw = form.get("year", "").strip()
    watched = form.get("watched") == "on"

    if not title or len(title) > 200:
        return None, "Tytuł jest wymagany (max 200 znaków)."
    if service not in SERVICES:
        return None, "Wybierz serwis z listy."
    year = None
    if year_raw:
        if not year_raw.isdigit() or not 1888 <= int(year_raw) <= 2100:
            return None, "Rok musi być liczbą z zakresu 1888–2100."
        year = int(year_raw)
    return {"title": title, "genre": genre, "year": year, "service": service, "watched": watched}, None


@app.context_processor
def inject_globals():
    return {"app_version": APP_VERSION, "hostname": HOSTNAME, "services": SERVICES}


@app.route("/")
def index():
    service = request.args.get("service", "")
    status = request.args.get("status", "")

    query = "SELECT id, title, genre, year, service, watched FROM movies WHERE TRUE"
    params = []
    if service in SERVICES:
        query += " AND service = %s"
        params.append(service)
    if status == "watched":
        query += " AND watched"
    elif status == "unwatched":
        query += " AND NOT watched"
    query += " ORDER BY watched, created_at DESC"

    with get_conn() as conn:
        movies = conn.execute(query, params).fetchall()
    return render_template("index.html", movies=movies, f_service=service, f_status=status)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data, error = parse_form(request.form)
        if error:
            flash(error, "danger")
            return render_template("form.html", movie=request.form, mode="add")
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO movies (title, genre, year, service, watched) VALUES (%s, %s, %s, %s, %s)",
                (data["title"], data["genre"], data["year"], data["service"], data["watched"]),
            )
        flash(f"Dodano film „{data['title']}”.", "success")
        return redirect(url_for("index"))
    return render_template("form.html", movie={}, mode="add")


@app.route("/edit/<int:movie_id>", methods=["GET", "POST"])
def edit(movie_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, genre, year, service, watched FROM movies WHERE id = %s", (movie_id,)
        ).fetchone()
    if row is None:
        abort(404)

    if request.method == "POST":
        data, error = parse_form(request.form)
        if error:
            flash(error, "danger")
            return render_template("form.html", movie=request.form, mode="edit", movie_id=movie_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE movies SET title=%s, genre=%s, year=%s, service=%s, watched=%s WHERE id=%s",
                (data["title"], data["genre"], data["year"], data["service"], data["watched"], movie_id),
            )
        flash("Zapisano zmiany.", "success")
        return redirect(url_for("index"))

    movie = {
        "title": row[1],
        "genre": row[2] or "",
        "year": row[3] or "",
        "service": row[4],
        "watched": "on" if row[5] else "",
    }
    return render_template("form.html", movie=movie, mode="edit", movie_id=movie_id)


@app.route("/toggle/<int:movie_id>", methods=["POST"])
def toggle(movie_id):
    with get_conn() as conn:
        conn.execute("UPDATE movies SET watched = NOT watched WHERE id = %s", (movie_id,))
    return redirect(request.referrer or url_for("index"))


@app.route("/delete/<int:movie_id>", methods=["POST"])
def delete(movie_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM movies WHERE id = %s", (movie_id,))
    flash("Usunięto film.", "warning")
    return redirect(url_for("index"))


@app.route("/healthz")
def healthz():
    """Liveness probe – proces żyje."""
    return {"status": "ok", "version": APP_VERSION}


@app.route("/readyz")
def readyz():
    """Readiness probe – aplikacja ma połączenie z bazą."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}
    except psycopg.OperationalError:
        return {"status": "db-unavailable"}, 503


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
