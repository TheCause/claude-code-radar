# 📡 Claude Code Radar & Observatoire Stratégique

Application locale de **visualisation graphique, analyse d'impact et exploration de l'historique** des évolutions de [Claude Code par Anthropic](https://code.claude.com/docs/en/changelog).

> **Périmètre & Sécurité** : Cet outil est dédié exclusivement à l'exploration analytique en local. Il n'envoie aucune notification externe (aucun webhook, aucun Telegram) et écoute strictement sur `127.0.0.1`.

---

## 🎯 Fonctionnalités Clés

1. **Tableau de Bord Visuel Interactif (Chart.js)** :
   - **Vélocité mensuelle** : suivi de la cadence (20 à 28 versions/mois en 2026 ; 13 à 28 versions/mois sur l'ensemble de l'historique 2025-2026).
   - **Nature des changements** : répartition entre ajouts (Features), correctifs (Fixes) et optimisations (Improvements).
   - **Poids des domaines par mots-clés** : Multi-Agent, MCP, Sécurité, Modèles de raisonnement, IDE & Cloud.

2. **Compréhension du Potentiel (5 Piliers Sourcés)** :
   - **Multi-Agents & Workflows Asynchrones** : sous-agents (`subagents`, `claude agents`), sessions d'arrière-plan (`claude --bg`), workflows (`/workflows`, `/batch`) et hooks de worktree (`WorktreeCreate`, ligne 134).
   - **Écosystème MCP & Extensibilité** : Model Context Protocol, mode URL elicitation (ligne 27), validation de configuration (`claude plugin validate`, ligne 28).
   - **Sécurité, Passerelle & Sandboxing** : Claude Apps Gateway (Bedrock IAM STS `assume_role` et Guardrails, lignes 23-24), Auto Mode avec classifieur côté serveur (ligne 148), sandboxing Bash (`sandbox.bwrapPath` sous Linux à la ligne 1989, AppContainer sous Windows à la ligne 1086, et limite mémoire cgroup Linux optionnelle via `CLAUDE_CODE_TOOL_MEMORY_LIMIT` à la ligne 1935).
   - **Interfaces Multiples (CLI, IDE, Web, Slack)** : Terminal interactif (mode Vim, navigation clavier), extensions VS Code / JetBrains, Web Cloud sessions (`claude.ai/code`, ligne 172), assistance Slack via `Claude Tag` (ligne 178).
   - **Modèles & Lecture de Cache** : Claude Opus 5.5 natif (1M tokens de contexte, 4 $/Mtok en entrée et 0,20 $/Mtok en lecture de cache, soit une division par 20 du coût de lecture, ligne 193).

3. **Game-Changers (Hall of Fame Sourcé)** :
   - Fiches des fonctionnalités phares avec numéro de ligne source dans `data/raw_changelog.md` et citations exactes.

4. **Explorateur Dynamique & Recherche Plein Texte** :
   - Recherche instantanée parmi les **400+ versions** et **6 200+ modifications**.
   - Filtres croisés par mot-clé, domaine et type d'action.

5. **Comparateur de Versions (Diff Tool)** :
   - Sélection de deux versions pour visualiser les fonctionnalités et corrections introduites dans l'intervalle.

6. **Sécurité Renforcée** :
   - Écoute strictement limitée à `127.0.0.1`.
   - Résolution stricte des chemins par `os.path.realpath` empêchant toute évasion de répertoire (testée avec `/data/../README.md`, `/data/%2e%2e/README.md`, etc.).
   - Route `/api/update` en POST uniquement (rejet 405 sur GET) avec verrou de concurrence (409 si déjà en cours).

---

## 🚀 Démarrage

### 1. Lancer l'Observatoire Web (sur 127.0.0.1)
```bash
python3 server.py
# ou : npm start
```
Ouvrez ensuite votre navigateur sur : **[http://127.0.0.1:3333](http://127.0.0.1:3333)**

---

### 2. Lancer les Tests de Sécurité (Unittest)
```bash
python3 tests/test_security.py
```
Vérifie la protection contre le path traversal, le rejet de GET sur `/api/update`, le verrou de mise à jour unique et le bind loopback.

---

### 3. Mettre à Jour les Données Manuellement
```bash
python3 scripts/update_changelog.py
# ou : npm run update
```

---

### 4. Configuration Optionnelle Launchd (macOS)
Le script [`scripts/setup_daily_cron.sh`](scripts/setup_daily_cron.sh) prépare localement le descripteur :
- Chemin absolu de Python détecté sur la machine (launchd n'hérite pas du `PATH`).
- `RunAtLoad` défini à `false`.
- Fichier généré localement dans `scripts/com.claude.changelog.daily.plist`.

Pour l'installer dans `~/Library/LaunchAgents/` :
```bash
./scripts/setup_daily_cron.sh --install
```
*(Non installé par défaut pour respecter l'isolation stricte du dossier de travail).*
