from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditEntry
from organizations.models import Category, DietType, Hostel, Organization, Room, StaffProfile
from residents.models import Student
from residents.services import allocate_room

PW = "pw12345!Xy"


class AuditBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org A", slug="a", timezone="Asia/Kolkata")
        self.today = self.org.local_today()
        self.cat = Category.objects.create(organization=self.org, name="National")
        self.diet = DietType.objects.create(organization=self.org, name="Veg")
        self.hostel = Hostel.objects.create(organization=self.org, name="Boys 1", gender="male")
        self.room1 = Room.objects.create(hostel=self.hostel, number="101", capacity=2)
        self.room2 = Room.objects.create(hostel=self.hostel, number="102", capacity=2)
        self.admin = self.make("admin1", "admin")
        self.warden = self.make("warden1", "warden", [self.hostel])

    def make(self, username, role, hostels=(), org=None):
        user = User.objects.create_user(username, password=PW)
        profile = StaffProfile.objects.create(user=user, organization=org or self.org, role=role)
        profile.hostels.set(hostels)
        return profile

    def student(self, roll="S1"):
        s = Student.objects.create(organization=self.org, roll_number=roll, name=f"Student {roll}", gender="male",
                                   category=self.cat, diet=self.diet)
        allocate_room(s, self.room1, self.today - timedelta(days=5))
        return s

    def last(self):
        return AuditEntry.objects.filter(organization=self.org).first()


class RecordingTests(AuditBase):
    def test_moving_a_student_is_logged_with_who_and_what(self):
        s = self.student()
        self.client.login(username="warden1", password=PW)
        self.client.post(reverse("residents:move", args=[s.pk]), {"room": self.room2.pk, "date": self.today.isoformat()})
        entry = self.last()
        self.assertEqual(entry.action, "student.moved")
        self.assertEqual(entry.actor_name, "warden1")
        self.assertEqual(entry.actor, self.warden.user)
        self.assertIn("Student S1", entry.summary)
        self.assertIn("102", entry.summary)

    def test_left_and_readmit_are_logged(self):
        s = self.student()
        self.client.login(username="admin1", password=PW)
        self.client.post(reverse("residents:leave", args=[s.pk]), {"date": self.today.isoformat()})
        self.assertEqual(self.last().action, "student.left")
        self.client.post(reverse("residents:readmit", args=[s.pk]), {"date": self.today.isoformat()})
        self.assertEqual(self.last().action, "student.readmitted")

    def test_registering_and_editing_are_logged(self):
        self.client.login(username="admin1", password=PW)
        data = {"roll_number": "N1", "name": "New Kid", "gender": "male", "category": self.cat.pk, "diet": self.diet.pk,
                "religion": "", "course": "", "department": "", "country": "", "state": "",
                "guardian_name": "", "guardian_phone": ""}
        self.client.post(reverse("residents:create"), data)
        self.assertEqual(self.last().action, "student.registered")
        student = Student.objects.get(roll_number="N1")
        data["name"] = "New Kid Renamed"
        data["status"] = "active"
        self.client.post(reverse("residents:edit", args=[student.pk]), data)
        self.assertEqual(self.last().action, "student.edited")

    def test_a_failed_action_is_not_logged(self):
        s = self.student()
        self.client.login(username="warden1", password=PW)
        self.client.post(reverse("residents:move", args=[s.pk]), {"room": self.room2.pk, "date": "2999-01-01"})
        self.assertFalse(AuditEntry.objects.exists())

    def test_setup_changes_staff_accounts_and_password_changes_are_logged(self):
        self.client.login(username="admin1", password=PW)
        self.client.post(reverse("setup:hostels"), {"name": "Girls 1", "gender": "female"})
        self.assertEqual(self.last().action, "setup.hostels")
        self.client.post(reverse("setup:index"), {"name": "Org A", "timezone": "Asia/Kolkata",
                                                  "roll_call_start": "18:00", "roll_call_end": "20:00"})
        self.assertEqual(self.last().action, "setup.index")
        new_pw = "Brand-new-Pass-8841"
        self.client.post(reverse("accounts:password_change"),
                         {"old_password": PW, "new_password1": new_pw, "new_password2": new_pw})
        self.assertEqual(self.last().action, "account.password_changed")

    def test_entries_belong_to_the_actors_organisation(self):
        s = self.student()
        self.client.login(username="admin1", password=PW)
        self.client.post(reverse("residents:leave", args=[s.pk]), {"date": self.today.isoformat()})
        self.assertEqual(AuditEntry.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(AuditEntry.objects.exclude(organization=self.org).count(), 0)


class ActivityPageTests(AuditBase):
    def entry(self, summary, action="student.moved", actor=None, org=None):
        actor = actor or self.admin.user
        return AuditEntry.objects.create(organization=org or self.org, actor=actor, actor_name=actor.username,
                                         action=action, summary=summary)

    def test_only_admins_can_open_it(self):
        self.assertEqual(self.client.get(reverse("audit:activity")).status_code, 302)
        self.client.login(username="warden1", password=PW)
        self.assertEqual(self.client.get(reverse("audit:activity")).status_code, 403)
        self.client.logout()
        self.client.login(username="admin1", password=PW)
        self.assertEqual(self.client.get(reverse("audit:activity")).status_code, 200)

    def test_shows_only_this_organisations_entries(self):
        other = Organization.objects.create(name="Org B", slug="b")
        other_admin = self.make("admin2", "admin", org=other)
        self.entry("Mine happened")
        self.entry("Theirs happened", actor=other_admin.user, org=other)
        self.client.login(username="admin1", password=PW)
        page = self.client.get(reverse("audit:activity"))
        self.assertContains(page, "Mine happened")
        self.assertNotContains(page, "Theirs happened")
        self.assertNotContains(page, "admin2")

    def test_filters_by_area_person_search_and_date(self):
        self.entry("Moved Alice", "student.moved", self.admin.user)
        self.entry("Added hostel Z", "setup.hostels", self.warden.user)
        self.client.login(username="admin1", password=PW)
        url = reverse("audit:activity")
        by_area = self.client.get(url, {"area": "setup"})
        self.assertContains(by_area, "Added hostel Z")
        self.assertNotContains(by_area, "Moved Alice")
        by_who = self.client.get(url, {"who": self.admin.user.pk})
        self.assertContains(by_who, "Moved Alice")
        self.assertNotContains(by_who, "Added hostel Z")
        by_text = self.client.get(url, {"q": "alice"})
        self.assertContains(by_text, "Moved Alice")
        self.assertNotContains(by_text, "Added hostel Z")
        future = self.client.get(url, {"from": "2999-01-01"})
        self.assertContains(future, "No activity recorded yet")
        self.assertEqual(self.client.get(url, {"from": "garbage", "to": "nonsense"}).status_code, 200)

    def test_pages_and_removed_accounts(self):
        for i in range(55):
            self.entry(f"Event number {i}")
        gone = User.objects.create_user("gone", password=PW)
        e = self.entry("Done by someone later removed", actor=gone)
        gone.delete()
        e.refresh_from_db()
        self.assertEqual(e.actor_name, "gone")
        self.client.login(username="admin1", password=PW)
        first = self.client.get(reverse("audit:activity"))
        self.assertContains(first, "Page 1 of 2")
        second = self.client.get(reverse("audit:activity"), {"page": 2})
        self.assertContains(second, "Event number 0")

    def test_setup_menu_links_to_it(self):
        self.client.login(username="admin1", password=PW)
        self.assertContains(self.client.get(reverse("setup:index")), reverse("audit:activity"))
