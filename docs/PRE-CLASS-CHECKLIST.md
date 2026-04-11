# Pre-Class Checklist

The runbook to walk before class day. Designed to be done in two sessions:
**T-24h** (the day before, while everything is still fixable) and
**T-30min** (final go/no-go).

This file is for the instructor only — it's deliberately not in
`docs/wiki/` since that's the student-facing surface.

---

## T-24h: dry-run

**Goal:** prove the entire branch-to-live loop works end-to-end with a
fake student PR. If anything breaks now, you have time to fix it.

### 1. Slim is online and healthy (5 min)

```bash
# From your laptop
ssh james@slim 'uptime && uname -a && docker --version'
ssh james@slim 'docker ps'
ssh james@slim 'systemctl status cloudflared --no-pager | head -10'
ssh james@slim 'sudo systemctl status nftables --no-pager 2>/dev/null || true'
```

Verify:

- [ ] Slim's uptime is reasonable
- [ ] Docker is running, all 3 wize73 containers are up
- [ ] `cloudflared` systemd unit is `active (running)`
- [ ] nftables wize73 table exists (`sudo nft list table inet wize73`)

### 2. Public URL is healthy (2 min)

```bash
curl -i https://class.wize73.com/healthz
curl -s https://class.wize73.com/metrics/ | grep "Token flow by turn"
curl -i https://class.wize73.com/ops/healthz   # should 200 (unauth liveness)
curl -i https://class.wize73.com/ops/          # should 302 → Cloudflare login
```

Verify:

- [ ] `/healthz` returns 200
- [ ] `/metrics/` contains the "Token flow by turn" marker
- [ ] `/ops/healthz` returns 200 (it's the unauth liveness probe)
- [ ] `/ops/` redirects to Cloudflare Access login
- [ ] TLS cert valid: `openssl s_client -connect class.wize73.com:443 < /dev/null | grep "Verify return code"`

### 3. Run the full smoke test (3 min)

```bash
bash scripts/e2e-smoke.sh
```

Verify:

- [ ] All 5 categories pass with no failures
- [ ] Round-trip chat works (a real POST /chat returns text and the
      ring buffer increments)

If anything fails, fix it now while there's time.

### 4. Walk a fake student PR end-to-end (15 min)

Use a second GitHub account if you have one (or just use your own and
follow the loop):

```bash
git checkout -b feature/dry-run-test
echo "# Dry run test persona" > app/personas/dry-run.yaml
git add app/personas/dry-run.yaml
git commit -m "feat: add dry-run test persona for pre-class smoke test"
git push -u origin feature/dry-run-test
gh pr create --fill --base main
```

Verify on the PR page:

- [ ] All 9 PR agents start running within 60 seconds of the push
- [ ] All 9 finish within 150 seconds (look at the timestamps)
- [ ] Each agent posts a check status to the PR
- [ ] No required check fails

Then click **Merge** and watch the deploy:

- [ ] `deploy on main` workflow starts immediately after merge
- [ ] `build-and-push` job completes in <2 minutes
- [ ] `deploy-to-slim` job completes in <1 minute
- [ ] `class.wize73.com/healthz` continues returning 200 throughout

### 5. Test the rollback (5 min)

```bash
ssh james@slim 'sudo /opt/wize73/rollback.sh --list'
ssh james@slim 'sudo /opt/wize73/rollback.sh'   # roll to :previous
curl -i https://class.wize73.com/healthz       # should still be 200
ssh james@slim 'docker inspect wize73-app --format "{{.Config.Image}}"'
# Should now be the :previous tag

# Roll forward again to the latest:
ssh james@slim 'sudo /opt/wize73/deploy.sh <latest-sha>'
```

Verify:

- [ ] `--list` shows multiple tags (at least :latest and :previous)
- [ ] Rollback completes in <30 seconds
- [ ] Public URL serves the rolled-back image
- [ ] Roll-forward also works

### 6. Test the kill switches (5 min)

Open `https://class.wize73.com/ops/` in a browser (Cloudflare Access
will gate it to your email).

- [ ] Click "Pause agent inference proxy" — verify the switch shows
      ACTIVE in the state panel
- [ ] Open a new PR and verify the LLM-based agents return a 503
      from the proxy (or a "skipped" notice if proxy is set to
      degrade gracefully)
- [ ] Click "Pause agent inference proxy" again to unpause
- [ ] Click "Reload firewall" — verify the action is logged in the
      events feed (one-shot trigger)

### 7. Pre-warm guapo (3 min)

The first audio call after a guapo restart pays a ~30s cold-start. Do
this once now so the first class call is fast:

```bash
# Tiny TTS call to warm whisper + xtts
curl -s --max-time 60 -X POST http://192.168.1.103:8000/v1/audio/speech \
    -H 'Content-Type: application/json' \
    -d '{"input":"warmup","voice":"alloy"}' \
    -o /tmp/warmup.wav

# Tiny STT call
curl -s --max-time 30 -X POST http://192.168.1.103:8000/v1/audio/transcriptions \
    -F "file=@/tmp/warmup.wav" \
    -F "model=large-v3-turbo"

rm /tmp/warmup.wav
```

Verify:

- [ ] Both calls return successfully
- [ ] guapo's `/healthz` shows `whisper_loaded:true` and `tts_loaded:true`

### 8. Tear down dry-run artifacts (2 min)

```bash
# Delete the dry-run PR's persona
git checkout main
git pull origin main
git checkout -b chore/cleanup-dry-run
rm app/personas/dry-run.yaml
git add app/personas/dry-run.yaml
git commit -m "chore: remove dry-run test persona"
git push -u origin chore/cleanup-dry-run
gh pr create --fill --base main
# Walk it through the agents and merge
```

You don't have to do this — the dry-run persona doesn't hurt anything
in production. But it's tidy.

### 9. Final state check (2 min)

```bash
gh issue list -R wize73-ai/slim --label starter-task
```

Verify:

- [ ] At least 16 starter issues exist (run `bash .github/scripts/create-starter-issues.sh`
      if not — see [.github/SETUP.md](.github/SETUP.md))
- [ ] Each is tagged with a difficulty (easy / medium / hard)
- [ ] Issues link back to the wiki Feature Backlog page

---

## T-30min: final go/no-go

**Goal:** verify nothing has changed since T-24h. If anything has,
investigate before students arrive.

### 1. Quick smoke test (1 min)

```bash
bash scripts/e2e-smoke.sh --quick
```

- [ ] Public surface checks pass
- [ ] Repo configuration checks pass
- [ ] (Quick mode skips the round-trip chat — that's OK at this stage)

### 2. Slim quick check (1 min)

```bash
ssh james@slim 'docker ps && tailscale status | head -3'
```

- [ ] All containers still running
- [ ] Tailscale still connected

### 3. Open the ops dashboard (2 min)

Open `https://class.wize73.com/ops/` in a browser tab and leave it
open for the duration of class.

- [ ] Cloudflare Access lets you in
- [ ] Live event feed loads
- [ ] Switch state panel shows all 4 switches as inactive

### 4. Open a Claude Code session for co-monitoring (2 min)

Start a Claude Code session on your laptop. Verify Claude can read
the ops events stream:

```bash
curl -s -H "Authorization: Bearer $OPS_BEARER_TOKEN" \
    https://class.wize73.com/ops/events.json | head -20
```

- [ ] Claude can curl `/ops/events.json` with the bearer token
- [ ] Stream returns valid JSON

### 5. Ready signal

If everything above is green, you're ready for class. Open the
following tabs in your browser and put them on a single screen:

1. `https://class.wize73.com/` — the chatbot
2. `https://class.wize73.com/metrics/` — what students will see
3. `https://class.wize73.com/ops/` — your live dashboard
4. `https://github.com/wize73-ai/slim/pulls` — the PR queue
5. `https://github.com/wize73-ai/slim/actions` — the CI runs

You're good. See you on the other side.

---

## During-class quick reference

When something goes wrong mid-class, in priority order:

1. **Look at the ops dashboard first.** It shows you what just happened.
2. **For a broken PR**: read the agent comments, ping the student in
   the PR thread, run `./scripts/explain-failure.sh <agent>` for them.
3. **For a broken deploy**: auto-rollback usually fires within 30s.
   If it doesn't, ssh james@slim and run
   `sudo /opt/wize73/rollback.sh`.
4. **For guapo starvation**: flip the "Pause agent inference proxy"
   kill switch on the ops dashboard. Student traffic gets priority,
   CI agents return 503 until you unflip.
5. **For an apparent malicious PR**: don't panic. The defenses keep
   going past the agent gate. Read the agent's comment, check the
   security-review issue it auto-created, talk to the student.

The most likely fire is a PR that fails an agent in a way the student
doesn't understand. The PR comment plus
`./scripts/explain-failure.sh` usually solves it. If not, you and
Claude tag-team it from the ops dashboard.

---

## Backup plans

**If guapo is unreachable**: the chatbot returns 503 to all chat
calls. The metrics tab still works. Students can still iterate on UI
and prompts; only the actual chat completions are affected. The
deploy box itself is fine.

**If Cloudflare is having an outage**: students can't reach the
public URL. Direct LAN access via `http://slim:8080` still works for
anyone on your network. Tell students to focus on local Codespaces
work until Cloudflare is back.

**If GitHub is down**: PRs can't run agents and merges can't deploy.
Students can still work in their Codespaces locally and run
`./scripts/preflight.sh` for feedback. Queue up the PRs for when
GitHub comes back.

**If slim falls over**: spin up a backup container ANYWHERE that can
reach guapo. Pull `ghcr.io/wize73-ai/slim/app:latest`, point at
guapo via `OPENAI_BASE_URL`, expose on port 8080, point cloudflared
at the new host. ~5 minutes from "slim is dead" to "back online" if
you've practiced.

**If the whole thing is on fire**: defer the live deploy portion of
the class. The local Codespaces + preflight loop works without any
server infrastructure. Students can still iterate, just without the
"watch your change go live" payoff. Reschedule the live deploy
session for the following week.
