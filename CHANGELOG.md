# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the
project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Multi-organisation core: organisations, categories, diet types, hostels, rooms, staff roles (admin and warden).
- Student registration with photo (upload or webcam), room allocation with history, CSV/Excel import with preview.
- Meal counters: QR / roll number / name lookup, meal windows, one meal per student per day, proxy collection.
- Special periods (for example Ramadan) with their own meal times, skipped meals and per-day time changes.
- Night roll call, exit permits with the days-until-absent countdown, and absence tracking (no fines are charged).
- Reports (meals per day, meals per student, attendance, absences) as web pages, CSV and PDF.
- Modern responsive interface with dark mode.
- Self-service organisation sign-up and in-app Setup screens for everything an admin configures.
- `seed_test_data` command with fictional students, history, leave in every state and a running Ramadan period.
- Environment-driven settings, production hardening, health endpoint `/healthz/`, protected photo serving.
- Student lifecycle (change room, mark as left, re-admit) and printable credit-card-size ID cards (PDF, one per page or A4 sheets) with the organisation logo set in Setup.
- `backup_db` command (verified SQLite or pg_dump backups, optional media zip, retention) with restore steps in `docs/deployment.md`.
- Change-password page for every user.
- All-rights-reserved licence (source readable for evaluation; commercial use needs permission).
- Public demo mode (`DEMO_MODE=1`): self-seeding fictional data, shown demo logins, banner, and account changes and uploads switched off; `render.yaml` for a free Render deployment.
- Reports: Excel (.xlsx) export, organisation logo in PDF headers, bold totals rows, a Hostel occupancy report, quick period buttons (today, yesterday, this week, this month); report downloads are recorded in the activity log.
- Activity log (Setup → Activity, admins only): student registrations, edits, room moves, leaving and re-admission, imports, setup changes, staff accounts and password changes, with filters.
- Dockerfile, Docker Compose, GitHub Actions CI (lint, tests on three Python versions, PostgreSQL, deployment checks, image build).

### Removed
- The earlier prototype apps and their API.
