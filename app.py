from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sqlite3
from pathlib import Path
from datetime import datetime
import uuid
import math
from PIL import Image

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "library.db"
STATIC_DIR = BASE_DIR / "static"
COVERS_DIR = STATIC_DIR / "covers"
COLLAGE_PATH = STATIC_DIR / "collage.jpg"

COVERS_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

GENRES = [
    "Romance",
    "Romantasy",
    "Fantasy",
    "Dark Romance",
    "Contemporary Romance",
    "Thriller",
    "Mystery",
    "Horror",
    "Sci-Fi",
    "Historical",
    "Young Adult",
    "New Adult",
    "Non-fiction",
    "Other",
]


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def author_first_name(author: str) -> str:
    return author.strip().split()[0].lower() if author.strip() else ""


# Create base table
with get_db() as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            author_first TEXT NOT NULL,
            edition TEXT,
            genre TEXT,
            cover_filename TEXT,
            created_at TEXT NOT NULL
        )
    """)

# DB upgrade: add hover_message if missing (safe)
with get_db() as db:
    cols = [row["name"] for row in db.execute("PRAGMA table_info(books)").fetchall()]
    if "hover_message" not in cols:
        db.execute("ALTER TABLE books ADD COLUMN hover_message TEXT")


def generate_cover_collage():
    """
    Creates/updates static/collage.jpg using all uploaded covers in static/covers.
    """
    covers = sorted(COVERS_DIR.glob("*"))
    covers = [p for p in covers if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]

    if not covers:
        if COLLAGE_PATH.exists():
            COLLAGE_PATH.unlink()
        return

    tile_w, tile_h = 220, 320
    n = len(covers)

    cols = min(8, max(3, int(math.sqrt(n) * 2)))
    rows = math.ceil(n / cols)

    collage = Image.new("RGB", (cols * tile_w, rows * tile_h), (255, 255, 255))

    for i, path in enumerate(covers):
        r = i // cols
        c = i % cols
        try:
            img = Image.open(path).convert("RGB")
            img = img.resize((tile_w, tile_h))
            collage.paste(img, (c * tile_w, r * tile_h))
        except Exception:
            continue

    collage.save(COLLAGE_PATH, quality=85)


@app.get("/", response_class=HTMLResponse)
def intro(request: Request):
    return templates.TemplateResponse("intro.html", {"request": request})


@app.get("/home", response_class=HTMLResponse)
def home(request: Request):
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS c FROM books").fetchone()["c"]
    db.close()
    return templates.TemplateResponse("home.html", {"request": request, "total": total})


@app.get("/add", response_class=HTMLResponse)
def add_form(request: Request):
    return templates.TemplateResponse("add.html", {"request": request, "genres": GENRES})


@app.post("/add")
async def add_book(
    title: str = Form(...),
    author: str = Form(...),
    edition: str = Form(""),
    genre: str = Form("Other"),
    hover_message: str = Form(""),
    cover: UploadFile | None = File(None),
):
    cover_filename = None

    if cover and cover.filename:
        suffix = Path(cover.filename).suffix.lower()
        cover_filename = f"{uuid.uuid4().hex}{suffix}"
        (COVERS_DIR / cover_filename).write_bytes(await cover.read())

    created_at = datetime.now().isoformat(timespec="seconds")

    db = get_db()
    db.execute(
        """
        INSERT INTO books
        (title, author, author_first, edition, genre, cover_filename, created_at, hover_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            author,
            author_first_name(author),
            edition,
            genre,
            cover_filename,
            created_at,
            hover_message,
        ),
    )
    db.commit()
    db.close()

    generate_cover_collage()
    return RedirectResponse(url="/collection", status_code=303)


@app.get("/collection", response_class=HTMLResponse)
def collection(request: Request, sort: str = "date"):
    order_by = {
        "date": "created_at DESC",
        "title": "title COLLATE NOCASE ASC",
        "genre": "genre COLLATE NOCASE ASC, title COLLATE NOCASE ASC",
        "author": "author_first COLLATE NOCASE ASC, author COLLATE NOCASE ASC",
    }.get(sort, "created_at DESC")

    db = get_db()
    books = db.execute(f"SELECT * FROM books ORDER BY {order_by}").fetchall()
    db.close()

    return templates.TemplateResponse(
        "collection.html",
        {"request": request, "books": books, "sort": sort},
    )


@app.get("/book/{book_id}/edit", response_class=HTMLResponse)
def edit_form(request: Request, book_id: int):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    db.close()

    if not book:
        return RedirectResponse(url="/collection", status_code=303)

    return templates.TemplateResponse(
        "edit.html",
        {"request": request, "book": book, "genres": GENRES},
    )


@app.post("/book/{book_id}/edit")
async def edit_book(
    book_id: int,
    title: str = Form(...),
    author: str = Form(...),
    edition: str = Form(""),
    genre: str = Form("Other"),
    hover_message: str = Form(""),
    cover: UploadFile | None = File(None),
):
    db = get_db()
    existing = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not existing:
        db.close()
        return RedirectResponse(url="/collection", status_code=303)

    cover_filename = existing["cover_filename"]

    if cover and cover.filename:
        suffix = Path(cover.filename).suffix.lower()
        cover_filename = f"{uuid.uuid4().hex}{suffix}"
        (COVERS_DIR / cover_filename).write_bytes(await cover.read())

    db.execute(
        """
        UPDATE books
        SET title = ?, author = ?, author_first = ?, edition = ?, genre = ?,
            hover_message = ?, cover_filename = ?
        WHERE id = ?
        """,
        (
            title,
            author,
            author_first_name(author),
            edition,
            genre,
            hover_message,
            cover_filename,
            book_id,
        ),
    )
    db.commit()
    db.close()

    generate_cover_collage()
    return RedirectResponse(url="/collection", status_code=303)


@app.post("/book/{book_id}/delete")
def delete_book(book_id: int):
    db = get_db()
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()
    db.close()

    generate_cover_collage()
    return RedirectResponse(url="/collection", status_code=303)
