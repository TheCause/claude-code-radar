"""Tests de l'analyse locale des nouvelles entrées (scripts/analyse_ia.py).

Invariant : une entrée non analysée n'est JAMAIS présentée comme analysée. Réponse
incomplète, vocabulaire inventé, témoin mal classé, modèle ou carte indisponible :
chaque cas laisse les entrées « en attente », comptées et retentées.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import analyse_ia as ia  # noqa: E402

_VERSIONS = [
    {"version": "2.1.282", "items": [{"text": "Added a new `PreCompact` hook field"},
                                     {"text": "Fixed a typo in a Windows dialog"}]},
    {"version": "2.1.281", "items": [{"text": "Old entry"}]},
]


def VERSIONS_neuves():
    return json.loads(json.dumps(_VERSIONS))


def faux_modele(temoins_justes=True, domaine="hooks_config"):
    """Relit ce qu'on lui envoie ; classe les témoins bien ou mal selon le cas."""
    def appel(systeme, utilisateur, n):
        rep = []
        for ligne in utilisateur.splitlines():
            num, _, texte = ligne.partition(". ")
            if texte == ia.TEMOIN_MAJEUR:
                impact = "majeur" if temoins_justes else "mineur"
            elif texte == ia.TEMOIN_MINEUR:
                impact = "mineur"
            else:
                impact = "notable"
            rep.append({"n": int(num), "domaine": domaine, "impact": impact,
                        "resume": f"résumé de {texte[:20]}"})
        assert len(rep) == n
        return json.dumps({"analyse": rep})
    return appel


def sans_carte():
    return None


class TestAnalyseIA(unittest.TestCase):
    def cache_depart_281(self):
        return {"depart": ["2.1.281"], "entrees": {}}

    def test_premier_passage_met_tout_au_depart(self):
        versions = VERSIONS_neuves()
        cache = ia.charger_cache("/chemin/absent.json", versions)
        self.assertEqual(cache["depart"], ["2.1.282", "2.1.281"])
        self.assertEqual(ia.a_analyser(versions, cache), [])

    def test_seules_les_versions_nouvelles_sont_analysees(self):
        cache = self.cache_depart_281()
        versions = VERSIONS_neuves()
        faites, pannes = ia.analyser(versions, cache, appel=faux_modele(), verifier=sans_carte)
        self.assertEqual((faites, pannes), (2, []))
        meta = ia.enrichir(versions, cache, pannes)
        self.assertEqual(meta["enAttente"], 0)
        self.assertEqual(versions[0]["items"][0]["ia"]["impact"], "notable")
        self.assertNotIn("ia", versions[1]["items"][0])     # le départ reste intact

    def test_temoin_mal_classe_laisse_le_lot_en_attente(self):
        cache = self.cache_depart_281()
        versions = VERSIONS_neuves()
        faites, pannes = ia.analyser(versions, cache, appel=faux_modele(temoins_justes=False),
                                     verifier=sans_carte)
        self.assertEqual(faites, 0)
        self.assertIn("témoin", pannes[0])
        self.assertEqual(ia.enrichir(versions, cache, pannes)["enAttente"], 2)
        self.assertNotIn("ia", versions[0]["items"][0])

    def test_vocabulaire_invente_refuse(self):
        brut = json.dumps({"analyse": [{"n": 1, "domaine": "futuriste", "impact": "majeur",
                                        "resume": "x"}]})
        with self.assertRaises(ia.PanneAnalyse):
            ia.valider(brut, 1)

    def test_carte_occupee_rien_n_est_tente(self):
        def occupee():
            raise ia.PanneAnalyse("carte GPU occupée")

        def interdit(*a):
            raise AssertionError("le modèle ne doit pas être appelé")
        cache = self.cache_depart_281()
        faites, pannes = ia.analyser(VERSIONS_neuves(), cache, appel=interdit, verifier=occupee)
        self.assertEqual((faites, pannes), (0, ["carte GPU occupée"]))

    def test_carte_tenue_par_le_modele_voulu_est_utilisable(self):
        import io
        import urllib.error
        import urllib.request

        def repond_409(corps):
            def ouvrir(url, timeout=None):
                raise urllib.error.HTTPError(url, 409, "Conflict", {}, io.BytesIO(corps))
            return ouvrir
        vrai = urllib.request.urlopen
        try:
            os.environ["OLLAMA_MODELE"] = "modele-voulu:test"
            urllib.request.urlopen = repond_409(json.dumps(
                {"modeles_charges": ["modele-voulu:test"]}).encode())
            ia.verifier_carte("http://etat")                     # ne lève pas
            urllib.request.urlopen = repond_409(json.dumps(
                {"modeles_charges": ["autre-modele:70b"]}).encode())
            with self.assertRaises(ia.PanneAnalyse):
                ia.verifier_carte("http://etat")
        finally:
            urllib.request.urlopen = vrai

    def test_le_nom_du_modele_n_est_jamais_publie(self):
        os.environ["OLLAMA_MODELE"] = "modele-secret:1b"
        cache = {"depart": ["2.1.281"], "entrees": {}}
        versions = VERSIONS_neuves()
        ia.analyser(versions, cache, appel=faux_modele(), verifier=sans_carte)
        publie = json.dumps([ia.enrichir(versions, cache, []), cache, versions])
        self.assertNotIn("modele-secret", publie)

    def test_sans_ollama_modele_panne_explicite(self):
        ancien = os.environ.pop("OLLAMA_MODELE", None)
        try:
            with self.assertRaises(ia.PanneAnalyse):
                ia.modele_voulu()
        finally:
            if ancien is not None:
                os.environ["OLLAMA_MODELE"] = ancien

    def test_sans_ollama_url_panne_explicite(self):
        ancien = os.environ.pop("OLLAMA_URL", None)
        try:
            with self.assertRaises(ia.PanneAnalyse):
                ia.appel_ollama("s", "u", 1)
        finally:
            if ancien is not None:
                os.environ["OLLAMA_URL"] = ancien

    def test_un_ia_perime_est_retire(self):
        versions = VERSIONS_neuves()
        versions[0]["items"][0]["ia"] = {"domaine": "autre", "impact": "majeur", "resume": "faux"}
        meta = ia.enrichir(versions, self.cache_depart_281(), [])
        self.assertNotIn("ia", versions[0]["items"][0])
        self.assertEqual(meta["enAttente"], 2)

    def test_retente_au_passage_suivant(self):
        cache = self.cache_depart_281()
        versions = VERSIONS_neuves()
        ia.analyser(versions, cache, appel=faux_modele(temoins_justes=False), verifier=sans_carte)
        faites, pannes = ia.analyser(versions, cache, appel=faux_modele(), verifier=sans_carte)
        self.assertEqual((faites, pannes), (2, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
