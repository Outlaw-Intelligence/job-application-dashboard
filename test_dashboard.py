#!/usr/bin/env python3
"""Tests for the Zeus Job Application Dashboard.

Run with:
    python -m unittest test_dashboard -v
or:
    python test_dashboard.py

Covers: board-card splitting, summary payload shape, and — most importantly —
the submission guardrails. The approval gate is the whole point of this app,
so the state machine around it (authorize -> block -> evidence -> submitted)
is tested through the real HTTP handler, not just the helper functions.
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import app


def _seed_rows(c):
    rows = [
        ("/tmp/acme-packet.md", "acme-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 1.0, "review", "ready for Dylan approval", 1.0),
        ("/tmp/beta-packet.md", "beta-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 2.0, "needs_changes", "needs salary answer", 2.0),
        ("/tmp/blocked-packet.md", "blocked-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 4.0, "submission_blocked", "hidden required employer field", 4.0),
        ("/tmp/submitted-packet.md", "submitted-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 5.0, "submitted", "sent to employer", 5.0),
        ("/tmp/unverified-packet.md", "unverified-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 5.5, "submitted", "marked submitted, no receipt yet", 5.5),
        ("/tmp/mercury-packet.md", "mercury-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 6.0, "submit_authorized", "authorized for Mercury", 6.0),
        ("/tmp/general-resume.md", "general-resume.md", "Career Packets", "Resume / CV assets", ".md", 100, 3.0, "review", "asset, not application", 3.0),
    ]
    c.executemany("""insert into files(path,name,root_label,purpose,suffix,size,mtime,status,notes,updated_at)
        values(?,?,?,?,?,?,?,?,?,?)""", rows)
    # Only packets with employer confirmation evidence count as submitted.
    c.execute("update files set confirmation_evidence='employer-receipt-123' where path='/tmp/submitted-packet.md'")
    c.commit()


class DashboardBoardCardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        self.old_sources = app.JOB_SOURCE_FILE
        app.DB = Path(self.tmp.name) / "dashboard.sqlite3"
        app.JOB_SOURCE_FILE = Path(self.tmp.name) / "job-search-sources.json"
        c = app.conn()
        _seed_rows(c)
        c.close()

    def tearDown(self):
        app.DB = self.old_db
        app.JOB_SOURCE_FILE = self.old_sources
        self.tmp.cleanup()

    def test_board_cards_split_approval_queue_from_attention_queue(self):
        cards = app.board_cards()

        submitted = next(card for card in cards if card["id"] == "submitted_queue")
        mercury = next(card for card in cards if card["id"] == "mercury_queue")
        blocked = next(card for card in cards if card["id"] == "submission_blocked_queue")
        approval = next(card for card in cards if card["id"] == "approval_queue")
        attention = next(card for card in cards if card["id"] == "attention_queue")

        # Both submitted rows appear on the board; only the evidenced one counts
        # as a confirmed submission in the summary (see next test).
        self.assertEqual(submitted["count"], 2)

        self.assertEqual(mercury["count"], 1)
        self.assertEqual(mercury["items"][0]["name"], "mercury-packet.md")
        self.assertEqual(mercury["items"][0]["status"], "submit_authorized")

        self.assertEqual(blocked["count"], 1)
        self.assertEqual(blocked["items"][0]["name"], "blocked-packet.md")
        self.assertEqual(blocked["items"][0]["status"], "submission_blocked")

        self.assertEqual(approval["count"], 1)
        self.assertEqual(approval["items"][0]["name"], "acme-packet.md")
        self.assertEqual(approval["items"][0]["status"], "review")

        self.assertEqual(attention["count"], 1)
        self.assertEqual(attention["items"][0]["name"], "beta-packet.md")
        self.assertEqual(attention["items"][0]["status"], "needs_changes")

    def test_summary_counts_only_evidenced_submissions(self):
        summary = app.summary_payload()
        self.assertIn("board_cards", summary)
        self.assertEqual([card["id"] for card in summary["board_cards"]], ["submitted_queue", "mercury_queue", "submission_blocked_queue", "approval_queue", "attention_queue"])
        # submitted-packet.md has evidence; unverified-packet.md does not.
        self.assertEqual(summary["submitted"], 1)
        self.assertEqual(summary["submitted_unverified"], 1)
        self.assertEqual(summary["submit_authorized"], 1)
        self.assertEqual(summary["submission_blocked"], 1)
        self.assertEqual(summary["submission_blockers"][0]["name"], "blocked-packet.md")

    def test_summary_exposes_source_radar_and_job_goal(self):
        app.JOB_SOURCE_FILE.write_text(json.dumps([
            {"name": "Instagram remote job lead", "url": "https://www.instagram.com/p/DY2OI5JEtp_/", "type": "social", "status": "to triage"}
        ]))

        summary = app.summary_payload()

        goal = summary["job_goal"]
        for key in ("deadline", "monthly_target", "daily_target", "quality_bar"):
            self.assertIn(key, goal)
            self.assertTrue(goal[key], f"job_goal[{key!r}] should be non-empty")
        self.assertEqual(summary["job_sources"][0]["name"], "Instagram remote job lead")


class BlockerTaxonomyTest(unittest.TestCase):
    def test_aliases_normalize(self):
        self.assertEqual(app._normalize_blocker_reason("login"), "login_required")
        self.assertEqual(app._normalize_blocker_reason("auth"), "login_required")
        self.assertEqual(app._normalize_blocker_reason("2fa"), "email_verification_code_needed")
        self.assertEqual(app._normalize_blocker_reason("CAPTCHA"), "captcha")
        self.assertEqual(app._normalize_blocker_reason("cover_letter_missing"), "missing_cover_letter")
        self.assertEqual(app._normalize_blocker_reason("max_attempts"), "max_attempts_reached")

    def test_unknown_and_empty_fall_back_to_manual_review(self):
        self.assertEqual(app._normalize_blocker_reason("something weird"), "manual_review_required")
        self.assertEqual(app._normalize_blocker_reason(""), "manual_review_required")
        self.assertEqual(app._normalize_blocker_reason(None), "manual_review_required")


class RefreshPruneTest(unittest.TestCase):
    def test_refresh_prunes_deleted_files_but_keeps_live_ones(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old_db, old_roots = app.DB, app.INDEX_ROOTS
        app.DB = Path(tmp.name) / "dashboard.sqlite3"
        packets = Path(tmp.name) / "packets"
        packets.mkdir()
        app.INDEX_ROOTS = {"Test": packets}
        try:
            live = packets / "acme-resume.md"
            dead = packets / "beta-resume.md"
            live.write_text("resume")
            dead.write_text("resume")
            first = app.refresh()
            self.assertEqual(first["indexed"], 2)
            self.assertEqual(first["pruned"], 0)

            dead.unlink()
            second = app.refresh()
            self.assertEqual(second["indexed"], 1)
            self.assertEqual(second["pruned"], 1)

            c = app.conn()
            try:
                names = {r[0] for r in c.execute("select name from files")}
            finally:
                c.close()
            self.assertEqual(names, {"acme-resume.md"})
        finally:
            app.DB, app.INDEX_ROOTS = old_db, old_roots

    def test_refresh_never_prunes_rows_outside_index_roots(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old_db, old_roots = app.DB, app.INDEX_ROOTS
        app.DB = Path(tmp.name) / "dashboard.sqlite3"
        app.INDEX_ROOTS = {"Test": Path(tmp.name) / "packets"}
        try:
            c = app.conn()
            c.execute("""insert into files(path,name,root_label,purpose,suffix,size,mtime,status,notes,updated_at)
                values(?,?,?,?,?,?,?,?,?,?)""",
                ("/tmp/manual-import.md", "manual-import.md", "Manual", "Application packets / tailored role materials",
                 ".md", 10, 1.0, "review", "hand-added", 1.0))
            c.commit()
            c.close()
            result = app.refresh()
            self.assertEqual(result["pruned"], 0)
            c = app.conn()
            try:
                self.assertEqual(c.execute("select count(*) from files where path='/tmp/manual-import.md'").fetchone()[0], 1)
            finally:
                c.close()
        finally:
            app.DB, app.INDEX_ROOTS = old_db, old_roots


class SubmissionGuardrailTest(unittest.TestCase):
    """Exercise the approval-gate state machine through the real HTTP handler."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_db = app.DB
        cls.old_sources = app.JOB_SOURCE_FILE
        app.DB = Path(cls.tmp.name) / "dashboard.sqlite3"
        app.JOB_SOURCE_FILE = Path(cls.tmp.name) / "job-search-sources.json"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()
        app.DB = cls.old_db
        app.JOB_SOURCE_FILE = cls.old_sources
        cls.tmp.cleanup()

    def setUp(self):
        c = app.conn()
        c.execute("delete from files")
        c.execute("delete from audit")
        c.commit()
        c.close()
        self.packet_dir = Path(self.tmp.name) / "packets"
        self.packet_dir.mkdir(exist_ok=True)

    # -- helpers ---------------------------------------------------------
    def _post(self, path, payload=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload or {}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def _insert_packet(self, name="acme-packet.md", with_materials=True, with_apply_url=True, status="review"):
        packet = self.packet_dir / name
        lines = [f"# {name}"]
        if with_apply_url:
            lines.append("- Apply URL: https://example.com/apply/acme")
        packet.write_text("\n".join(lines))
        resume = self.packet_dir / "resume.pdf"
        cover = self.packet_dir / "cover.pdf"
        if with_materials:
            resume.write_text("resume")
            cover.write_text("cover")
        c = app.conn()
        c.execute("""insert into files(path,name,root_label,purpose,suffix,size,mtime,status,notes,updated_at,resume_path,cover_letter_path)
            values(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(packet), name, "Career Packets", "Application packets / tailored role materials",
             ".md", 100, 1.0, status, "", 1.0,
             str(resume) if with_materials else "", str(cover) if with_materials else ""))
        fid = c.execute("select id from files where path=?", (str(packet),)).fetchone()[0]
        c.commit()
        c.close()
        return fid

    def _row(self, fid):
        c = app.conn()
        try:
            return dict(c.execute("select * from files where id=?", (fid,)).fetchone())
        finally:
            c.close()

    # -- tests -----------------------------------------------------------
    def test_status_endpoint_rejects_direct_submitted(self):
        fid = self._insert_packet(status="submit_authorized")
        code, body = self._post(f"/api/files/{fid}/status", {"status": "submitted"})
        self.assertEqual(code, 409)
        self.assertFalse(body.get("ok", True))
        self.assertEqual(self._row(fid)["status"], "submit_authorized")

    def test_submit_blocked_when_materials_missing(self):
        fid = self._insert_packet(with_materials=False)
        code, body = self._post(f"/api/files/{fid}/submit", {"notes": "go"})
        self.assertEqual(code, 409)
        row = self._row(fid)
        self.assertEqual(row["status"], "submission_blocked")
        self.assertIn("missing_resume", row["blocker_reason"])
        self.assertIn("missing_cover_letter", row["blocker_reason"])

    def test_submit_blocked_when_apply_url_missing(self):
        fid = self._insert_packet(with_apply_url=False)
        code, _ = self._post(f"/api/files/{fid}/submit", {"notes": "go"})
        self.assertEqual(code, 409)
        self.assertIn("broken_apply_link", self._row(fid)["blocker_reason"])

    def test_submit_authorized_when_packet_complete(self):
        fid = self._insert_packet()
        code, body = self._post(f"/api/files/{fid}/submit", {"notes": "looks good"})
        self.assertEqual(code, 200)
        row = self._row(fid)
        self.assertEqual(row["status"], "submit_authorized")
        c = app.conn()
        try:
            audit = c.execute("select action from audit where action='submit_authorized'").fetchone()
        finally:
            c.close()
        self.assertIsNotNone(audit)

    def test_submitted_requires_evidence(self):
        fid = self._insert_packet(status="submit_authorized")
        code, _ = self._post(f"/api/files/{fid}/submitted", {"notes": "sent it"})
        self.assertEqual(code, 409)
        self.assertEqual(self._row(fid)["status"], "submit_authorized")

        code, _ = self._post(f"/api/files/{fid}/submitted", {"notes": "sent it", "evidence": "confirmation #12345"})
        self.assertEqual(code, 200)
        row = self._row(fid)
        self.assertEqual(row["status"], "submitted")
        self.assertEqual(row["confirmation_evidence"], "confirmation #12345")

    def test_attempt_cap_blocks_after_two(self):
        fid = self._insert_packet()
        code, first = self._post(f"/api/files/{fid}/attempt")
        self.assertEqual(code, 200)
        self.assertEqual(first["attempt_count"], 1)
        self.assertEqual(self._row(fid)["status"], "review")

        code, second = self._post(f"/api/files/{fid}/attempt")
        self.assertEqual(code, 200)
        self.assertEqual(second["attempt_count"], 2)
        row = self._row(fid)
        self.assertEqual(row["status"], "submission_blocked")
        self.assertIn("max_attempts_reached", row["blocker_reason"])

    def test_submit_action_stays_disabled(self):
        code, body = self._post("/api/action", {"id": "submit_application", "confirm": True})
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
