import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.management.commands.backup_db import verify_sqlite
from organizations.models import Organization, StaffProfile

PW = "pw12345!Xy"
NEW_PW = "Brand-new-Pass-8841"


class BackupTests(TransactionTestCase):
    # Not TestCase: SQLite's online backup cannot run while the test's wrapping transaction is open.

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        Organization.objects.create(name="Org A", slug="a")

    def run_backup(self, *args):
        out = StringIO()
        call_command("backup_db", "--dir", self.dir, *args, stdout=out)
        return out.getvalue()

    def test_backup_contains_the_data_and_is_verified(self):
        output = self.run_backup()
        files = list(Path(self.dir).glob("hostel-*.sqlite3"))
        self.assertEqual(len(files), 1)
        self.assertIn("Verified", output)
        import sqlite3

        db = sqlite3.connect(files[0])
        self.assertEqual(db.execute("SELECT name FROM organizations_organization").fetchone()[0], "Org A")
        db.close()

    def test_old_backups_are_removed_beyond_keep(self):
        for stamp in ("20200101-000000", "20200102-000000", "20200103-000000"):
            (Path(self.dir) / f"hostel-{stamp}.sqlite3").write_bytes(b"old")
            (Path(self.dir) / f"hostel-{stamp}-media.zip").write_bytes(b"old")
        self.run_backup("--keep", "2")
        names = sorted(p.name for p in Path(self.dir).glob("hostel-*.sqlite3"))
        self.assertEqual(len(names), 2)
        self.assertNotIn("hostel-20200101-000000.sqlite3", names)
        self.assertFalse((Path(self.dir) / "hostel-20200101-000000-media.zip").exists())

    def test_media_can_be_included(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        (Path(media) / "org_logos").mkdir()
        (Path(media) / "org_logos" / "a.png").write_bytes(b"x")
        with override_settings(MEDIA_ROOT=media):
            self.run_backup("--media")
        import zipfile

        archive = zipfile.ZipFile(next(Path(self.dir).glob("*-media.zip")))
        self.assertEqual(archive.namelist(), ["org_logos/a.png"])

    def test_a_broken_file_fails_verification(self):
        broken = Path(self.dir) / "broken.sqlite3"
        broken.write_bytes(b"this is not a database at all")
        with self.assertRaises(CommandError):
            verify_sqlite(broken)

    def test_empty_database_file_is_rejected(self):
        import sqlite3

        empty = Path(self.dir) / "empty.sqlite3"
        sqlite3.connect(empty).close()
        with self.assertRaises(CommandError):
            verify_sqlite(empty)

    def test_postgres_uses_pg_dump_and_never_puts_the_password_on_the_command_line(self):
        from accounts.management.commands import backup_db

        settings_dict = {"NAME": "hostel", "USER": "u", "PASSWORD": "secret", "HOST": "db", "PORT": "5432"}

        def fake_run(command, env, **kwargs):
            Path(command[command.index("--file") + 1]).write_bytes(b"dump")

        with (
            mock.patch.object(backup_db.connection, "vendor", "postgresql"),
            mock.patch.object(backup_db.connection, "settings_dict", settings_dict),
            mock.patch.object(backup_db.shutil, "which", return_value="/usr/bin/pg_dump"),
            mock.patch.object(backup_db.subprocess, "run", side_effect=fake_run) as run,
        ):
            self.run_backup()
        command, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(command[0], "pg_dump")
        self.assertNotIn("secret", " ".join(command))
        self.assertEqual(kwargs["env"]["PGPASSWORD"], "secret")
        self.assertEqual(len(list(Path(self.dir).glob("hostel-*.dump"))), 1)


class PasswordChangeTests(TestCase):
    def setUp(self):
        org = Organization.objects.create(name="Org A", slug="a")
        self.user = User.objects.create_user("warden1", password=PW)
        StaffProfile.objects.create(user=self.user, organization=org, role="warden")
        self.url = reverse("accounts:password_change")

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_changes_the_password_and_keeps_the_user_signed_in(self):
        self.client.login(username="warden1", password=PW)
        response = self.client.post(
            self.url, {"old_password": PW, "new_password1": NEW_PW, "new_password2": NEW_PW}, follow=True
        )
        self.assertContains(response, "password has been changed")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PW))
        self.assertEqual(self.client.get(reverse("accounts:home")).status_code, 200)

    def test_wrong_old_password_is_refused(self):
        self.client.login(username="warden1", password=PW)
        response = self.client.post(
            self.url, {"old_password": "nope", "new_password1": NEW_PW, "new_password2": NEW_PW}
        )
        self.assertContains(response, "old password was entered incorrectly")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PW))

    def test_weak_password_is_refused(self):
        self.client.login(username="warden1", password=PW)
        response = self.client.post(self.url, {"old_password": PW, "new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PW))

    def test_menu_links_to_the_page(self):
        self.client.login(username="warden1", password=PW)
        self.assertContains(self.client.get(reverse("accounts:home")), self.url)


class BackupInsideTransactionTests(TestCase):
    def test_refuses_instead_of_hanging(self):
        with self.assertRaises(CommandError):
            call_command("backup_db", "--dir", tempfile.mkdtemp(), stdout=StringIO())
