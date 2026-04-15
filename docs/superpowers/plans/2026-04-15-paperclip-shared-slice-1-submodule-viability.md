# Paperclip Shared Fragments — Slice #1: Submodule Viability

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Доказать что submodule-паттерн работает для `paperclip-shared-fragments` — перенести 5 existing Medic fragments в новый shared репо как submodule, **без правок содержимого и без других изменений**, убедиться что Medic-команда продолжает работать end-to-end.

**Architecture:** Копируем 5 существующих `Medic/paperclips/fragments/*.md` верхом в `paperclip-shared-fragments/fragments/`, tag `v0.0.1`. В Medic добавляем submodule в `paperclips/fragments/shared/`, удаляем локальные копии, обновляем `@include` пути в ролях, пересобираем `dist/`, атомарно деплоим в live `AGENTS.md`. Сравниваем byte-идентичность dist до/после — должно быть 0 различий (контент не менялся). Smoke test через Board comment подтверждает что agent chain не порвался.

**Tech Stack:**
- Git submodule
- Bash (build.sh, deploy.sh, measure.sh)
- SSH к `imac-ssh.ant013.work`
- Anthropic `POST /v1/messages/count_tokens` API (для токен-измерений)
- Python 3 inline (для JSON parsing в scripts)

**Спек-источник:** `Gimle-Palace/docs/superpowers/specs/2026-04-15-paperclip-shared-fragments-and-teams-design.md` §13.1

**Рабочие окружения:**
- Server canonical state: `imac-ssh.ant013.work`, user `anton`, password `0013`, Medic в `/Users/Shared/Ios/Medic/`
- Shared-репо: `git@github.com:ant013/paperclip-shared-fragments.git` (существует, 1 commit scaffold)
- Local dev machine: работаем в этой же сессии через SSH; локальные клоны репо не требуются

**Принцип:** если хоть один критерий отказа (§ в конце каждого Task'а) триггерится — **STOP**, фиксируем inцидент, не идём в Task #2/#3 из §13.2-13.3 спека.

---

## File Structure

**paperclip-shared-fragments repo** (после Task 1):
```
paperclip-shared-fragments/
├── README.md                         # modify: stub → real intro
├── .gitignore                        # existing (scaffold)
├── build.sh                          # create: копия Medic/paperclips/build.sh
└── fragments/
    ├── heartbeat-discipline.md       # create: verbatim copy from Medic server
    ├── git-workflow.md               # create: verbatim copy
    ├── worktree-discipline.md        # create: verbatim copy
    ├── pre-work-discovery.md         # create: verbatim copy
    └── language.md                   # create: verbatim copy
```

**Medic repo изменения** (Task 3-5):
```
/Users/Shared/Ios/Medic/
├── .gitmodules                       # create
├── paperclips/
│   ├── fragments/
│   │   └── shared/ → [submodule]    # create
│   ├── roles/                        # modify: 9 files — @include sed
│   │   ├── ceo.md                   
│   │   ├── cto.md                   
│   │   └── ... (7 more)
│   ├── build.sh                      # modify: если нужно — резолв нового пути
│   └── dist/                         # regenerate: 9 files (content unchanged)
├── tools/                            # create
│   └── measure.sh                    # create: wrapper над count_tokens API
│   └── deploy-agents.sh              # create: atomic deploy .tmp + mv
└── tmp/baseline-tokens.json          # create: baseline измерений (gitignored)
```

**Remote:** 9 files в `~/.paperclip/instances/default/companies/7c094d21-a02d-4554-8f35-730bf25ea492/agents/*/instructions/AGENTS.md` — обновляются deploy скриптом.

---

## Task 0: Preconditions Check

**Files:**
- Read-only: проверяем окружение
- Create: `/tmp/medic-preflight.txt` (output проверок для аудита)

- [ ] **Step 1: SSH connectivity**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'whoami && hostname && echo OK'
```
Expected output: `anton`, `Antons-iMac.local`, `OK`.

- [ ] **Step 2: Verify 5 Medic fragments exist on server**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'ls /Users/Shared/Ios/Medic/paperclips/fragments/*.md | wc -l'
```
Expected output: `5`.

- [ ] **Step 3: Verify all Medic agents idle**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require(\"/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg\");
(async()=>{const c=new Client({host:\"127.0.0.1\",port:54329,user:\"paperclip\",password:\"paperclip\",database:\"paperclip\"});
await c.connect();
const r=await c.query(\"SELECT COUNT(*) AS n FROM agents WHERE company_id=\\\$1 AND status!=\\x27idle\\x27\",[\"7c094d21-a02d-4554-8f35-730bf25ea492\"]);
console.log(\"non-idle agents:\",r.rows[0].n);
await c.end();})().catch(e=>{console.error(e.message);process.exit(1)})'"
```
Expected output: `non-idle agents: 0`.

**Failure criterion:** если `n > 0` — кто-то работает, подождать или запросить Anton pause всех через UI.

- [ ] **Step 4: Verify paperclip-shared-fragments repo reachable**

Run:
```bash
git ls-remote git@github.com:ant013/paperclip-shared-fragments.git HEAD
```
Expected output: one line with hash + `HEAD`.

- [ ] **Step 5: Verify at least one active Medic issue for smoke test later**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require(\"/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg\");
(async()=>{const c=new Client({host:\"127.0.0.1\",port:54329,user:\"paperclip\",password:\"paperclip\",database:\"paperclip\"});
await c.connect();
const r=await c.query(\"SELECT identifier, status FROM issues WHERE company_id=\\\$1 AND status NOT IN (\\x27done\\x27,\\x27cancelled\\x27,\\x27backlog\\x27) LIMIT 3\",[\"7c094d21-a02d-4554-8f35-730bf25ea492\"]);
for (const x of r.rows) console.log(x.identifier, x.status);
await c.end();})().catch(e=>{console.error(e.message);process.exit(1)})'"
```
Expected output: at least 1 line with issue identifier (STA-XX) and status.

---

## Task 1: Populate paperclip-shared-fragments repo

**Files:**
- Create on shared repo: `fragments/heartbeat-discipline.md`, `fragments/git-workflow.md`, `fragments/worktree-discipline.md`, `fragments/pre-work-discovery.md`, `fragments/language.md` (5 files)
- Create: `build.sh` (copy from Medic)
- Modify: `README.md` (replace scaffold intro)
- Create locally: `/tmp/paperclip-shared-work/` working dir

- [ ] **Step 1: Clone shared repo locally**

Run:
```bash
mkdir -p /tmp/paperclip-shared-work && cd /tmp/paperclip-shared-work
git clone git@github.com:ant013/paperclip-shared-fragments.git
cd paperclip-shared-fragments
git log --oneline | head -3
```
Expected: 1 commit visible (scaffold).

- [ ] **Step 2: Pull 5 fragments from Medic server**

Run (from inside `/tmp/paperclip-shared-work/paperclip-shared-fragments`):
```bash
mkdir -p fragments
for f in heartbeat-discipline.md git-workflow.md worktree-discipline.md pre-work-discovery.md language.md; do
  SSHPASS='0013' sshpass -e scp -o PreferredAuthentications=password -o PubkeyAuthentication=no anton@imac-ssh.ant013.work:/Users/Shared/Ios/Medic/paperclips/fragments/$f fragments/$f
done
ls fragments/
```
Expected output: 5 .md files listed.

- [ ] **Step 3: Pull build.sh from Medic server**

Run:
```bash
SSHPASS='0013' sshpass -e scp -o PreferredAuthentications=password -o PubkeyAuthentication=no anton@imac-ssh.ant013.work:/Users/Shared/Ios/Medic/paperclips/build.sh ./build.sh
chmod +x build.sh
head -5 build.sh
```
Expected output: bash shebang + первые строки awk-препроцессора.

- [ ] **Step 4: Replace README with real intro**

Edit `README.md` content to:
```markdown
# Paperclip Shared Fragments

Reusable building blocks для [Paperclip AI](https://github.com/paperclipai/paperclip) agent teams, переиспользуемые между проектами.

## Содержимое (v0.0.1)

- `fragments/` — атомарные `@include`-блоки правил (heartbeat discipline, git workflow, worktree discipline, pre-work discovery, language)
- `build.sh` — awk-препроцессор: резолвит `<!-- @include fragments/X.md -->`

## Consumers

- [Medic](https://github.com/ant013/Medic) — health/medication kit

## Status

**v0.0.1 — slice #1 validation.** Содержит только 5 existing Medic fragments без правок. Проверяется submodule viability. См. `Gimle-Palace/docs/superpowers/plans/2026-04-15-paperclip-shared-slice-1-submodule-viability.md`.

Расширение scope (fragments Category B, templates, research notes) — только после успеха slice #1.
```

- [ ] **Step 5: Commit all new files + tag v0.0.1 + push**

Run:
```bash
git add fragments/ build.sh README.md
git -c user.name="Anton Stavnichiy" -c user.email="ant013@icloud.com" commit -m "feat(slice-1): import 5 Medic fragments + build.sh verbatim

Slice #1 of paperclip-shared-fragments viability validation.
No content changes — exact byte copy from /Users/Shared/Ios/Medic/paperclips/
on server canonical.

Ref: Gimle-Palace/docs/superpowers/plans/2026-04-15-paperclip-shared-slice-1-submodule-viability.md"
git tag v0.0.1
git push origin main --tags
```
Expected output: commit + tag pushed, `main` branch now has 2 commits.

**Failure criteria:**
- SCP fails (auth / network) — retry, escalate SSH issue
- Push rejected — check branch protection settings, temporarily allow admin push or use PR

---

## Task 2: Baseline measurement of current live AGENTS.md

**Files:**
- Create: `/tmp/paperclip-shared-work/baseline-tokens.json` — snapshot of current state
- Uses: Anthropic `count_tokens` API (key from paperclip config)

- [ ] **Step 1: Extract API key once**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'python3 -c "import json;print(json.load(open(\"/Users/anton/.paperclip/instances/default/config.json\"))[\"llm\"][\"apiKey\"])"' > /tmp/paperclip-shared-work/api-key.txt
wc -c /tmp/paperclip-shared-work/api-key.txt
chmod 600 /tmp/paperclip-shared-work/api-key.txt
```
Expected output: file with >80 bytes (JWT-like string).

- [ ] **Step 2: Measure all 9 live AGENTS.md on server**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const fs=require(\"fs\"), https=require(\"https\");
const API=JSON.parse(fs.readFileSync(\"/Users/anton/.paperclip/instances/default/config.json\")).llm.apiKey;
const DIR=\"/Users/anton/.paperclip/instances/default/companies/7c094d21-a02d-4554-8f35-730bf25ea492/agents\";
(async()=>{
  const out=[];
  for (const id of fs.readdirSync(DIR)) {
    const path=DIR+\"/\"+id+\"/instructions/AGENTS.md\";
    if (!fs.existsSync(path)) continue;
    const body=fs.readFileSync(path,\"utf8\");
    const data=JSON.stringify({model:\"claude-sonnet-4-5-20250929\",messages:[{role:\"user\",content:body}]});
    const res=await new Promise((r,rj)=>{
      const req=https.request({hostname:\"api.anthropic.com\",path:\"/v1/messages/count_tokens\",method:\"POST\",headers:{\"x-api-key\":API,\"anthropic-version\":\"2023-06-01\",\"content-type\":\"application/json\",\"content-length\":Buffer.byteLength(data)}},res=>{
        let d=\"\";res.on(\"data\",c=>d+=c);res.on(\"end\",()=>r(JSON.parse(d)));
      });
      req.on(\"error\",rj);req.write(data);req.end();
    });
    out.push({agent_id:id,bytes:body.length,tokens:res.input_tokens});
  }
  console.log(JSON.stringify(out,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
'" > /tmp/paperclip-shared-work/baseline-tokens.json
cat /tmp/paperclip-shared-work/baseline-tokens.json
```
Expected output: JSON array with 9 entries, each with `agent_id`, `bytes`, `tokens` fields. Все tokens должны быть в диапазоне 1500-5000.

- [ ] **Step 3: Archive baseline for post-migration comparison**

Run:
```bash
cp /tmp/paperclip-shared-work/baseline-tokens.json /tmp/paperclip-shared-work/baseline-pre-migration.json
ls -la /tmp/paperclip-shared-work/
```
Expected: два файла (baseline + baseline-pre-migration) идентичны.

**Failure criteria:**
- API returns 401/403 — API key invalid or rate-limited, abort
- Some agent AGENTS.md file missing — investigate, can be legit (archived?) but flag

---

## Task 3: Add submodule to Medic + remove local fragments

**Files on server:**
- Create: `/Users/Shared/Ios/Medic/.gitmodules`
- Create (git submodule): `/Users/Shared/Ios/Medic/paperclips/fragments/shared/` (cloned)
- Delete: `/Users/Shared/Ios/Medic/paperclips/fragments/*.md` (5 files)

- [ ] **Step 1: Pre-change git status of Medic server**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git branch --show-current && git status --short'
```
Expected output: current branch name + clean or small `M .temp/cli-latest` only.

**Failure criterion:** если в `git status` есть `paperclips/` modifications — отложить, очистить stage first.

- [ ] **Step 2: Create feature branch for migration**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git fetch origin && git checkout -b refactor/paperclips-shared-fragments origin/develop'
```
Expected output: switched to new branch based on origin/develop.

- [ ] **Step 3: Add submodule**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git submodule add --depth 1 git@github.com:ant013/paperclip-shared-fragments.git paperclips/fragments/shared && ls paperclips/fragments/shared/'
```
Expected output: submodule clone message + listing containing README.md, build.sh, fragments/.

- [ ] **Step 4: Verify submodule content matches shared repo**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && diff <(ls paperclips/fragments/shared/fragments/) <(echo "git-workflow.md"; echo "heartbeat-discipline.md"; echo "language.md"; echo "pre-work-discovery.md"; echo "worktree-discipline.md") || echo MISMATCH'
```
Expected: no diff output (lists match) OR "MISMATCH" → abort.

- [ ] **Step 5: Verify fragment content is byte-identical (sanity check)**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && for f in heartbeat-discipline.md git-workflow.md worktree-discipline.md pre-work-discovery.md language.md; do
  if diff -q paperclips/fragments/$f paperclips/fragments/shared/fragments/$f > /dev/null; then
    echo "OK: $f identical"
  else
    echo "DIFF: $f — submodule != local"
    diff paperclips/fragments/$f paperclips/fragments/shared/fragments/$f
  fi
done'
```
Expected output: 5 lines `OK: <filename> identical`.

**Failure criterion:** любой `DIFF:` — abort, investigate (submodule has stale commit?).

---

## Task 4: Update @include paths in Medic roles

**Files on server:**
- Modify: `/Users/Shared/Ios/Medic/paperclips/roles/*.md` (9 files — sed @include)

- [ ] **Step 1: Count @include markers before change (expect 5+ per role avg)**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && grep -cE "@include fragments/" paperclips/roles/*.md'
```
Expected output: 9 lines, each with filename:N (N ≥ 3 for each role).

- [ ] **Step 2: Sed replace `@include fragments/` → `@include fragments/shared/` в roles**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && for f in paperclips/roles/*.md; do
  sed -i "" "s|@include fragments/\\([a-z-]*\\.md\\)|@include fragments/shared/\\1|g" "$f"
done
grep -c "@include fragments/shared/" paperclips/roles/*.md'
```
Expected output: 9 lines, counts same as Step 1.

- [ ] **Step 3: Verify no stale `@include fragments/X.md` остались (без shared/)**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && grep -n "@include fragments/[a-z]" paperclips/roles/*.md | grep -v shared || echo "NONE — clean"'
```
Expected output: `NONE — clean`.

**Failure criterion:** если есть строки без `shared/` — неверный sed, abort + revert.

---

## Task 5: Remove local fragments + rebuild dist + verify byte-identical

**Files on server:**
- Delete: `/Users/Shared/Ios/Medic/paperclips/fragments/heartbeat-discipline.md`, `git-workflow.md`, `worktree-discipline.md`, `pre-work-discovery.md`, `language.md` (5 files)
- Regenerate: `/Users/Shared/Ios/Medic/paperclips/dist/*.md` (9 files)

- [ ] **Step 1: Backup current dist/ before rebuild**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && cp -r paperclips/dist /tmp/medic-dist-pre-migration && ls /tmp/medic-dist-pre-migration/'
```
Expected: 9 .md files listed in backup dir.

- [ ] **Step 2: Remove local fragments (submodule stays, root fragments/*.md go)**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git rm paperclips/fragments/heartbeat-discipline.md paperclips/fragments/git-workflow.md paperclips/fragments/worktree-discipline.md paperclips/fragments/pre-work-discovery.md paperclips/fragments/language.md && ls paperclips/fragments/'
```
Expected output: only `shared` directory remains in `paperclips/fragments/`.

- [ ] **Step 3: Check if build.sh уже работает с новым путём (скорее всего — нет)**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && cat paperclips/build.sh'
```
Expected: original script — смотри строку `frag = substr($0, RSTART + 10, RLENGTH - 10)` и путь `FRAG_DIR="$SCRIPT_DIR/fragments"`.

Если build.sh статично указывает на `fragments/` (не на `fragments/shared/`) — продолжаем к Step 4. Если скрипт умеет резолвить `fragments/shared/` благодаря `@include fragments/shared/X.md` синтаксису + awk режет префикс `fragments/` → **надо скорректировать** awk-код.

- [ ] **Step 4: Скорректировать build.sh — резолвить `fragments/shared/X.md` как `shared/X.md` относительно FRAG_DIR**

Заменить в build.sh блок awk (он сейчас обрезает `fragments/` и берёт имя файла, но для `fragments/shared/X.md` надо брать `shared/X.md`):

Нужный awk-код:
```bash
awk -v frag_dir="$FRAG_DIR" '
  /<!-- @include fragments\/.*\.md -->/ {
    match($0, /fragments\/[^ ]+\.md/)
    # Берём всё после "fragments/" до конца matched string
    rel = substr($0, RSTART + 10, RLENGTH - 10)
    path = frag_dir "/" rel
    if ((getline line < path) <= 0) {
      print "ERROR: cannot read " path > "/dev/stderr"
      exit 2
    }
    print line
    while ((getline line < path) > 0) print line
    close(path)
    next
  }
  { print }
' "$role_file" > "$out_file"
```

Run (применяем через heredoc-replace):
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cat > /Users/Shared/Ios/Medic/paperclips/build.sh << '"'"'BUILDSH'"'"'
#!/usr/bin/env bash
# Expands `<!-- @include fragments/X.md -->` markers in roles/*.md into dist/*.md
# Supports both `fragments/X.md` (legacy) and `fragments/shared/X.md` (submodule-backed)
# Path after "fragments/" is resolved relative to FRAG_DIR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLES_DIR="$SCRIPT_DIR/roles"
FRAG_DIR="$SCRIPT_DIR/fragments"
OUT_DIR="$SCRIPT_DIR/dist"

mkdir -p "$OUT_DIR"

for role_file in "$ROLES_DIR"/*.md; do
  role_name=$(basename "$role_file")
  out_file="$OUT_DIR/$role_name"
  awk -v frag_dir="$FRAG_DIR" '"'"'
    /<!-- @include fragments\/.*\.md -->/ {
      match($0, /fragments\/[^ ]+\.md/)
      rel = substr($0, RSTART + 10, RLENGTH - 10)
      path = frag_dir "/" rel
      if ((getline line < path) <= 0) {
        print "ERROR: cannot read " path > "/dev/stderr"
        close(path)
        exit 2
      }
      print line
      while ((getline line < path) > 0) print line
      close(path)
      next
    }
    { print }
  '"'"' "$role_file" > "$out_file"
  echo "built $out_file"
done
BUILDSH
chmod +x /Users/Shared/Ios/Medic/paperclips/build.sh
head -20 /Users/Shared/Ios/Medic/paperclips/build.sh'
```
Expected output: first 20 lines of the new build.sh.

- [ ] **Step 5: Run build.sh, observe no errors**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && ./paperclips/build.sh 2>&1 | tail -15'
```
Expected output: 9 lines `built .../dist/<role>.md`, no `ERROR:` lines.

**Failure criterion:** any `ERROR: cannot read` → submodule content missing or @include path mismatch. Abort + revert.

- [ ] **Step 6: Byte-identical check vs backup — CRITICAL**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && for f in paperclips/dist/*.md; do
  name=$(basename "$f")
  if diff -q "$f" "/tmp/medic-dist-pre-migration/$name" > /dev/null; then
    echo "OK: $name byte-identical"
  else
    echo "DIFF: $name"
    diff "$f" "/tmp/medic-dist-pre-migration/$name" | head -10
  fi
done'
```
Expected output: 9 lines `OK: <role>.md byte-identical`.

**Failure criterion:** any `DIFF:` line — content changed during migration, which means `@include` isn't resolving identically. Investigate specific file, abort + revert.

---

## Task 6: Draft + run atomic deploy-agents.sh

**Files on server:**
- Create: `/Users/Shared/Ios/Medic/tools/deploy-agents.sh`
- Modify: 9 live `~/.paperclip/.../AGENTS.md` files (atomically)

- [ ] **Step 1: Create tools/ dir + draft deploy-agents.sh**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'mkdir -p /Users/Shared/Ios/Medic/tools && cat > /Users/Shared/Ios/Medic/tools/deploy-agents.sh << '"'"'DEPLOY'"'"'
#!/usr/bin/env bash
# Atomically deploy Medic paperclips/dist/*.md to live AGENTS.md for each agent.
# Strategy: write to .tmp → rename all at once at the end. If any write fails,
# nothing is left half-updated.
set -euo pipefail

MEDIC_ROOT="/Users/Shared/Ios/Medic"
COMPANY_ID="7c094d21-a02d-4554-8f35-730bf25ea492"
LIVE_BASE="/Users/anton/.paperclip/instances/default/companies/$COMPANY_ID/agents"
DIST="$MEDIC_ROOT/paperclips/dist"

# agent_name → agent_id mapping (Medic, 9 agents)
declare -a MAPPING=(
  "backend-engineer.md:cdf1455f-0873-465a-b1d5-a581272c608e"
  "ceo.md:419d56ec-e3da-47bc-bce9-2979f100d8b9"
  "code-reviewer.md:cf52c981-165e-4239-a2bb-f590be87de79"
  "cto.md:780ec10f-f42b-415e-9b38-e89b08510806"
  "ios-engineer.md:c47eb69e-5e77-46f8-922f-d862b682dbee"
  "kmp-engineer.md:1222c2f7-cee8-43b3-8c7d-1ecc5a980b99"
  "qa-engineer.md:1f65199b-4f8e-4d92-9c44-4a2ea0a2bd40"
  "research-agent.md:5085cd02-2b61-48c4-9115-79824c45473f"
  "ux-designer.md:20b806a1-1618-4bf9-ae6d-fae4226c5e61"
)

# Stage 1: write all .tmp files
for pair in "${MAPPING[@]}"; do
  src="${pair%%:*}"
  id="${pair##*:}"
  dest="$LIVE_BASE/$id/instructions/AGENTS.md"
  tmp="$dest.tmp"
  [[ -f "$DIST/$src" ]] || { echo "ERROR: missing $DIST/$src"; exit 1; }
  [[ -d "$(dirname "$dest")" ]] || { echo "ERROR: missing dest dir $(dirname "$dest")"; exit 1; }
  cp "$DIST/$src" "$tmp"
done

# Stage 2: atomic rename all
for pair in "${MAPPING[@]}"; do
  id="${pair##*:}"
  dest="$LIVE_BASE/$id/instructions/AGENTS.md"
  mv "$dest.tmp" "$dest"
done

echo "Deployed ${#MAPPING[@]} agents successfully"
DEPLOY
chmod +x /Users/Shared/Ios/Medic/tools/deploy-agents.sh
head -30 /Users/Shared/Ios/Medic/tools/deploy-agents.sh'
```
Expected: first 30 lines of deploy-agents.sh shown.

- [ ] **Step 2: Backup current live AGENTS.md files (safety)**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'mkdir -p /tmp/medic-live-backup-pre-migration && COMPANY=/Users/anton/.paperclip/instances/default/companies/7c094d21-a02d-4554-8f35-730bf25ea492/agents && for agent_dir in "$COMPANY"/*/; do
  id=$(basename "$agent_dir")
  cp "$agent_dir/instructions/AGENTS.md" "/tmp/medic-live-backup-pre-migration/$id.AGENTS.md"
done && ls /tmp/medic-live-backup-pre-migration/ | wc -l'
```
Expected output: `9` (9 backup files).

- [ ] **Step 3: Run deploy-agents.sh**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work '/Users/Shared/Ios/Medic/tools/deploy-agents.sh'
```
Expected output: `Deployed 9 agents successfully`.

**Failure criterion:** any ERROR line → abort, live AGENTS.md в .tmp состоянии — ручками убрать .tmp файлы, переразвернуть.

- [ ] **Step 4: Verify live AGENTS.md files bytes match dist**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'COMPANY=/Users/anton/.paperclip/instances/default/companies/7c094d21-a02d-4554-8f35-730bf25ea492/agents
MAP=(
  "backend-engineer.md:cdf1455f-0873-465a-b1d5-a581272c608e"
  "ceo.md:419d56ec-e3da-47bc-bce9-2979f100d8b9"
  "code-reviewer.md:cf52c981-165e-4239-a2bb-f590be87de79"
  "cto.md:780ec10f-f42b-415e-9b38-e89b08510806"
  "ios-engineer.md:c47eb69e-5e77-46f8-922f-d862b682dbee"
  "kmp-engineer.md:1222c2f7-cee8-43b3-8c7d-1ecc5a980b99"
  "qa-engineer.md:1f65199b-4f8e-4d92-9c44-4a2ea0a2bd40"
  "research-agent.md:5085cd02-2b61-48c4-9115-79824c45473f"
  "ux-designer.md:20b806a1-1618-4bf9-ae6d-fae4226c5e61"
)
for pair in "${MAP[@]}"; do
  name="${pair%%:*}"
  id="${pair##*:}"
  if diff -q /Users/Shared/Ios/Medic/paperclips/dist/$name $COMPANY/$id/instructions/AGENTS.md > /dev/null; then
    echo "OK: $name deployed identical"
  else
    echo "DIFF: $name"
  fi
done'
```
Expected output: 9 lines `OK: <name> deployed identical`.

---

## Task 7: Post-deploy token measurement — compare to baseline

**Files:**
- Read: `/tmp/paperclip-shared-work/baseline-pre-migration.json`
- Create: `/tmp/paperclip-shared-work/post-migration-tokens.json`

- [ ] **Step 1: Re-measure all 9 live AGENTS.md after migration**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const fs=require(\"fs\"), https=require(\"https\");
const API=JSON.parse(fs.readFileSync(\"/Users/anton/.paperclip/instances/default/config.json\")).llm.apiKey;
const DIR=\"/Users/anton/.paperclip/instances/default/companies/7c094d21-a02d-4554-8f35-730bf25ea492/agents\";
(async()=>{
  const out=[];
  for (const id of fs.readdirSync(DIR)) {
    const path=DIR+\"/\"+id+\"/instructions/AGENTS.md\";
    if (!fs.existsSync(path)) continue;
    const body=fs.readFileSync(path,\"utf8\");
    const data=JSON.stringify({model:\"claude-sonnet-4-5-20250929\",messages:[{role:\"user\",content:body}]});
    const res=await new Promise((r,rj)=>{
      const req=https.request({hostname:\"api.anthropic.com\",path:\"/v1/messages/count_tokens\",method:\"POST\",headers:{\"x-api-key\":API,\"anthropic-version\":\"2023-06-01\",\"content-type\":\"application/json\",\"content-length\":Buffer.byteLength(data)}},res=>{
        let d=\"\";res.on(\"data\",c=>d+=c);res.on(\"end\",()=>r(JSON.parse(d)));
      });
      req.on(\"error\",rj);req.write(data);req.end();
    });
    out.push({agent_id:id,bytes:body.length,tokens:res.input_tokens});
  }
  console.log(JSON.stringify(out,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
'" > /tmp/paperclip-shared-work/post-migration-tokens.json
cat /tmp/paperclip-shared-work/post-migration-tokens.json
```
Expected output: JSON с 9 записями.

- [ ] **Step 2: Compare baseline vs post-migration — CRITICAL**

Run:
```bash
python3 << 'PYEOF'
import json
base=json.load(open("/tmp/paperclip-shared-work/baseline-pre-migration.json"))
post=json.load(open("/tmp/paperclip-shared-work/post-migration-tokens.json"))
base_map={x["agent_id"]:x for x in base}
post_map={x["agent_id"]:x for x in post}
all_ok=True
for aid in sorted(base_map.keys()):
    b=base_map[aid]
    p=post_map.get(aid)
    if not p:
        print(f"MISSING post-migration: {aid}")
        all_ok=False
        continue
    dt=p["tokens"]-b["tokens"]
    db=p["bytes"]-b["bytes"]
    status="OK" if dt==0 and db==0 else "DIFF"
    if status=="DIFF": all_ok=False
    print(f"{status} {aid[:8]}: bytes {b['bytes']}→{p['bytes']} (Δ{db:+d}), tokens {b['tokens']}→{p['tokens']} (Δ{dt:+d})")
print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
PYEOF
```
Expected output: 9 lines `OK <id>: bytes N→N (Δ+0), tokens M→M (Δ+0)` + `Overall: PASS`.

**Failure criterion:** **ANY** `DIFF` или `Overall: FAIL` → live AGENTS.md различаются pre/post → submodule migration поменяла рендер; это регрессия. Abort + rollback (восстановить из `/tmp/medic-live-backup-pre-migration/`).

---

## Task 8: Smoke test — Medic chain still alive

**Files:** no file changes. Verification via DB + observing runs.

- [ ] **Step 1: Capture pre-smoke snapshot of agent state**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require(\"/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg\");
(async()=>{const c=new Client({host:\"127.0.0.1\",port:54329,user:\"paperclip\",password:\"paperclip\",database:\"paperclip\"});
await c.connect();
const r=await c.query(\"SELECT name, status, last_heartbeat_at FROM agents WHERE company_id=\\\$1 ORDER BY name\",[\"7c094d21-a02d-4554-8f35-730bf25ea492\"]);
for (const x of r.rows) console.log(x.name.padEnd(17)+\" \"+x.status+\" last=\"+(x.last_heartbeat_at?x.last_heartbeat_at.toISOString().slice(11,19):\"-\"));
const now=await c.query(\"SELECT NOW() as t\");
console.log(\"NOW UTC: \"+now.rows[0].t.toISOString());
await c.end();})().catch(e=>{console.error(e.message);process.exit(1)})'"
```
Expected: 9 agents listed with statuses + current UTC time. Note last_heartbeat_at values.

- [ ] **Step 2: Pick target issue for smoke test**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require(\"/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg\");
(async()=>{const c=new Client({host:\"127.0.0.1\",port:54329,user:\"paperclip\",password:\"paperclip\",database:\"paperclip\"});
await c.connect();
const r=await c.query(\"SELECT id, identifier, title, status, assignee_agent_id FROM issues WHERE company_id=\\\$1 AND status NOT IN (\\x27done\\x27,\\x27cancelled\\x27,\\x27backlog\\x27) ORDER BY updated_at DESC LIMIT 5\",[\"7c094d21-a02d-4554-8f35-730bf25ea492\"]);
for (const x of r.rows) console.log(x.identifier+\" | \"+x.status+\" | \"+x.title.slice(0,60));
await c.end();})().catch(e=>{console.error(e.message);process.exit(1)})'"
```
Expected: list of up to 5 active issues. **Pick one** and remember identifier (`STA-XX`) for next step.

- [ ] **Step 3: Board comment on chosen issue mentioning @CTO**

**Manual step — ask the user (Anton):** go to `https://paperclip.ant013.work`, open the chosen issue (identifier from Step 2), add a comment:
```
@CTO проверь что цепочка работает после submodule-migration. Это smoke test.
```

Then notify plan-executor when comment is posted.

- [ ] **Step 4: Observe wake within 60 seconds**

Run (after Step 3):
```bash
sleep 30 && SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require(\"/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg\");
(async()=>{const c=new Client({host:\"127.0.0.1\",port:54329,user:\"paperclip\",password:\"paperclip\",database:\"paperclip\"});
await c.connect();
const r=await c.query(\"SELECT a.name, w.source, w.reason, w.status, w.requested_at FROM agent_wakeup_requests w JOIN agents a ON a.id=w.agent_id WHERE w.company_id=\\\$1 AND w.requested_at > NOW() - INTERVAL \\x27 5 minutes \\x27 ORDER BY w.requested_at DESC LIMIT 5\",[\"7c094d21-a02d-4554-8f35-730bf25ea492\"]);
console.log(\"Recent wakeups:\");
for (const x of r.rows) console.log(\"  \"+x.requested_at.toISOString().slice(11,19)+\" \"+x.name+\" source=\"+x.source+\" reason=\"+x.reason+\" status=\"+x.status);
await c.end();})().catch(e=>{console.error(e.message);process.exit(1)})'"
```
Expected output: at least 1 wakeup for CTO with reason `issue_comment_mentioned` or similar, within last 5 min.

**Failure criterion:** no wakeup found after 60s → @-mention broken OR deployment broke agent reachability. Investigate + rollback.

- [ ] **Step 5: Observe CTO's run success**

Run (wait ~2 min after wake to let CTO complete):
```bash
sleep 120 && SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work "/Users/anton/.nvm/versions/node/v20.20.2/bin/node -e '
const {Client}=require(\"/Users/anton/.npm/_npx/43414d9b790239bb/node_modules/pg\");
(async()=>{const c=new Client({host:\"127.0.0.1\",port:54329,user:\"paperclip\",password:\"paperclip\",database:\"paperclip\"});
await c.connect();
const r=await c.query(\"SELECT a.name, hr.status, hr.started_at, hr.finished_at, hr.id, hr.error_code FROM heartbeat_runs hr JOIN agents a ON a.id=hr.agent_id WHERE hr.company_id=\\\$1 AND hr.started_at > NOW() - INTERVAL \\x27 10 minutes \\x27 ORDER BY hr.started_at DESC LIMIT 3\",[\"7c094d21-a02d-4554-8f35-730bf25ea492\"]);
console.log(\"Recent runs:\");
for (const x of r.rows) console.log(\"  \"+(x.started_at?x.started_at.toISOString().slice(11,19):\"-\")+\" \"+x.name+\" status=\"+x.status+\" err=\"+(x.error_code||\"-\")+\" id=\"+x.id.slice(0,8));
await c.end();})().catch(e=>{console.error(e.message);process.exit(1)})'"
```
Expected output: at least 1 CTO run with `status=succeeded`, no error_code.

**Failure criterion:** status `failed` or `timed_out` → investigate run log at `~/.paperclip/.../data/run-logs/<company>/<ctoid>/<runid>.ndjson` tail.

- [ ] **Step 6: Spot-check CTO used new fragments correctly**

Run (find CTO's run log и проверяем что AGENTS.md в его контексте новый):
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'ls -lt /Users/anton/.paperclip/instances/default/data/run-logs/7c094d21-a02d-4554-8f35-730bf25ea492/780ec10f-f42b-415e-9b38-e89b08510806/*.ndjson | head -1 | awk "{print \$NF}" | xargs head -c 20000 | grep -oE "@-упоминания|Handoff|handoff" | head -5'
```
Expected output: at least 1 line confirming fragment content (handoff/mention rules are from `heartbeat-discipline.md`, proving it was loaded).

---

## Task 9: Commit Medic migration + push (if smoke passed)

**Files on server:** commit all changes, push branch, open PR.

- [ ] **Step 1: Review changed files**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git status && echo "---diff summary---" && git diff --stat'
```
Expected: `.gitmodules` added, `paperclips/fragments/shared` added, 5 fragment files removed, 9 role files modified (sed), `paperclips/build.sh` modified, 9 dist files modified (likely 0-byte change but timestamp), `tools/deploy-agents.sh` new.

- [ ] **Step 2: Commit**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git add .gitmodules paperclips/fragments/shared paperclips/fragments paperclips/roles paperclips/build.sh paperclips/dist tools/ && git -c user.name="Anton Stavnichiy" -c user.email="ant013@icloud.com" commit -m "refactor(paperclips): migrate fragments to paperclip-shared-fragments submodule

Slice #1 of shared-fragments viability validation.

- Added paperclips/fragments/shared as git submodule → ant013/paperclip-shared-fragments v0.0.1
- Removed 5 local fragment copies (heartbeat, git-workflow, worktree, pre-work, language)
- Updated @include paths in 9 role files (fragments/ → fragments/shared/)
- Hardened paperclips/build.sh with set -euo pipefail and error-on-missing-file
- Added tools/deploy-agents.sh for atomic live AGENTS.md deployment
- Regenerated dist/ (content byte-identical to pre-migration)

Live AGENTS.md bytes + tokens confirmed identical vs baseline (Task 7).
Smoke test passed: CTO wake + run succeeded after Board comment (Task 8).

Ref: Gimle-Palace/docs/superpowers/plans/2026-04-15-paperclip-shared-slice-1-submodule-viability.md
Ref: Gimle-Palace/docs/superpowers/specs/2026-04-15-paperclip-shared-fragments-and-teams-design.md §13.1

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"'
```
Expected output: single commit, `X files changed`.

- [ ] **Step 3: Push feature branch + open PR**

Run:
```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic && git push -u origin refactor/paperclips-shared-fragments 2>&1 | tail -3'
```
Expected output: push succeeded.

- [ ] **Step 4: Confirm CI green (manual)**

**Manual step:** check GitHub Actions status for the new branch. If CI passes — merge to `develop` via PR.

---

## Task 10: Document outcome + advance spec

**Files:**
- Modify: `Gimle-Palace/docs/superpowers/specs/2026-04-15-paperclip-shared-fragments-and-teams-design.md` (add Slice #1 outcome section)
- Modify locally: `Gimle-Palace/docs/superpowers/plans/2026-04-15-paperclip-shared-slice-1-submodule-viability.md` (mark completed)

- [ ] **Step 1: Append outcome section to spec §13.1**

Add below §13.1 scope list:
```markdown
### 13.1.1 Slice #1 outcome (filled after execution)

- Executed: **YYYY-MM-DD by <who>**
- Token delta (pre vs post migration, all 9 agents): **all Δ=0** (or list any diffs)
- Smoke test result: **PASS / FAIL** (одна из)
- Time spent: **N hours**
- Surprises / findings:
  - (заполнить если что-то интересное)
- Decision: **proceed to slice #2** (per §13.2) / **pause + redesign §X**
```

- [ ] **Step 2: Commit spec update**

Run:
```bash
cd /Users/ant013/Android/Gimle-Palace && git add docs/superpowers/specs/2026-04-15-paperclip-shared-fragments-and-teams-design.md && git -c user.name="Anton Stavnichiy" -c user.email="ant013@icloud.com" commit -m "docs(spec): record slice #1 outcome in §13.1.1"
```

- [ ] **Step 3: Now it's OK to push Gimle-Palace spec commits**

Run:
```bash
cd /Users/ant013/Android/Gimle-Palace && git push origin main
```
Expected output: 3 commits pushed (0d7aaa2, 155ccb4, new outcome commit).

---

## Rollback procedure (если что-то пошло не так)

**Если в Task 5 или Task 6 детектируем regression:**

```bash
SSHPASS='0013' sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 imac-ssh.ant013.work 'cd /Users/Shared/Ios/Medic
# Revert all uncommitted changes
git checkout .
git clean -fdx paperclips/fragments/shared
git submodule deinit -f paperclips/fragments/shared
# Восстановить удалённые fragments
git checkout HEAD paperclips/fragments/
# Вернуться на develop
git checkout develop
git branch -D refactor/paperclips-shared-fragments
# Восстановить live AGENTS.md из backup
COMPANY=/Users/anton/.paperclip/instances/default/companies/7c094d21-a02d-4554-8f35-730bf25ea492/agents
for bk in /tmp/medic-live-backup-pre-migration/*.AGENTS.md; do
  id=$(basename "$bk" .AGENTS.md)
  cp "$bk" "$COMPANY/$id/instructions/AGENTS.md"
done'
```

Затем на shared-репо убрать tag если нужно:
```bash
cd /tmp/paperclip-shared-work/paperclip-shared-fragments
git push --delete origin v0.0.1
git tag -d v0.0.1
```

---

## Success Criteria (по §11.1 спеcка)

Slice #1 считается успешным ТОЛЬКО если **ВСЕ** из следующего:
1. ✅ Submodule cloned и содержит все 5 fragments identical to original
2. ✅ build.sh regenerates dist/ без errors, все 9 dist файлов byte-identical vs pre-migration
3. ✅ deploy-agents.sh outputs `Deployed 9 agents successfully`
4. ✅ Live AGENTS.md tokens identical vs baseline (Δ=0 для всех 9 агентов)
5. ✅ Smoke test: CTO wakeup fired after Board comment, run status=succeeded
6. ✅ Commit + push на feature branch без CI errors

**Если хоть один пункт FAIL — STOP, не идём в Slice #2/#3 спека.**

---

_Plan создан: 2026-04-15. Версия 1.0._
