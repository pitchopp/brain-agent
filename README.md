# brain-agent

Agent IA Telegram ↔ second brain Markdown. Un seul service FastAPI qui reçoit
des messages Telegram, les route (capture vs query) et laisse un agent Claude
(via le Claude Agent SDK) lire/écrire dans une copie locale du repo brain,
valider, committer et pusher sur GitHub.

## Architecture

```
Telegram ──webhook HTTPS──> FastAPI (brain-agent, Dokploy)
                                │
                                ├─ whitelist user_id + secret_token
                                ├─ détection intent (capture | query)
                                ├─ ClaudeSDKClient
                                │     ├─ tools built-in (Read/Write/Edit/Grep/Glob/Bash)
                                │     └─ MCP "brain" : validate_brain, git_commit_push
                                │     └─ system prompt dynamique
                                │         (CLAUDE.md + TAXONOMIE.md + MAP.md frais)
                                └─ réponse Telegram
                                
Background task : git pull --rebase toutes les 5 min sur /data/brain
```

## Pré-requis

1. **Bot Telegram** créé via [@BotFather](https://t.me/BotFather), token récupéré.
2. **Clé API Anthropic** (console Anthropic).
3. **Repo GitHub privé** pour le brain (ici `github.com:pitchopp/brain.git`).
4. **Deploy key SSH** avec accès **write** au repo brain
   (Settings → Deploy keys → Add deploy key, cocher *Allow write access*).
5. **VPS avec Dokploy** opérationnel et un domaine HTTPS disponible.
6. **Ton user_id Telegram** (envoie un message à [@userinfobot](https://t.me/userinfobot) pour l'obtenir).

## Variables d'environnement

Voir [.env.example](.env.example). Toutes obligatoires sauf mention.

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | Chaîne aléatoire, vérifiée à chaque call webhook |
| `ALLOWED_TELEGRAM_USER_IDS` | CSV des user_id autorisés (fail-closed si vide) |
| `TELEGRAM_ADMIN_CHAT_ID` | Chat id pour les notifs système (conflits git…) |
| `ANTHROPIC_API_KEY` | Clé API Anthropic |
| `ANTHROPIC_MODEL` | Défaut `claude-sonnet-4-5` |
| `BRAIN_REPO_URL` | URL SSH du repo brain, ex `git@github.com:pitchopp/brain.git` |
| `BRAIN_REPO_BRANCH` | Défaut `main` |
| `BRAIN_LOCAL_PATH` | Défaut `/data/brain` (ne pas changer en Dokploy) |
| `GIT_USER_NAME` / `GIT_USER_EMAIL` | Identité des commits du bot |
| `GIT_SSH_PRIVATE_KEY` | Clé privée PEM complète (multiline) de la deploy key |
| `BRAIN_PULL_INTERVAL_SECONDS` | Défaut 300 |
| `MAX_AGENT_TURNS` | Défaut 20 (garde-fou de coût) |
| `AGENT_TIMEOUT_SECONDS` | Défaut 120 |
| `LOG_LEVEL` | `INFO` / `DEBUG` |

## Développement local

Le projet utilise [uv](https://docs.astral.sh/uv/).

```bash
# 1. Installer les deps
cd brain-agent
uv sync

# 2. Lancer les tests unitaires
uv run pytest -v

# 3. Créer un .env (hors git, à côté du pyproject.toml)
cp .env.example .env
# puis remplir les variables

# 4. Lancer localement
uv run uvicorn brain_agent.main:app --reload
```

Pour tester en local avec Docker :

```bash
docker compose up --build
curl http://localhost:8000/health
```

## Déploiement sur Dokploy

### 1. Pousser le code sur GitHub

```bash
cd brain-agent
git init
git add .
git commit -m "init brain-agent"
git branch -M main
git remote add origin https://github.com/pitchopp/brain-agent.git
git push -u origin main
```

### 2. Créer l'application dans Dokploy

1. Dans ton projet Dokploy, **Create → Application → Docker** (ou *Dockerfile*)
2. **Source** : GitHub → repo `pitchopp/brain-agent`, branche `main`
3. **Build type** : Dockerfile (racine du repo)
4. **Port** : `8000`

### 3. Variables d'environnement

Dans l'onglet **Environment** de l'application Dokploy, ajouter chaque variable
du `.env.example`. Pour `GIT_SSH_PRIVATE_KEY`, coller la clé privée complète
**sur plusieurs lignes** (BEGIN/END inclus).

### 4. Volume persistant

Dans l'onglet **Volumes** : monter un volume nommé sur `/data/brain`.
Ce volume contient le clone du repo brain et survit aux redéploiements.

### 5. Domaine HTTPS

Onglet **Domains** : attacher un domaine (ex `brain-agent.tondomaine.com`),
activer HTTPS (Let's Encrypt).

### 6. Déployer

Bouton **Deploy**. Suivre les logs pour vérifier :
- SSH key écrite, clone du brain réussi (`Brain cloned successfully`)
- `puller started, interval=300s`
- `Uvicorn running on http://0.0.0.0:8000`

### 7. Enregistrer le webhook Telegram

Depuis ta machine :

```bash
BOT=123456:ABC...           # ton TELEGRAM_BOT_TOKEN
SECRET=ton_webhook_secret   # même valeur que TELEGRAM_WEBHOOK_SECRET
URL=https://brain-agent.tondomaine.com/webhook/telegram

curl -X POST "https://api.telegram.org/bot${BOT}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"${URL}\",\"secret_token\":\"${SECRET}\",\"allowed_updates\":[\"message\"]}"
```

Vérifier :

```bash
curl "https://api.telegram.org/bot${BOT}/getWebhookInfo"
```

Tu dois voir l'URL enregistrée et `pending_update_count: 0`.

## Tests end-to-end

Depuis ton compte Telegram autorisé, envoyer au bot :

1. **Query** (lecture seule) :
   > `qu'est-ce que j'ai noté sur l'immobilier ?`
   
   Attendu : réponse FR courte avec des `[[id-note]]` en références. Aucun commit.

2. **Capture simple** :
   > `note rapide : le principe de levier s'applique aussi aux réseaux, pas qu'au capital`
   
   Attendu : un commit apparaît sur `main` du repo brain (~30s), la réponse
   mentionne le SHA court et le `[[id]]` de la note créée ou mise à jour.

3. **Capture longue** :
   > `Idée à capturer : le "sweat equity" est un apport en compétences/temps dans un SPV, rémunéré via des CCA progressives selon milestones. Différent d'un apport en numéraire.`
   
   Attendu : note créée dans `knowledge/` avec frontmatter valide, 3+ wiki-links,
   MAP.md mis à jour, commit.

4. **Test garde-fou** : envoyer depuis un compte **non** whitelisté → aucune
   réponse, les logs Dokploy montrent `rejected user_id=... (not whitelisted)`.

## Commandes de debug utiles

```bash
# Dans le conteneur Dokploy (via terminal intégré)
ls /data/brain           # vérifier le clone
cd /data/brain && git log --oneline -5

# Retirer le webhook Telegram (pour debug)
curl -X POST "https://api.telegram.org/bot${BOT}/deleteWebhook"
```

## Organisation du code

```
src/brain_agent/
├── main.py            # FastAPI app + lifespan
├── config.py          # Settings pydantic
├── telegram/
│   ├── webhook.py     # POST /webhook/telegram
│   ├── client.py      # httpx Telegram API
│   └── formatter.py   # troncature / format
├── agent/
│   ├── runner.py      # ClaudeSDKClient wrapper
│   ├── prompt.py      # system prompt dynamique
│   └── intent.py      # capture vs query
├── brain/
│   ├── repo.py        # git clone/pull/commit/push
│   ├── puller.py      # background task
│   └── validation.py  # validators wiki-links + tags + frontmatter
└── tools/
    └── brain_mcp.py   # tools custom MCP in-process
```
