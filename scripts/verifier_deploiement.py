#!/usr/bin/env python3
"""Contrôle de mise en ligne, appelé par publier_quotidien.sh après le push.

Le push ne publie rien : il déclenche GitHub Actions (.github/workflows/publication.yml).
Ce contrôle attend l'exécution déclenchée par CE commit, puis vérifie que le site EN LIGNE
sert les données produites ce matin (même `lastUpdatedUtc` que data/insights.json local).

Si le déploiement échoue, il est relancé UNE fois par une exécution neuve
(`gh workflow run`, déclencheur workflow_dispatch). `gh run rerun` ne convient pas : la
relance voit deux archives `github-pages` dans la même exécution et refuse (21 nov 2026).

Codes de sortie (lus par la veille de 07 h 40, qui alerte sur tout code non nul) :
  0  le site en ligne sert les données de ce matin
  5  déploiement en ÉCHEC (après la relance, ou relance refusée)
  6  mise en ligne NON CONFIRMÉE dans le délai (aucune exécution, gh en panne, site figé)

Usage : verifier_deploiement.py <sha> <chemin de data/insights.json>
Variables : DEPLOIEMENT_DELAI_MAX (s, défaut 900), SITE_INSIGHTS_URL, GH (défaut gh).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

WORKFLOW = "publication.yml"
SITE_INSIGHTS_URL = "https://thecause.github.io/claude-code-radar/data/insights.json"
CODE_ECHEC = 5
CODE_NON_CONFIRME = 6


def gh_reel(binaire="gh"):
    def lancer(args):
        try:
            r = subprocess.run([binaire, *args], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, f"{type(e).__name__}: {e}"
        return r.returncode, (r.stdout if r.returncode == 0 else (r.stderr or r.stdout)).strip()
    return lancer


def lire_url(url):
    # paramètre neuf à chaque lecture : le cache de GitHub Pages garde une copie 10 min
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}controle={int(time.time())}",
                                 headers={"User-Agent": "claude-code-radar-publication"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def verifier(sha, maj_locale, *, gh, lire_site, dormir, horloge, journal,
             delai_max=900, pas=20, site_url=SITE_INSIGHTS_URL):
    """Rend (code, message). N'échoue jamais en silence : le message dit la dernière cause."""
    fin = horloge() + delai_max
    en_echec = set()   # exécutions déjà vues en échec : jamais reprises, jamais relancées deux fois
    relance = False
    etat = "aucune exécution trouvée pour ce commit"

    # 1. l'exécution GitHub Actions de ce commit
    while True:
        rc, sortie = gh(["run", "list", "--workflow", WORKFLOW, "--commit", sha,
                         "--json", "databaseId,status,conclusion", "--limit", "10"])
        if rc != 0:
            etat = f"gh en panne : {sortie[:300]}"
        else:
            try:
                runs = [r for r in json.loads(sortie) if r["databaseId"] not in en_echec]
            except (ValueError, KeyError, TypeError) as e:
                runs, etat = [], f"réponse de gh illisible ({type(e).__name__})"
            if runs:
                r = runs[0]  # gh liste la plus récente d'abord
                if r["status"] != "completed":
                    etat = f"exécution {r['databaseId']} : {r['status']}"
                elif r["conclusion"] == "success":
                    journal(f"déploiement réussi (exécution {r['databaseId']})")
                    break
                elif relance:
                    return CODE_ECHEC, (f"déploiement en ÉCHEC après relance (exécution "
                                        f"{r['databaseId']} : {r['conclusion']})")
                else:
                    en_echec.add(r["databaseId"])
                    journal(f"déploiement en échec (exécution {r['databaseId']} : "
                            f"{r['conclusion']}) — relance par une exécution neuve")
                    rc, sortie = gh(["workflow", "run", WORKFLOW, "--ref", "main"])
                    if rc != 0:
                        return CODE_ECHEC, f"déploiement en ÉCHEC, relance refusée : {sortie[:300]}"
                    relance = True
                    etat = "relance demandée, exécution neuve pas encore visible"
        if horloge() >= fin:
            return CODE_NON_CONFIRME, f"mise en ligne NON CONFIRMÉE en {delai_max} s : {etat}"
        dormir(pas)

    # 2. le site en ligne, là où l'on regarde
    while True:
        try:
            servi = json.loads(lire_site(site_url))["metadata"]["lastUpdatedUtc"]
            if servi == maj_locale:
                return 0, f"site en ligne à jour ({servi})"
            etat = f"le site sert {servi}, attendu {maj_locale}"
        except Exception as e:  # noqa: BLE001 — toute panne de lecture est une cause à dire
            etat = f"site illisible ({type(e).__name__}: {e})"
        if horloge() >= fin:
            return CODE_NON_CONFIRME, f"mise en ligne NON CONFIRMÉE en {delai_max} s : {etat}"
        dormir(pas)


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    sha, chemin = argv[1], argv[2]
    with open(chemin, encoding="utf-8") as f:
        maj = json.load(f)["metadata"]["lastUpdatedUtc"]

    def journal(m):
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [publication] {m}", flush=True)

    code, msg = verifier(sha, maj, gh=gh_reel(os.environ.get("GH", "gh")), lire_site=lire_url,
                         dormir=time.sleep, horloge=time.monotonic, journal=journal,
                         delai_max=int(os.environ.get("DEPLOIEMENT_DELAI_MAX", "900")),
                         site_url=os.environ.get("SITE_INSIGHTS_URL", SITE_INSIGHTS_URL))
    journal(("" if code == 0 else "ÉCHEC : ") + msg)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
