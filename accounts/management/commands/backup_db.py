"""Take a consistent backup of the database (and optionally the uploaded photos and logos).

    python manage.py backup_db                      # backups/hostel-YYYYmmdd-HHMMSS.sqlite3 (or .dump for PostgreSQL)
    python manage.py backup_db --dir /data/backups --keep 14 --media

SQLite is copied with SQLite's own online backup, so it is safe while the app is running. PostgreSQL is written with
pg_dump (it must be installed). Every SQLite backup is opened again and checked before the command reports success.
"""
import os
import shutil
import sqlite3
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

PREFIX = "hostel-"


def verify_sqlite(path):
    """Open a SQLite backup and check it is complete. Returns the number of tables."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
        tables = db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    except sqlite3.DatabaseError as error:
        raise CommandError(f"Backup is not a readable database: {error}") from error
    finally:
        db.close()
    if result != "ok":
        raise CommandError(f"Backup failed its integrity check: {result}")
    if tables == 0:
        raise CommandError("Backup contains no tables.")
    return tables


class Command(BaseCommand):
    help = "Back up the database (and optionally the media folder) to a timestamped file."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=os.environ.get("BACKUP_DIR", "backups"), help="Where to write backups.")
        parser.add_argument("--keep", type=int, default=14, help="How many backups to keep (0 keeps all).")
        parser.add_argument("--media", action="store_true", help="Also zip the uploaded photos and logos.")

    def handle(self, *args, **options):
        target = Path(options["dir"])
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        engine = connection.vendor
        if engine == "sqlite":
            path = target / f"{PREFIX}{stamp}.sqlite3"
            self.backup_sqlite(path)
        elif engine == "postgresql":
            path = target / f"{PREFIX}{stamp}.dump"
            self.backup_postgres(path)
        else:
            raise CommandError(f"Backups are not supported for {engine}.")
        self.stdout.write(self.style.SUCCESS(f"Database backup written to {path} ({path.stat().st_size // 1024} KB)."))
        if options["media"]:
            self.stdout.write(self.style.SUCCESS(f"Media backup written to {self.backup_media(target, stamp)}."))
        if options["keep"] > 0:
            self.prune(target, options["keep"])

    def backup_sqlite(self, path):
        connection.ensure_connection()
        if connection.in_atomic_block:
            # SQLite's online backup waits forever for a connection that is inside an open transaction.
            raise CommandError("Cannot back up from inside a database transaction.")
        destination = sqlite3.connect(path)
        try:
            connection.connection.backup(destination)
        finally:
            destination.close()
        try:
            tables = verify_sqlite(path)
        except CommandError:
            path.unlink(missing_ok=True)
            raise
        self.stdout.write(f"Verified: opens cleanly, {tables} tables.")

    def backup_postgres(self, path):
        if shutil.which("pg_dump") is None:
            raise CommandError("pg_dump was not found. Install the PostgreSQL client tools.")
        db = connection.settings_dict
        command = ["pg_dump", "--format=custom", "--file", str(path), "--dbname", db["NAME"]]
        for flag, key in (("--host", "HOST"), ("--port", "PORT"), ("--username", "USER")):
            if db.get(key):
                command += [flag, str(db[key])]
        env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
        try:
            subprocess.run(command, env=env, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            path.unlink(missing_ok=True)
            raise CommandError(f"pg_dump failed: {error.stderr.strip()}") from error
        if not path.exists() or path.stat().st_size == 0:
            raise CommandError("pg_dump produced an empty file.")

    def backup_media(self, target, stamp):
        media = Path(settings.MEDIA_ROOT)
        path = target / f"{PREFIX}{stamp}-media.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            if media.is_dir():
                for file in sorted(media.rglob("*")):
                    if file.is_file():
                        archive.write(file, file.relative_to(media))
        return path

    def prune(self, target, keep):
        """Keep the newest `keep` database backups (and delete the media zips that belong to removed ones)."""
        databases = sorted(p for p in target.glob(f"{PREFIX}*") if p.suffix in {".sqlite3", ".dump"})
        for old in databases[:-keep]:
            old.unlink()
            old.with_name(old.stem + "-media.zip").unlink(missing_ok=True)
            self.stdout.write(f"Removed old backup {old.name}.")
