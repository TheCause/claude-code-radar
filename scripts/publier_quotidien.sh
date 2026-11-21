#!/usr/bin/env bash
# Publication quotidienne, exécutée EN LOCAL (planifiée par launchd, cron…) :
#   1. lit le changelog officiel (--strict : aucun repli sur une copie en cache) ;
#   2. analyse les nouvelles entrées avec le modèle local (--analyse-ia, voir analyse_ia.py) ;
#   3. commite les SEULS fichiers de données, puis pousse sur main ;
#   4. le push déclenche GitHub Actions, qui publie le site (.github/workflows/publication.yml) ;
#   5. attend la mise en ligne et la vérifie sur le site public (verifier_deploiement.py),
#      avec UNE relance si le déploiement échoue.
#
# Variables d'environnement (fournies par le planificateur, jamais écrites dans le dépôt) :
#   OLLAMA_URL      obligatoire pour l'analyse (ex. http://hote:11434)
#   GPU_ETAT_URL    facultatif : service /disponible?mib=N de la carte
#   PYTHON          facultatif : interpréteur (défaut python3)
#
# Code de sortie non nul = rien n'a été publié ; le journal dit pourquoi.
# Exceptions : 5 et 6 = données POUSSÉES, mais mise en ligne en échec (5) ou non confirmée (6).
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VERROU="$RACINE/.publication.lock"

journal() { echo "$(date '+%Y-%m-%d %H:%M:%S') [publication] $*"; }

if ! mkdir "$VERROU" 2>/dev/null; then
  journal "ÉCHEC : une publication tourne déjà ($VERROU)"
  exit 3
fi
trap 'rmdir "$VERROU"' EXIT

cd "$RACINE"

branche="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branche" != "main" ]; then
  journal "ÉCHEC : branche courante « $branche », la publication ne se fait que depuis main"
  exit 4
fi

journal "synchronisation avec origin/main"
git pull --ff-only --quiet origin main

journal "mise à jour + analyse locale"
"$PYTHON" scripts/update_changelog.py --strict --analyse-ia

git add data/changelog.json data/insights.json data/analyse_ia.json
if git diff --staged --quiet; then
  journal "données inchangées, rien à publier"
  exit 0
fi

version="$("$PYTHON" -c 'import json; print(json.load(open("data/insights.json"))["metadata"]["latestVersion"])')"
git commit --quiet -m "données : synchronisation du changelog (v$version), analyse locale"
git push --quiet origin main
sha="$(git rev-parse HEAD)"
journal "poussé : ${sha:0:7} (v$version) — attente de la mise en ligne par GitHub Actions"

# Le push ne prouve pas la mise en ligne (21 nov 2026 : déploiement Pages en échec, journal
# « publié », code 0, panne invisible 5 h). « publié » n'est écrit que si le site EN LIGNE
# sert ces données ; sinon code 5 ou 6, que la veille de 07 h 40 transforme en alerte.
"$PYTHON" scripts/verifier_deploiement.py "$sha" data/insights.json
journal "publié et EN LIGNE : ${sha:0:7} (v$version)"
