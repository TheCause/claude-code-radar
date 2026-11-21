"""Tests du contrôle de mise en ligne (scripts/verifier_deploiement.py).

Défaut visé (21 nov 2026) : le push de 07 h était fait, mais le déploiement GitHub Pages a
échoué (« Fetching artifact metadata failed ») ; le journal local disait « publié » et la
tâche sortait en 0. Panne INVISIBLE côté machine pendant 5 h. Invariants :
- « publié » n'est dit que si le SITE EN LIGNE sert les données de ce matin ;
- un déploiement en échec est relancé UNE fois par une exécution NEUVE (workflow_dispatch :
  `gh run rerun` refuse, deux archives github-pages dans la même exécution) ;
- tout le reste sort en code non nul : la veille de 07 h 40 lit ce code et alerte.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import verifier_deploiement as vd  # noqa: E402

SHA = "3fea4d9a6fb0d7dc18474710e6cd05ec79a4ae0a"
MAJ = "2026-11-21T06:00:07Z"


def site(maj=MAJ):
    return json.dumps({"metadata": {"lastUpdatedUtc": maj, "latestVersion": "2.1.330"}})


class FauxGh:
    """Rejoue une suite d'états de `gh run list` ; enregistre les relances."""

    def __init__(self, etats, dispatch_rc=0):
        self.etats = list(etats)  # chaque état : liste d'exécutions, ou (rc, sortie) brut
        self.appels = []
        self.relances = 0
        self.dispatch_rc = dispatch_rc

    def __call__(self, args):
        self.appels.append(args)
        if args[:2] == ["workflow", "run"]:
            self.relances += 1
            return self.dispatch_rc, "" if self.dispatch_rc == 0 else "HTTP 403"
        etat = self.etats.pop(0) if len(self.etats) > 1 else self.etats[0]
        if isinstance(etat, tuple):
            return etat
        return 0, json.dumps(etat)


def run(i, status="completed", conclusion="success"):
    return {"databaseId": i, "status": status, "conclusion": conclusion if status == "completed" else ""}


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def verifier(gh, lectures, delai_max=900):
    h = Horloge()
    lectures = list(lectures)

    def lire(url):
        return lectures.pop(0) if len(lectures) > 1 else lectures[0]

    messages = []
    code, msg = vd.verifier(SHA, MAJ, gh=gh, lire_site=lire, dormir=h.dormir, horloge=h,
                            delai_max=delai_max, pas=20, journal=messages.append)
    return code, msg, messages, h.t


class TestVerifierDeploiement(unittest.TestCase):
    def test_succes_et_site_a_jour(self):
        code, msg, _, _ = verifier(FauxGh([[run(1)]]), [site()])
        self.assertEqual(code, 0, msg)

    def test_attend_que_l_execution_apparaisse_et_se_termine(self):
        gh = FauxGh([[], [run(1, "queued")], [run(1, "in_progress")], [run(1)]])
        code, msg, _, t = verifier(gh, [site()])
        self.assertEqual(code, 0, msg)
        self.assertGreaterEqual(t, 60)

    def test_attend_le_cache_du_site(self):
        code, msg, _, _ = verifier(FauxGh([[run(1)]]), [site("2026-11-20T06:00:05Z"), site()])
        self.assertEqual(code, 0, msg)

    def test_echec_puis_relance_reussie(self):
        # après la relance, la liste montre l'ancienne exécution en échec tant que la neuve
        # n'existe pas : elle ne doit être ni reprise pour un succès, ni relancée deux fois
        gh = FauxGh([[run(1, conclusion="failure")],
                     [run(1, conclusion="failure")],
                     [run(2, "queued"), run(1, conclusion="failure")],
                     [run(2), run(1, conclusion="failure")]])
        code, msg, messages, _ = verifier(gh, [site()])
        self.assertEqual(code, 0, msg)
        self.assertEqual(gh.relances, 1)
        self.assertIn(["workflow", "run", "publication.yml", "--ref", "main"], gh.appels)
        self.assertTrue(any("relance" in m for m in messages), messages)

    def test_deux_echecs_code_5_une_seule_relance(self):
        gh = FauxGh([[run(1, conclusion="failure")],
                     [run(2, conclusion="failure"), run(1, conclusion="failure")]])
        code, msg, _, _ = verifier(gh, [site()])
        self.assertEqual(code, vd.CODE_ECHEC)
        self.assertEqual(gh.relances, 1)
        self.assertIn("ÉCHEC", msg)

    def test_annulee_compte_comme_echec(self):
        gh = FauxGh([[run(1, conclusion="cancelled")], [run(2, conclusion="cancelled"), run(1)]])
        code, _, _, _ = verifier(gh, [site()])
        self.assertEqual(code, vd.CODE_ECHEC)

    def test_relance_refusee_code_5(self):
        gh = FauxGh([[run(1, conclusion="failure")]], dispatch_rc=1)
        code, msg, _, _ = verifier(gh, [site()])
        self.assertEqual(code, vd.CODE_ECHEC)
        self.assertIn("HTTP 403", msg)

    def test_aucune_execution_code_6(self):
        code, msg, _, t = verifier(FauxGh([[]]), [site()], delai_max=300)
        self.assertEqual(code, vd.CODE_NON_CONFIRME)
        self.assertLessEqual(t, 320)
        self.assertIn("aucune exécution", msg)

    def test_gh_en_panne_dit_la_cause(self):
        # ex. gh non authentifié sous launchd : la cause doit figurer dans le message
        code, msg, _, _ = verifier(FauxGh([(1, "To get started with GitHub CLI, please run: gh auth login")]),
                                   [site()], delai_max=120)
        self.assertEqual(code, vd.CODE_NON_CONFIRME)
        self.assertIn("gh auth login", msg)

    def test_deploiement_reussi_mais_site_figé_code_6(self):
        code, msg, _, _ = verifier(FauxGh([[run(1)]]), [site("2026-11-20T06:00:05Z")], delai_max=300)
        self.assertEqual(code, vd.CODE_NON_CONFIRME)
        self.assertIn("2026-11-20T06:00:05Z", msg)

    def test_site_illisible_code_6(self):
        def lire(url):
            raise OSError("HTTP 404")
        h = Horloge()
        code, msg = vd.verifier(SHA, MAJ, gh=FauxGh([[run(1)]]), lire_site=lire, dormir=h.dormir,
                                horloge=h, delai_max=120, pas=20, journal=lambda m: None)
        self.assertEqual(code, vd.CODE_NON_CONFIRME)
        self.assertIn("HTTP 404", msg)

    def test_interroge_les_executions_de_ce_commit(self):
        gh = FauxGh([[run(1)]])
        verifier(gh, [site()])
        liste = gh.appels[0]
        self.assertEqual(liste[:2], ["run", "list"])
        self.assertIn(SHA, liste)
        self.assertIn("publication.yml", liste)


if __name__ == "__main__":
    unittest.main()
