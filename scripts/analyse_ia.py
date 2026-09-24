"""Analyse locale des NOUVELLES entrées du changelog par un modèle servi par Ollama.

Chaque entrée reçoit : un domaine, un niveau d'impact et un résumé d'une ligne en
français. Seules les versions apparues APRÈS la mise en service sont analysées : les
versions présentes au premier passage sont notées « départ » et gardent le classement
par mots-clés d'update_changelog.py.

Configuration par variables d'environnement (rien de propre à une machine dans le code) :
  OLLAMA_URL       ex. http://hote:11434  (obligatoire pour analyser)
  OLLAMA_MODELE    obligatoire pour analyser (nom du modèle Ollama)
  GPU_ETAT_URL     facultatif : service qui répond /disponible?mib=N (200 libre, 409 occupé)

Garde-fous :
- une réponse incomplète ou hors vocabulaire fait échouer le lot ;
- chaque lot porte deux TÉMOINS inventés, un majeur et un mineur connus d'avance ; un
  témoin mal classé rend le lot non fiable, et ses entrées restent « en attente » ;
- une entrée non analysée n'est jamais présentée comme analysée : elle est comptée
  « en attente » dans les métadonnées publiées, et retentée au passage suivant.
"""
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

DOMAINES = ("agents", "mcp", "securite", "interface", "modeles", "hooks_config",
            "performance", "autre")
IMPACTS = ("majeur", "notable", "mineur")
TAILLE_LOT = 25
MIB_NECESSAIRES = 21000

TEMOIN_MAJEUR = ("Added a new default model with a context window ten times larger, "
                 "available on every plan")
TEMOIN_MINEUR = "Fixed a typo in the footer of the `/help` screen"

CONSIGNE = """Tu analyses des entrées du changelog de Claude Code (l'outil de développement
en ligne de commande d'Anthropic), pour un lecteur francophone qui veut comprendre ce qui
change. Pour CHAQUE entrée numérotée, rends :
- "domaine" parmi : agents (sous-agents, workflows, tâches de fond), mcp (serveurs MCP,
  plugins, extensions), securite (permissions, sandbox, mode auto, identifiants),
  interface (terminal, IDE, web, Slack, affichage), modeles (modèles, raisonnement,
  coûts, cache), hooks_config (hooks, réglages, mémoire, CLAUDE.md), performance
  (vitesse, mémoire vive, démarrage), autre ;
- "impact" parmi : majeur (change la façon de travailler pour beaucoup d'utilisateurs),
  notable (nouvelle possibilité ou correction utile à un usage courant), mineur (détail,
  cas rare, affichage, plateforme ou offre particulière) ;
- "resume" : UNE phrase en français, 140 caractères au plus, qui dit ce qui change pour
  l'utilisateur, sans reprendre les noms de variables sauf s'ils sont indispensables.
Une correction de bug (« Fixed ») est le plus souvent "mineur". Rends exactement une
réponse par entrée, dans l'ordre, avec son numéro."""


class PanneAnalyse(RuntimeError):
    """Le lot n'a pas été analysé de façon exploitable."""


def modele_voulu():
    """Le nom du modèle n'est publié nulle part : ni dans ce code, ni dans les données."""
    modele = os.environ.get("OLLAMA_MODELE", "").strip()
    if not modele:
        raise PanneAnalyse("OLLAMA_MODELE non défini")
    return modele


def cle(texte):
    return hashlib.sha1(texte.encode("utf-8")).hexdigest()[:16]


def charger_cache(chemin, versions):
    """Au premier passage, toutes les versions présentes deviennent le « départ »."""
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"depart": [v["version"] for v in versions], "entrees": {}}


def a_analyser(versions, cache):
    """Les entrées des versions postérieures au départ, pas encore analysées."""
    depart = set(cache["depart"])
    faites = cache["entrees"]
    return [(v["version"], it["text"]) for v in versions if v["version"] not in depart
            for it in v["items"] if cle(it["text"]) not in faites]


def schema(n):
    return {"type": "object", "required": ["analyse"], "properties": {"analyse": {
        "type": "array", "minItems": n, "maxItems": n, "items": {
            "type": "object", "required": ["n", "domaine", "impact", "resume"],
            "properties": {"n": {"type": "integer"},
                           "domaine": {"type": "string", "enum": list(DOMAINES)},
                           "impact": {"type": "string", "enum": list(IMPACTS)},
                           "resume": {"type": "string"}}}}}}


def appel_ollama(systeme, utilisateur, n, url=None, modele=None):
    url = (url or os.environ.get("OLLAMA_URL", "")).rstrip("/")
    if not url:
        raise PanneAnalyse("OLLAMA_URL non défini")
    corps = json.dumps({
        "model": modele or modele_voulu(),
        "stream": False, "think": False, "format": schema(n),
        "options": {"temperature": 0, "num_ctx": 16384},
        "messages": [{"role": "system", "content": systeme},
                     {"role": "user", "content": utilisateur}]}).encode()
    req = urllib.request.Request(url + "/api/chat", data=corps,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["message"]["content"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise PanneAnalyse(f"modèle injoignable : {type(e).__name__}") from e


def verifier_carte(url=None):
    """Refuse de lancer si le service d'état dit la carte occupée. Sans service : on tente."""
    url = url or os.environ.get("GPU_ETAT_URL", "")
    if not url:
        return
    try:
        urllib.request.urlopen(f"{url.rstrip('/')}/disponible?mib={MIB_NECESSAIRES}", timeout=5)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            # Le « bloqueur » peut être le modèle voulu, déjà chargé (par la veille, par
            # un passage précédent) : alors il n'y a rien à charger, la carte sert telle
            # quelle. Sans ce cas, on refusait une carte parfaitement utilisable.
            try:
                charges = json.loads(e.read() or b"{}").get("modeles_charges") or []
            except ValueError:
                charges = []
            if modele_voulu() in charges:
                return
            raise PanneAnalyse("carte GPU occupée") from e
        raise PanneAnalyse(f"service d'état GPU : HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise PanneAnalyse(f"service d'état GPU injoignable : {type(e).__name__}") from e


def valider(brut, n):
    try:
        rep = json.loads(brut)["analyse"]
    except (ValueError, KeyError, TypeError) as e:
        raise PanneAnalyse(f"réponse illisible : {e}") from e
    if not isinstance(rep, list) or len(rep) != n:
        raise PanneAnalyse("nombre de réponses faux")
    if sorted(r.get("n") for r in rep) != list(range(1, n + 1)):
        raise PanneAnalyse("numérotation incomplète")
    for r in rep:
        if r.get("domaine") not in DOMAINES or r.get("impact") not in IMPACTS:
            raise PanneAnalyse("valeur hors vocabulaire")
        if not str(r.get("resume", "")).strip():
            raise PanneAnalyse("résumé vide")
    return sorted(rep, key=lambda r: r["n"])


def analyser_lot(lot, appel):
    """lot = [(version, texte)]. Rend {cle: analyse} ; lève PanneAnalyse si non fiable."""
    textes = [t for _, t in lot]
    p_maj, p_min = len(textes) // 3, (2 * len(textes)) // 3
    avec = textes[:p_maj] + [TEMOIN_MAJEUR] + textes[p_maj:]
    avec = avec[:p_min + 1] + [TEMOIN_MINEUR] + avec[p_min + 1:]
    i_maj, i_min = avec.index(TEMOIN_MAJEUR), avec.index(TEMOIN_MINEUR)
    liste = "\n".join(f"{i}. {t}" for i, t in enumerate(avec, start=1))
    rep = valider(appel(CONSIGNE, liste, len(avec)), len(avec))
    if rep[i_maj]["impact"] != "majeur" or rep[i_min]["impact"] != "mineur":
        raise PanneAnalyse("témoin mal classé : lot non fiable")
    rep = [r for i, r in enumerate(rep) if i not in (i_maj, i_min)]
    le = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {cle(t): {"version": v, "domaine": r["domaine"], "impact": r["impact"],
                     "resume": r["resume"].strip()[:200], "le": le}
            for (v, t), r in zip(lot, rep)}


def analyser(versions, cache, appel=None, verifier=None, taille_lot=TAILLE_LOT):
    """Analyse ce qui est en attente. Rend (nb_analysees, [pannes]) ; complète le cache."""
    appel = appel or appel_ollama
    en_attente = a_analyser(versions, cache)
    if not en_attente:
        return 0, []
    try:
        (verifier or verifier_carte)()
    except PanneAnalyse as e:
        return 0, [str(e)]
    faites, pannes = 0, []
    for debut in range(0, len(en_attente), taille_lot):
        lot = en_attente[debut:debut + taille_lot]
        try:
            resultat = analyser_lot(lot, appel)
        except PanneAnalyse as e:
            pannes.append(str(e))
            continue
        cache["entrees"].update(resultat)
        faites += len(resultat)
    return faites, pannes


def enrichir(versions, cache, pannes):
    """Pose `ia` sur chaque entrée analysée ; rend les métadonnées publiées."""
    depart = set(cache["depart"])
    attente = 0
    for v in versions:
        for it in v["items"]:
            a = cache["entrees"].get(cle(it["text"]))
            if a:
                it["ia"] = {k: a[k] for k in ("domaine", "impact", "resume")}
            else:
                it.pop("ia", None)          # jamais un « ia » qui ne vient pas du cache
                if v["version"] not in depart:
                    attente += 1
    nouvelles = [v["version"] for v in versions if v["version"] not in depart]
    return {
        "versionsAnalysees": nouvelles,
        "entreesAnalysees": len(cache["entrees"]),
        "enAttente": attente,
        "pannes": pannes,
    }
