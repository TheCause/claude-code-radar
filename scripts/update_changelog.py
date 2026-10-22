#!/usr/bin/env python3
"""
Claude Code Changelog Ingestion & Intelligence Analyzer
Fetches the official changelog (CHANGELOG.md on GitHub), parses all 400+ versions,
categorizes items, evaluates strategic impact, and exports structured JSON for visualization.

Source : jusqu'au 20 oct 2026, la page code.claude.com/docs/en/changelog.md (blocs
<Update label=… description="October 19, 2026">). Le 21 oct, elle a perdu ses blocs et
ses dates. Elle omettait déjà des entrées : 5 475 lues contre 8 003 dans le CHANGELOG
GitHub pour les mêmes versions (mesuré le 22 oct 2026). On lit désormais le fichier GitHub.
Il ne porte aucune date : celles déjà publiées sont reprises de data/changelog.json, et
une version nouvelle prend sa date de publication sur npm (jour UTC).
"""

import sys
import os
import re
import json
import urllib.request
from datetime import datetime, timezone
from collections import Counter, defaultdict

CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
NPM_URL = "https://registry.npmjs.org/@anthropic-ai/claude-code"
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
PUBLIC_DATA_DIR = os.path.join(WORKSPACE_DIR, "public", "data")

HIGH_IMPACT_KEYWORDS = [
    "opus 5.5", "opus", "sonnet 3.7", "1m context", "claude apps gateway",
    "subagent", "workflows", "claude agents", "auto mode", "guardrail",
    "assume_role", "elicitation", "remote control", "claude tag",
    "prompt cache", "fast mode", "background session", "ultrareview",
    "batch", "mcp url-mode", "sandbox", "headless"
]

SOURCE_LIVE = True  # passe à False si la copie en cache a servi : dit dans les métadonnées


def fetch_changelog(url=CHANGELOG_URL, allow_cache=True):
    print(f"[*] Fetching changelog from {url}...")
    headers = {
        "User-Agent": "Claude-Code-Changelog-Tracker/1.0 (Automated Daily Observatory)"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            print(f"[+] Downloaded {len(content):,} bytes successfully.")
            return content
    except Exception as e:
        print(f"[-] Error fetching online changelog: {e}")
        # En publication (--strict), AUCUN repli : un site qui se dit « à jour » avec une
        # copie périmée est pire qu'une tâche en échec, qui, elle, se voit.
        if not allow_cache:
            raise
        # Try fallback to cached raw file if available
        cache_path = os.path.join(DATA_DIR, "raw_changelog.md")
        if os.path.exists(cache_path):
            print(f"[!] Using cached changelog from {cache_path}...")
            global SOURCE_LIVE
            SOURCE_LIVE = False
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        raise

def date_en_texte(jour):
    """2026-10-02 → « October 2, 2026 », le format des dates déjà publiées."""
    return f"{jour:%B} {jour.day}, {jour.year}"


def dates_connues(chemin=None):
    """Les dates déjà publiées (version → « October 19, 2026 »). Une date illisible
    (« Unknown ») n'est pas reprise : elle sera recherchée à nouveau sur npm."""
    chemin = chemin or os.path.join(DATA_DIR, "changelog.json")
    try:
        with open(chemin, encoding="utf-8") as f:
            anciennes = json.load(f)["versions"]
    except (OSError, ValueError, KeyError):
        return {}
    dates = {}
    for v in anciennes:
        try:
            datetime.strptime(v["date"], "%B %d, %Y")
        except (KeyError, TypeError, ValueError):
            continue
        dates[v["version"]] = v["date"]
    return dates


def entrees_publiees(chemin=None):
    """Le nombre d'entrées de chaque version déjà publiée (version → itemCount)."""
    chemin = chemin or os.path.join(DATA_DIR, "changelog.json")
    try:
        with open(chemin, encoding="utf-8") as f:
            return {v["version"]: v["itemCount"] for v in json.load(f)["versions"]}
    except (OSError, ValueError, KeyError):
        return {}


def controles_format(markdown_text, versions, reference):
    """« Zéro version » ne voit que la rupture TOTALE. La perte du 21 oct 2026 était
    partielle (un tiers des entrées omises par la page docs, tout restait vert). D'où :
    aucune ligne inconnue, et aucune version publiée qui disparaît ou perd des entrées."""
    pannes = []
    inconnues = [l for l in markdown_text.split("\n")
                 if l.strip() and l.strip() != "# Changelog"
                 and not re.match(r"^## \d+\.\d+\.\d+\S*\s*$", l) and not l.startswith("- ")]
    if inconnues:
        pannes.append(f"{len(inconnues)} ligne(s) non reconnue(s), ex. {inconnues[:3]}")
    actuel = {v["version"]: v["itemCount"] for v in versions}
    disparues = [v for v in reference if v not in actuel]
    if disparues:
        pannes.append(f"{len(disparues)} version(s) publiée(s) DISPARUE(S) : {disparues[:5]}")
    amputees = [f"{v} ({n} → {actuel[v]})" for v, n in reference.items()
                if v in actuel and actuel[v] < n]
    if amputees:
        pannes.append(f"{len(amputees)} version(s) ont PERDU des entrées : {amputees[:5]}")
    return pannes


def fetch_dates_npm(url=NPM_URL):
    """Date de publication de chaque version sur npm (jour UTC). Une panne rend {} :
    les versions concernées restent « Unknown » et seront redatées au passage suivant."""
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "Claude-Code-Changelog-Tracker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            temps = json.load(resp)["time"]
    except Exception as e:
        print(f"[-] Dates npm indisponibles ({e}) : nouvelles versions datées « Unknown ».")
        return {}
    dates = {}
    for version, horodatage in temps.items():
        try:
            jour = datetime.strptime(horodatage[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        dates[version] = date_en_texte(jour)
    return dates


def parse_changelog(markdown_text, dates=None):
    """Titres `## x.y.z` suivis de lignes `- entrée` (CHANGELOG.md de GitHub, à plat ;
    vérifié le 22 oct 2026 : 428 versions, aucune ligne d'un autre type). `dates` :
    version → « October 19, 2026 »."""
    print("[*] Parsing changelog sections...")
    dates = dates or {}
    matches = []
    for ligne in markdown_text.split("\n"):
        m = re.match(r"^## (\d+\.\d+\.\d+\S*)\s*$", ligne)
        if m:
            matches.append((m.group(1), dates.get(m.group(1), ""), []))
        elif matches and ligne.startswith("- "):
            matches[-1][2].append(ligne[2:].strip())
    print(f"[+] Found {len(matches)} version releases.")

    parsed_versions = []

    for label, desc_date, lignes in matches:
        version = label.strip()
        date_str = desc_date.strip() or "Unknown"
        
        # Parse ISO date
        iso_date = None
        try:
            dt = datetime.strptime(date_str, "%B %d, %Y")
            iso_date = dt.strftime("%Y-%m-%d")
            year_month = dt.strftime("%Y-%m")
            year_quarter = f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
        except Exception:
            iso_date = "Unknown"
            year_month = "Unknown"
            year_quarter = "Unknown"
        
        # Parse bullet points
        items = []
        for text in lignes:
            item = analyze_change_item(text, version, iso_date)
            items.append(item)
            
        parsed_versions.append({
            "version": version,
            "date": date_str,
            "isoDate": iso_date,
            "yearMonth": year_month,
            "yearQuarter": year_quarter,
            "itemCount": len(items),
            "items": items
        })
        
    return parsed_versions

def analyze_change_item(text, version, iso_date):
    # Detect Scope prefix like [VSCode], [Claude Tag], [Claude Code on the web], [Code Review]
    scope = "Core CLI"
    clean_text = text
    scope_match = re.match(r"^\\?\[([^\]]+)\]\s*(.*)", text)
    if scope_match:
        scope = scope_match.group(1).strip()
        clean_text = scope_match.group(2).strip()
        
    # Detect Action Type (Added, Fixed, Improved, Changed, Removed)
    action_type = "Other"
    first_word = clean_text.split(" ")[0] if clean_text else ""
    if first_word.lower() in ["added", "ajoute", "ajout"]:
        action_type = "Added"
    elif first_word.lower() in ["fixed", "fix", "corrige"]:
        action_type = "Fixed"
    elif first_word.lower() in ["improved", "enhance", "ameliore"]:
        action_type = "Improved"
    elif first_word.lower() in ["changed", "update", "modifie"]:
        action_type = "Changed"
    elif first_word.lower() in ["removed", "deprecated", "supprime"]:
        action_type = "Removed"
    else:
        # Check starting with Windows: Fixed...
        if "fixed" in clean_text[:20].lower():
            action_type = "Fixed"
        elif "added" in clean_text[:20].lower():
            action_type = "Added"
        elif "improved" in clean_text[:20].lower():
            action_type = "Improved"
        elif "changed" in clean_text[:20].lower():
            action_type = "Changed"

    # Multi-tag analysis
    tags = []
    low = clean_text.lower()
    
    if any(k in low for k in ["mcp", "model context protocol", "mcp_tool", "mcp.json"]):
        tags.append("MCP & Tools")
    if any(k in low for k in ["agent", "subagent", "workflow", "batch", "teammate", "ultrareview", "background agent", "--bg"]):
        tags.append("Multi-Agent & Workflows")
    if any(k in low for k in ["opus", "sonnet", "haiku", "thinking", "advisor", "prompt cache", "token", "model"]):
        tags.append("Models & Intelligence")
    if any(k in low for k in ["sandbox", "permission", "auto mode", "iam", "bedrock", "guardrail", "assume_role", "trust", "keychain", "rm -rf", "safe mode"]):
        tags.append("Security & Governance")
    if any(k in low for k in ["vscode", "vs code", "jetbrains", "slack", "claude tag", "remote control", "claude.ai", "web"]):
        tags.append("IDE & Cloud Ubiquity")
    if any(k in low for k in ["plugin", "skill", "marketplace", "hook"]):
        tags.append("Plugins & Skills")
    if any(k in low for k in ["perf", "memory", "heap", "crash", "retry", "watchdog", "stream", "latency", "startup", "resume"]):
        tags.append("Performance & Reliability")
    if any(k in low for k in ["vim", "terminal", "diff", "dialog", "fullscreen", "keybinding", "mouse", "prompt", "ui"]):
        tags.append("Terminal & UX")

    if not tags:
        tags.append("General Core")

    # Impact Level Evaluation
    impact = "Standard"
    is_high_impact = any(k in low for k in HIGH_IMPACT_KEYWORDS)
    if is_high_impact or (action_type == "Added" and any(t in tags for t in ["Multi-Agent & Workflows", "Models & Intelligence", "MCP & Tools", "Security & Governance"])):
        impact = "High"
    elif action_type in ["Added", "Improved"] or scope in ["VSCode", "Claude Tag", "Claude Code on the web"]:
        impact = "Medium"

    return {
        "text": text,
        "cleanText": clean_text,
        "scope": scope,
        "actionType": action_type,
        "tags": tags,
        "impact": impact,
        "version": version,
        "date": iso_date
    }

def compute_insights(versions):
    print("[*] Computing strategic insights & trend analytics...")
    
    total_versions = len(versions)
    all_items = [item for v in versions for item in v["items"]]
    total_items = len(all_items)
    
    # Counts by Action Type
    action_counts = Counter(item["actionType"] for item in all_items)
    
    # Counts by Tag
    tag_counts = Counter()
    for item in all_items:
        for t in item["tags"]:
            tag_counts[t] += 1
            
    # Counts by Scope
    scope_counts = Counter(item["scope"] for item in all_items)
    
    # Timeline releases & items per month
    month_stats = defaultdict(lambda: {"releases": 0, "items": 0, "added": 0, "fixed": 0, "improved": 0})
    for v in versions:
        m = v["yearMonth"]
        if m == "Unknown": continue
        month_stats[m]["releases"] += 1
        month_stats[m]["items"] += v["itemCount"]
        for item in v["items"]:
            act = item["actionType"].lower()
            if act in month_stats[m]:
                month_stats[m][act] += 1
                
    sorted_months = sorted(month_stats.keys())
    timeline_data = [
        {
            "month": m,
            "releases": month_stats[m]["releases"],
            "items": month_stats[m]["items"],
            "added": month_stats[m]["added"],
            "fixed": month_stats[m]["fixed"],
            "improved": month_stats[m]["improved"]
        }
        for m in sorted_months
    ]
    
    # High-impact innovations list (chronological or reverse)
    high_impact_items = [
        item for item in all_items if item["impact"] == "High"
    ]
    
    # Curated Game-Changers (Sourcés directement depuis data/raw_changelog.md)
    game_changers = [
        {
            "title": "Claude Opus 5.5 par défaut (1M Contexte, Cache Reads $0.20/Mtok)",
            "version": "2.1.280",
            "date": "2026-09-22",
            "category": "Models & Intelligence",
            "sourceLine": 193,
            "potential": "Modèle Opus par défaut avec 1M de tokens de contexte, tarif de 4 $/Mtok en entrée et 0,20 $/Mtok en lecture de cache (soit une division par 20 du coût de lecture par rapport à l'entrée standard).",
            "quote": "Added Claude Opus 5.5 (`claude-opus-5-5`), now the default Opus model — 1M context, $4/$20 per Mtok with $0.20/Mtok cache reads."
        },
        {
            "title": "Claude Apps Gateway (Bedrock STS Assume-Role & Guardrails)",
            "version": "2.1.281",
            "date": "2026-09-23",
            "category": "Security & Governance",
            "sourceLine": 23,
            "potential": "Prise de rôle IAM via STS (`assume_role`) et application systématique de guardrails Amazon Bedrock sur les upstreams de la passerelle.",
            "quote": "Added assume_role on Claude apps gateway Bedrock upstreams... Added guardrail: {id, version} on Claude apps gateway Bedrock upstreams."
        },
        {
            "title": "MCP URL-Mode Elicitation",
            "version": "2.1.281",
            "date": "2026-09-23",
            "category": "MCP & Tools",
            "sourceLine": 27,
            "potential": "Protocole de connexion permettant aux serveurs MCP d'ouvrir des flux interactifs via navigateur web.",
            "quote": "Added MCP URL-mode elicitation on 2026-07-28 protocol connections, so servers can ask Claude Code to open a browser-based flow."
        },
        {
            "title": "Système Multi-Agents & Workflows (/workflows, /batch, Worktree)",
            "version": "2.1.278",
            "date": "2026-09-19",
            "category": "Multi-Agent & Workflows",
            "sourceLine": 134,
            "potential": "Exécution de commandes batch et sous-agents en arrière-plan avec isolation dans des git worktrees fournis par hooks.",
            "quote": "Improved /batch to run where a WorktreeCreate hook provides the agent worktrees, not only inside a git repository."
        },
        {
            "title": "Auto Mode avec Examen par Classifieur Côté Serveur",
            "version": "2.1.281",
            "date": "2026-09-23",
            "category": "Security & Governance",
            "sourceLine": 148,
            "potential": "Les commandes shell en lecture seule et sandboxées attendent l'examen d'un classifieur côté serveur et sont bloquées s'il les signale.",
            "quote": "Changed auto mode so that, where its classifier review runs server-side, read-only and sandboxed shell commands also wait for that review and are blocked when it flags them."
        },
        {
            "title": "Claude Tag dans Slack Threads",
            "version": "2.1.280",
            "date": "2026-09-22",
            "category": "IDE & Cloud Ubiquity",
            "sourceLine": 178,
            "potential": "Intégration de Claude dans les fils de discussion Slack avec routines dédiées au canal et reprise de contexte.",
            "quote": "[Claude Tag] Added a short line in the Slack thread after someone presses Stop... Changed the routine list Claude gives when asked in a Slack thread."
        },
        {
            "title": "Claude Code sur le Web (claude.ai/code)",
            "version": "2.1.281",
            "date": "2026-09-23",
            "category": "IDE & Cloud Ubiquity",
            "sourceLine": 172,
            "potential": "Sessions de développement distantes dans le cloud avec sélecteur de mode rapide (Fast mode) et intégration GitHub.",
            "quote": "[Claude Code on the web] Added a Fast mode switch to the composer's model menu in cloud sessions... Added a settings shortcut on the GitHub setup tip."
        }
    ]

    # Strategic Pillars Analysis (Sourcés strictement depuis data/raw_changelog.md)
    multi_agent_keywords = ["agent", "subagent", "workflow", "batch", "teammate", "ultrareview", "background agent", "--bg"]
    mcp_keywords = ["mcp", "model context protocol", "mcp_tool", "mcp.json"]
    security_keywords = ["sandbox", "permission", "auto mode", "iam", "bedrock", "guardrail", "assume_role", "trust", "keychain", "rm -rf", "safe mode"]
    ubiquity_keywords = ["vscode", "vs code", "jetbrains", "slack", "claude tag", "remote control", "claude.ai", "web"]
    models_keywords = ["opus", "sonnet", "haiku", "thinking", "advisor", "prompt cache", "token", "model"]

    strategic_pillars = [
        {
            "id": "pillar_agents",
            "title": "1. Multi-Agents & Workflows Asynchrones",
            "icon": "🤖",
            "badge": "Autonomie",
            "metric": f"{tag_counts['Multi-Agent & Workflows']} entrées contenant ces mots-clés",
            "keywords": multi_agent_keywords,
            "summary": "Évolution vers l'exécution asynchrone et la coordination de sous-agents.",
            "details": [
                "Sous-agents (`subagents`, `claude agents`) et sessions en arrière-plan (`claude --bg`).",
                "Gestion des workflows (`/workflows`, `/batch`) avec hooks d'arborescence (`WorktreeCreate`, ligne 134).",
                "Revue de code approfondie (`/ultrareview`) et gestion des tâches en cours (`/tasks`)."
            ]
        },
        {
            "id": "pillar_mcp",
            "title": "2. Écosystème MCP & Extensibilité",
            "icon": "🔌",
            "badge": "Intégration",
            "metric": f"{tag_counts['MCP & Tools']} entrées contenant ces mots-clés",
            "keywords": mcp_keywords,
            "summary": "Support et enrichissement du Model Context Protocol (MCP) pour la connexion d'outils externes.",
            "details": [
                "Mode URL-Mode Elicitation (ligne 27) pour les flux d'authentification et formulaires via navigateur.",
                "Plafonnement des descriptions de serveurs (`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH`, ligne 195).",
                "Validation de configuration via `claude plugin validate` (lignes 28 et 80)."
            ]
        },
        {
            "id": "pillar_security",
            "title": "3. Sécurité, Passerelle & Sandboxing",
            "icon": "🛡️",
            "badge": "Gouvernance",
            "metric": f"{tag_counts['Security & Governance']} entrées contenant ces mots-clés",
            "keywords": security_keywords,
            "summary": "Contrôle d'accès, passerelle entreprise et sandboxing des commandes shell.",
            "details": [
                "Claude Apps Gateway : prise de rôle IAM AWS Bedrock (`assume_role`) et guardrails (lignes 23-24).",
                "Auto Mode avec examen des commandes shell par classifieur serveur (ligne 148).",
                "Sandboxing des commandes Bash : isolation système et réseau (`sandbox.bwrapPath` sous Linux à la ligne 1989, AppContainer/restricted-token sous Windows à la ligne 1086, et limite mémoire cgroup Linux optionnelle via `CLAUDE_CODE_TOOL_MEMORY_LIMIT` à la ligne 1935)."
            ]
        },
        {
            "id": "pillar_ubiquity",
            "title": "4. Interfaces Multiples (CLI, IDE, Web, Slack)",
            "icon": "🌐",
            "badge": "Omnicanal",
            "metric": f"{scope_counts['VSCode'] + scope_counts['Claude Code on the web'] + scope_counts['Claude Tag']} entrées scopées",
            "keywords": ubiquity_keywords,
            "summary": "Extension du client au-delà du terminal local vers l'éditeur, le cloud et la messagerie.",
            "details": [
                "Terminal interactif : navigation au clavier, support du mode Vim et affichage plein écran.",
                "Extensions pour environnements de développement (panneaux VS Code et JetBrains).",
                "Sessions Web distantes (`claude.ai/code`, ligne 172) et assistance Slack via `Claude Tag` (ligne 178)."
            ]
        },
        {
            "id": "pillar_intelligence",
            "title": "5. Modèles & Lecture de Cache",
            "icon": "⚡",
            "badge": "Modèles",
            "metric": f"{tag_counts['Models & Intelligence']} entrées contenant ces mots-clés",
            "keywords": models_keywords,
            "summary": "Intégration des modèles Claude et optimisation des temps et coûts de traitement.",
            "details": [
                "Claude Opus 5.5 (`claude-opus-5-5`) par défaut avec 1M de tokens de contexte (ligne 193).",
                "Tarif de 4 $ / 20 $ par Mtok avec lecture de cache à 0,20 $/Mtok (division par 20 du coût de lecture par rapport à l'entrée standard, ligne 193).",
                "Modes de pensée adaptatifs (Thinking mode) et reprise automatique de sessions interrompues."
            ]
        }
    ]

    return {
        "metadata": {
            "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "latestVersion": versions[0]["version"] if versions else "Unknown",
            "latestDate": versions[0]["date"] if versions else "Unknown",
            "totalVersions": total_versions,
            "totalItems": total_items,
            "highImpactCount": len(high_impact_items)
        },
        "actionCounts": dict(action_counts),
        "tagCounts": dict(tag_counts),
        "scopeCounts": dict(scope_counts),
        "timeline": timeline_data,
        "gameChangers": game_changers,
        "strategicPillars": strategic_pillars
    }

def main():
    strict = "--strict" in sys.argv
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    
    # 1. Fetch
    raw_markdown = fetch_changelog(allow_cache=not strict)
    
    # Save raw markdown backup
    with open(os.path.join(DATA_DIR, "raw_changelog.md"), "w", encoding="utf-8") as f:
        f.write(raw_markdown)
        
    # 2. Parse — dates déjà publiées d'abord, npm seulement pour les versions nouvelles
    dates = dates_connues()
    dates = {**fetch_dates_npm(), **dates}
    versions = parse_changelog(raw_markdown, dates)
    if not versions:
        # Page lue mais méconnaissable (refonte du format) : ne JAMAIS publier un site vide.
        print("[-] Aucune version reconnue dans la source : format changé ? Rien n'est écrit.")
        sys.exit(1)

    # 2 bis. Rupture PARTIELLE du format : en publication, on n'écrase pas un site sain
    # avec des données amputées. Après vérification humaine (suppression voulue en amont) :
    #   scripts/update_changelog.py --strict --analyse-ia --acquitter-format
    if "--acquitter-format" not in sys.argv:
        pannes_format = controles_format(raw_markdown, versions, entrees_publiees())
        for panne in pannes_format:
            print(f"[-] Format : {panne}")
        if pannes_format and strict:
            print("[-] Publication refusée : rien n'est écrit (--acquitter-format après vérification).")
            sys.exit(1)

    # 3. Analyze & Insights
    insights = compute_insights(versions)
    insights["metadata"]["lastUpdatedUtc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    insights["metadata"]["sourceLive"] = SOURCE_LIVE

    # 3 bis. Analyse locale des NOUVELLES versions par un modèle Ollama (voir analyse_ia.py).
    # Une panne n'arrête pas la publication : les entrées restent « en attente », comptées
    # dans les métadonnées publiées, et sont retentées au passage suivant.
    if "--analyse-ia" in sys.argv:
        import analyse_ia
        chemin_cache = os.path.join(DATA_DIR, "analyse_ia.json")
        cache = analyse_ia.charger_cache(chemin_cache, versions)
        faites, pannes_ia = analyse_ia.analyser(versions, cache)
        insights["metadata"]["analyseIA"] = analyse_ia.enrichir(versions, cache, pannes_ia)
        with open(chemin_cache, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=1, ensure_ascii=False)
        print(f"[*] Analyse IA : {faites} entrée(s) analysée(s), "
              f"{insights['metadata']['analyseIA']['enAttente']} en attente"
              + (f" — pannes : {'; '.join(pannes_ia)}" if pannes_ia else ""))
    
    # 4. Save JSON files
    changelog_payload = {
        "metadata": insights["metadata"],
        "versions": versions
    }
    
    print("[*] Writing data files...")
    
    # Write to data/
    with open(os.path.join(DATA_DIR, "changelog.json"), "w", encoding="utf-8") as f:
        json.dump(changelog_payload, f, indent=2, ensure_ascii=False)
        
    with open(os.path.join(DATA_DIR, "insights.json"), "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)
        
    # Write to public/data/ for frontend direct loading
    with open(os.path.join(PUBLIC_DATA_DIR, "changelog.json"), "w", encoding="utf-8") as f:
        json.dump(changelog_payload, f, indent=2, ensure_ascii=False)
        
    with open(os.path.join(PUBLIC_DATA_DIR, "insights.json"), "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)
        
    print(f"[✓] Success! Processed {insights['metadata']['totalVersions']} versions with {insights['metadata']['totalItems']} changes.")
    print(f"[✓] Latest version: {insights['metadata']['latestVersion']} ({insights['metadata']['latestDate']})")

if __name__ == "__main__":
    main()
