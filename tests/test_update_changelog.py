"""Tests de la lecture du changelog (scripts/update_changelog.py).

Défaut visé (21 oct 2026) : la page docs a perdu ses blocs <Update> et ses dates ; elle
omettait déjà un tiers des entrées. Invariants : la source est le CHANGELOG GitHub, une
date déjà publiée ne change jamais, et un format méconnaissable rend ZÉRO version (la
publication s'arrête au lieu de publier un site vide).
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

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


class ControlesDeFormat(unittest.TestCase):
    """Chaque contrôle a son test NÉGATIF : une source falsifiée qui doit le faire sonner."""
    REFERENCE = {"2.1.308": 1, "2.1.307": 2}

    def test_source_saine_ne_dit_rien(self):
        vs = uc.parse_changelog(CHANGELOG)
        self.assertEqual(uc.controles_format(CHANGELOG, vs, self.REFERENCE), [])

    def test_rubrique_inattendue_sonne(self):
        texte = CHANGELOG.replace("## 2.1.307\n", "## 2.1.307\n\n### Added\n")
        pannes = uc.controles_format(texte, uc.parse_changelog(texte), self.REFERENCE)
        self.assertEqual(len(pannes), 1)
        self.assertIn("### Added", pannes[0])

    def test_entree_perdue_sonne(self):
        texte = CHANGELOG.replace("- Added `/claude-api api-version`\n", "")
        pannes = uc.controles_format(texte, uc.parse_changelog(texte), self.REFERENCE)
        self.assertEqual(pannes, ["1 version(s) ont PERDU des entrées : ['2.1.307 (2 → 1)']"])

    def test_version_disparue_sonne(self):
        texte = CHANGELOG.split("## 2.1.307")[0]
        pannes = uc.controles_format(texte, uc.parse_changelog(texte), self.REFERENCE)
        self.assertEqual(pannes, ["1 version(s) publiée(s) DISPARUE(S) : ['2.1.307']"])

    def test_publication_stricte_refusee_rien_n_est_ecrit(self):
        texte = CHANGELOG.replace("- Added `/claude-api api-version`\n", "")
        with tempfile.TemporaryDirectory() as d:
            data, public = os.path.join(d, "data"), os.path.join(d, "public")
            os.makedirs(data)
            chemin = os.path.join(data, "changelog.json")
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump({"versions": [{"version": "2.1.307", "date": "October 21, 2026",
                                         "itemCount": 2}]}, f)
            with mock.patch.multiple(uc, DATA_DIR=data, PUBLIC_DATA_DIR=public,
                                     fetch_changelog=lambda allow_cache: texte,
                                     fetch_dates_npm=lambda: {}), \
                    mock.patch.object(sys, "argv", ["x", "--strict"]), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as fin:
                    uc.main()
            self.assertEqual(fin.exception.code, 1)
            with open(chemin, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["versions"][0]["itemCount"], 2)
            self.assertFalse(os.path.exists(os.path.join(data, "insights.json")))


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
