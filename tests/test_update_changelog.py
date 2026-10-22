"""Tests de la lecture du changelog (scripts/update_changelog.py).

Défaut visé (21 oct 2026) : la page docs a perdu ses blocs <Update> et ses dates ; elle
omettait déjà un tiers des entrées. Invariants : la source est le CHANGELOG GitHub, une
date déjà publiée ne change jamais, et un format méconnaissable rend ZÉRO version (la
publication s'arrête au lieu de publier un site vide).
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import update_changelog as uc  # noqa: E402

CHANGELOG = """# Changelog

## 2.1.308

- Bug fixes and reliability improvements

## 2.1.307

- Added `/claude-api api-version`
- [VSCode] Fixed dictation behind a TLS-inspecting proxy
"""

# Le format de la page docs depuis le 21 oct 2026 : versions et rubriques en gras.
PAGE_DOCS_REGROUPEE = """# Claude Code changelog

**2.1.307**

**Added**

* Added `/claude-api api-version`
"""


class LectureDuChangelog(unittest.TestCase):
    def test_versions_entrees_et_dates(self):
        dates = {"2.1.308": "October 22, 2026", "2.1.307": "October 21, 2026"}
        vs = uc.parse_changelog(CHANGELOG, dates)
        self.assertEqual([v["version"] for v in vs], ["2.1.308", "2.1.307"])
        self.assertEqual([v["itemCount"] for v in vs], [1, 2])
        self.assertEqual(vs[1]["isoDate"], "2026-10-21")
        self.assertEqual(vs[1]["yearQuarter"], "2026-Q4")
        self.assertEqual(vs[1]["items"][1]["scope"], "VSCode")

    def test_version_sans_date_reste_unknown(self):
        vs = uc.parse_changelog(CHANGELOG, {})
        self.assertEqual(vs[0]["date"], "Unknown")
        self.assertEqual(vs[0]["isoDate"], "Unknown")

    def test_page_docs_regroupee_rend_zero_version(self):
        self.assertEqual(uc.parse_changelog(PAGE_DOCS_REGROUPEE), [])

    def test_source_est_le_changelog_github(self):
        self.assertTrue(uc.CHANGELOG_URL.startswith(
            "https://raw.githubusercontent.com/anthropics/claude-code/"))


class Datation(unittest.TestCase):
    def test_date_en_texte_sans_zero(self):
        from datetime import date
        self.assertEqual(uc.date_en_texte(date(2026, 10, 2)), "October 2, 2026")

    def test_dates_publiees_reprises_unknown_ignoree(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "changelog.json")
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump({"versions": [{"version": "2.1.304", "date": "October 19, 2026"},
                                        {"version": "2.1.305", "date": "Unknown"}]}, f)
            self.assertEqual(uc.dates_connues(chemin), {"2.1.304": "October 19, 2026"})

    def test_dates_connues_sans_fichier(self):
        self.assertEqual(uc.dates_connues("/nonexistent/changelog.json"), {})

    def test_npm_injoignable_rend_vide(self):
        self.assertEqual(uc.fetch_dates_npm("http://127.0.0.1:9/inexistant"), {})


if __name__ == "__main__":
    unittest.main()
