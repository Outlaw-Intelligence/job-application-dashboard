#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

import app


class DashboardBoardCardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        self.old_sources = app.JOB_SOURCE_FILE
        app.DB = Path(self.tmp.name) / "dashboard.sqlite3"
        app.JOB_SOURCE_FILE = Path(self.tmp.name) / "job-search-sources.json"
        c = app.conn()
        rows = [
            ("/tmp/acme-packet.md", "acme-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 1.0, "review", "ready for Dylan approval", 1.0),
            ("/tmp/beta-packet.md", "beta-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 2.0, "needs_changes", "needs salary answer", 2.0),
            ("/tmp/blocked-packet.md", "blocked-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 4.0, "submission_blocked", "hidden required employer field", 4.0),
            ("/tmp/submitted-packet.md", "submitted-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 5.0, "submitted", "sent to employer", 5.0),
            ("/tmp/mercury-packet.md", "mercury-packet.md", "Career Packets", "Application packets / tailored role materials", ".md", 100, 6.0, "submit_authorized", "authorized for Mercury", 6.0),
            ("/tmp/general-resume.md", "general-resume.md", "Career Packets", "Resume / CV assets", ".md", 100, 3.0, "review", "asset, not application", 3.0),
        ]
        c.executemany("""insert into files(path,name,root_label,purpose,suffix,size,mtime,status,notes,updated_at)
            values(?,?,?,?,?,?,?,?,?,?)""", rows)
        c.commit()
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

        self.assertEqual(submitted["count"], 1)
        self.assertEqual(submitted["items"][0]["name"], "submitted-packet.md")
        self.assertEqual(submitted["items"][0]["status"], "submitted")

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

    def test_summary_exposes_board_cards_for_the_frontend(self):
        summary = app.summary_payload()
        self.assertIn("board_cards", summary)
        self.assertEqual([card["id"] for card in summary["board_cards"]], ["submitted_queue", "mercury_queue", "submission_blocked_queue", "approval_queue", "attention_queue"])
        self.assertEqual(summary["submitted"], 1)
        self.assertEqual(summary["submit_authorized"], 1)
        self.assertEqual(summary["submission_blocked"], 1)
        self.assertEqual(summary["submission_blockers"][0]["name"], "blocked-packet.md")

    def test_summary_exposes_source_radar_and_july_goal(self):
        app.JOB_SOURCE_FILE.write_text(json.dumps([
            {"name": "Instagram remote job lead", "url": "https://www.instagram.com/p/DY2OI5JEtp_/", "type": "social", "status": "to triage"}
        ]))

        summary = app.summary_payload()

        self.assertEqual(summary["job_goal"]["deadline"], "July")
        self.assertEqual(summary["job_goal"]["monthly_target"], "leave current job for full-time remote AI/AI-adjacent work")
        self.assertEqual(summary["job_goal"]["daily_target"], "10+ submitted applications/day")
        self.assertIn("tailored", summary["job_goal"]["quality_bar"])
        self.assertEqual(summary["job_sources"][0]["name"], "Instagram remote job lead")


if __name__ == "__main__":
    unittest.main()
