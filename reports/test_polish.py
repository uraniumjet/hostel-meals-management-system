import io
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook
from PIL import Image

from audit.models import AuditEntry
from reports import builders
from reports.exporters import to_pdf, to_xlsx
from reports.tables import Table
from reports.tests import Fixture

MEDIA = tempfile.mkdtemp()


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGBA", (200, 100), (30, 64, 175, 255)).save(buffer, "PNG")
    return buffer.getvalue()


class ExcelAndPdfTests(SimpleTestCase):
    table = Table("Title", "Sub", ["Name", "Count"], [["=cmd|calc", 3], ["Total", 3]], ["a note"], total_row=True)

    def test_xlsx_has_headers_data_and_never_a_formula(self):
        book = load_workbook(io.BytesIO(to_xlsx(self.table, heading="Generated now")))
        sheet = book.active
        self.assertEqual(sheet["A1"].value, "Title")
        self.assertEqual(sheet["A5"].value, "Name")
        self.assertEqual(sheet["A6"].value, "=cmd|calc")
        self.assertEqual(sheet["A6"].data_type, "s")
        self.assertEqual(sheet["B6"].value, 3)
        self.assertTrue(sheet["A7"].font.bold)
        self.assertFalse(sheet["A6"].font.bold)
        self.assertEqual(sheet.freeze_panes, "A6")

    def test_pdf_with_and_without_a_logo(self):
        self.assertTrue(to_pdf(self.table, logo=png_bytes()).startswith(b"%PDF"))
        self.assertTrue(to_pdf(self.table, logo=b"not an image").startswith(b"%PDF"))
        self.assertTrue(to_pdf(self.table).startswith(b"%PDF"))


class OccupancyTests(Fixture):
    def test_counts_rooms_beds_residents_and_free_beds(self):
        table = builders.occupancy(self.admin, None, None)
        self.assertEqual(table.headers, ["Hostel", "Rooms", "Beds", "Residents", "Free beds", "Occupancy"])
        self.assertEqual(table.rows[0], ["Boys 1", 1, 4, 3, 1, "75%"])
        self.assertEqual(table.rows[1], ["Boys 2", 1, 4, 1, 3, "25%"])
        self.assertEqual(table.rows[2], ["Total", 2, 8, 4, 4, "50%"])
        self.assertTrue(table.total_row)

    def test_students_who_left_do_not_count_and_scope_applies(self):
        from residents.services import mark_left

        mark_left(self.alice, self.org.local_today())
        self.assertEqual(builders.occupancy(self.admin, None, None).rows[0][3], 2)
        warden_table = builders.occupancy(self.warden, None, None)
        self.assertEqual([row[0] for row in warden_table.rows], ["Boys 1", "Total"])
        only = builders.occupancy(self.admin, None, None, self.h2)
        self.assertEqual([row[0] for row in only.rows], ["Boys 2", "Total"])

    def test_empty_hostel_shows_a_dash_not_a_division_error(self):
        from organizations.models import Hostel

        Hostel.objects.create(organization=self.org, name="Empty", gender="male")
        rows = {row[0]: row for row in builders.occupancy(self.admin, None, None).rows}
        self.assertEqual(rows["Empty"], ["Empty", 0, 0, 0, 0, "-"])


@override_settings(MEDIA_ROOT=MEDIA)
class PolishViewTests(Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, MEDIA, True)

    def setUp(self):
        super().setUp()
        self.seed_meals()
        self.client.login(username="admin", password="pw12345!")
        self.params = {"period": "custom", "start": "2026-11-10", "end": "2026-11-11"}

    def test_excel_download(self):
        response = self.client.get(reverse("reports:report", args=["meals-daily"]), {**self.params, "format": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn(".xlsx", response["Content-Disposition"])
        sheet = load_workbook(io.BytesIO(response.content)).active
        self.assertEqual(sheet["A1"].value, "Meals served per day")

    def test_occupancy_report_in_every_format(self):
        url = reverse("reports:report", args=["occupancy"])
        self.assertContains(self.client.get(url, self.params), "Boys 1")
        for fmt in ("csv", "xlsx", "pdf"):
            self.assertEqual(self.client.get(url, {**self.params, "format": fmt}).status_code, 200)

    def test_pdf_includes_the_logo_when_the_organisation_has_one(self):
        self.org.logo.save("logo.png", SimpleUploadedFile("logo.png", png_bytes()), save=True)
        response = self.client.get(reverse("reports:report", args=["absences"]), {**self.params, "format": "pdf"})
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(b"/Image", response.content)

    def test_totals_row_is_bold_on_the_page(self):
        page = self.client.get(reverse("reports:report", args=["meals-daily"]), self.params)
        self.assertContains(page, 'class="fw-bold table-active"', count=1)

    def test_index_has_excel_buttons_and_period_shortcuts(self):
        page = self.client.get(reverse("reports:index"))
        self.assertContains(page, "format=xlsx")
        self.assertContains(page, "Download Excel")
        today = self.org.local_today()
        yesterday = today - timedelta(days=1)
        self.assertContains(page, "Yesterday")
        self.assertContains(page, f"date={yesterday.isoformat()}")
        self.assertContains(page, "This month")

    def test_shortcuts_keep_the_chosen_hostel(self):
        page = self.client.get(reverse("reports:index"), {"period": "day", "date": "2026-11-10", "hostel": self.h1.pk})
        self.assertContains(page, f"hostel={self.h1.pk}")

    def test_downloads_are_logged_but_viewing_is_not(self):
        url = reverse("reports:report", args=["absences"])
        self.client.get(url, self.params)
        self.assertFalse(AuditEntry.objects.exists())
        self.client.get(url, {**self.params, "format": "csv"})
        self.client.get(url, {**self.params, "format": "xlsx"})
        entries = list(AuditEntry.objects.order_by("id"))
        self.assertEqual([e.action for e in entries], ["report.downloaded"] * 2)
        self.assertIn("Absent without permission", entries[0].summary)
        self.assertIn("CSV", entries[0].summary)
        self.assertEqual(entries[0].actor_name, "admin")

    def test_warden_downloads_stay_scoped_and_are_logged(self):
        self.client.logout()
        self.client.login(username="warden", password="pw12345!")
        response = self.client.get(reverse("reports:report", args=["occupancy"]), {**self.params, "format": "csv"})
        text = response.content.decode("utf-8-sig")
        self.assertIn("Boys 1", text)
        self.assertNotIn("Boys 2", text)
        self.assertEqual(AuditEntry.objects.get().actor_name, "warden")
