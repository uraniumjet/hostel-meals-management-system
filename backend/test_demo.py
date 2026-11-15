import shutil
import tempfile
from io import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from organizations.models import Organization, StaffProfile
from residents.models import Student

PW = "pw12345!Xy"


class DemoFixture(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Demo Org", slug="d")
        self.admin = User.objects.create_user("demo_admin", password=PW)
        StaffProfile.objects.create(user=self.admin, organization=self.org, role="admin")
        self.client.login(username="demo_admin", password=PW)


class NormalModeTests(DemoFixture):
    def test_nothing_is_blocked_and_there_is_no_banner(self):
        self.assertEqual(self.client.get(reverse("accounts:password_change")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("accounts:home")), "Public demo")
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("accounts:login")), "Demo logins")


@override_settings(DEMO_MODE=True, DEMO_PASSWORD="shown-on-page-1")
class DemoModeTests(DemoFixture):
    def test_banner_and_logins_are_shown(self):
        self.assertContains(self.client.get(reverse("accounts:home")), "Public demo")
        self.client.logout()
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, "demo_admin")
        self.assertContains(page, "shown-on-page-1")

    def test_account_pages_are_refused_with_a_message(self):
        for name, args in (("accounts:password_change", []), ("setup:staff_new", [])):
            response = self.client.get(reverse(name, args=args), follow=True)
            self.assertContains(response, "switched off in the public demo")
        before = self.admin.password
        self.client.post(reverse("accounts:password_change"), {"old_password": PW, "new_password1": "Zq-81x-newpass", "new_password2": "Zq-81x-newpass"})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.password, before)

    def test_staff_edit_and_import_are_refused(self):
        staff_id = self.admin.staff_profile.pk
        for url in (reverse("setup:staff_edit", args=[staff_id]), reverse("residents:import")):
            self.assertContains(self.client.get(url, follow=True), "switched off in the public demo")

    def test_uploads_are_refused_but_normal_posts_work(self):
        photo = SimpleUploadedFile("a.png", b"x", content_type="image/png")
        response = self.client.post(reverse("setup:index"), {"name": "Hack", "logo": photo}, follow=True)
        self.assertContains(response, "switched off in the public demo")
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Demo Org")
        ok = self.client.post(reverse("setup:index"), {"name": "Renamed", "timezone": "UTC",
                                                       "roll_call_start": "18:00", "roll_call_end": "20:00"})
        self.assertEqual(ok.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Renamed")

    def test_signup_is_switched_off(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:signup")).status_code, 302)  # sent to sign in with a message
        self.assertFalse(Organization.objects.filter(name="Intruder").exists())
        self.client.post(reverse("accounts:signup"), {"organization": "Intruder"})
        self.assertFalse(Organization.objects.filter(name="Intruder").exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BootDemoTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, settings.MEDIA_ROOT, True)

    def run_boot(self):
        out = StringIO()
        call_command("boot_demo", "--students", "6", "--days", "3", stdout=out)
        return out.getvalue()

    @override_settings(DEMO_PASSWORD="boot-pass-123")
    def test_seeds_an_empty_database_once(self):
        self.assertIn("Demo data is ready", self.run_boot())
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(Student.objects.count(), 6)
        user = User.objects.get(username="demo_admin")
        self.assertTrue(user.check_password("boot-pass-123"))
        self.assertIn("not re-seeded", self.run_boot())
        self.assertEqual(Student.objects.count(), 6)

    def test_never_touches_a_database_that_already_has_an_organisation(self):
        Organization.objects.create(name="Real client", slug="real")
        self.assertIn("not re-seeded", self.run_boot())
        self.assertEqual(Organization.objects.count(), 1)
