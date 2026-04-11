# Troubleshooting

When something goes wrong. Most failures fall into a few categories.

## Symptom: a PR agent is failing and I don't understand why

```bash
./scripts/explain-failure.sh
```

This reads the failing checks on your current branch's PR via the
`gh` CLI and prints a plain-language explanation of each. If you
know which agent is failing, pass its name directly:

```bash
./scripts/explain-failure.sh code-quality
./scripts/explain-failure.sh red-team
./scripts/explain-failure.sh slop-and-scope
```

If you want to see what each agent does without a failing PR:

```bash
./scripts/explain-failure.sh --list
```

The full reference is in [Agents Reference](05-Agents-Reference).

## Symptom: my changes work locally but the deploy fails

The auto-rollback engages within 30 seconds and the live URL is back
to the previous version. So the immediate user impact is small.

Diagnostic steps:

1. Click **Actions** in the GitHub repo
2. Find the failing `deploy on main` run
3. Click into the failing job (usually `deploy-to-slim`)
4. Read the deploy.sh output — it logs each step

The most common deploy failures are:

- **`/healthz` doesn't respond within 30s**: your changes have a
  startup error. Check `docker logs wize73-app` on slim (instructor).
- **GHCR push fails**: usually a temporary GH problem, retry the
  workflow.
- **Tailscale SSH fails**: the OAuth client may have expired, or
  the ACL may not allow the runner to SSH. Check the Tailscale admin
  console.

## Symptom: the public URL is returning 502

The `cloudflared` tunnel is up but it can't reach the app container
on `localhost:8080`. Either:

- The app container is down (not running, or crashed). Instructor:
  `docker ps` on slim, then `docker logs wize73-app`.
- The auto-rollback fired and the previous container is starting up.
  Wait 30 seconds and refresh.
- Slim itself is down. `tailscale ping slim` from a tailnet device
  to check.

## Symptom: the public URL is returning 503

Either:

- Cloudflare is rate-limiting or having an outage (rare; check
  https://www.cloudflarestatus.com/)
- The app's panic-stop kill switch was flipped from the ops
  dashboard. Instructor: visit `/ops`, check the kill switches panel.

## Symptom: the metrics tab is blank or showing weird data

The most common cause is that no chat turns have happened yet — the
ring buffer starts empty. Have a conversation with the chatbot and
the table will populate.

If the tab itself fails to load:

- Check `/metrics/healthz` directly — it should return 200 with a
  buffer size.
- Check the slim host stats panel — if it shows "sidecar
  unavailable", the stats sidecar container is down.
- Check the guapo panel — if it shows red, the indirect provider
  can't reach guapo's `/healthz`.

The metrics tab is mounted as a separate FastAPI sub-app, so it
survives even when the main chatbot router has bugs. If `/metrics/`
is broken, something's wrong with the locked core itself — file an
issue tagged `metrics-broken` and tag the instructor.

## Symptom: I want to roll back to a specific commit

The instructor has `/opt/wize73/rollback.sh` on slim:

```bash
ssh james@slim 'sudo /opt/wize73/rollback.sh --list'   # show available tags
ssh james@slim 'sudo /opt/wize73/rollback.sh sha-abc123'   # roll to that SHA
ssh james@slim 'sudo /opt/wize73/rollback.sh'              # roll to :previous
```

Up to the last 5 SHA tags are kept on slim for arbitrary rollback.

## Symptom: I broke main with a merge

The auto-rollback already engaged if the deploy failed health check.
If the deploy succeeded but the chatbot is *behaviorally* broken
(works at /healthz but is producing wrong output), use the manual
rollback above.

Then open a follow-up PR that fixes forward. **Don't try to revert
the merge with `git revert`** — it complicates linear history. Just
fix the bug in a new PR.

## Symptom: my agent inference proxy is rate-limited

You'll see this on PR comments as `429 too many calls`. The proxy
has both per-PR and global rate limits to prevent CI from starving
guapo of capacity for live student traffic.

Wait a minute and re-run the workflow. If you keep hitting the limit
on a single PR, you're probably stuck in a loop — pause, fix the
underlying issue, then push again.

## Symptom: the firewall blocked something legitimate

Instructor: check `journalctl -k | grep wize73-drop` on slim to see
exactly what was dropped. The `audit_drops.sh` service forwards drop
events to the ops dashboard event stream as critical-severity events.

If the drop is a false positive, you can either:

- Add the destination to the allow-list in `docker/firewall/rules.nft`
  (CODEOWNERS-protected — needs an instructor PR)
- Temporarily disable the firewall: `sudo nft delete table inet wize73`
  (re-applied at next deploy)

## Symptom: a student PR triggered the malicious-code-review agent

The instructor has been notified via the auto-created
`security-review` issue. Read the agent's PR comment for what
specifically tripped, then:

1. Read the actual diff to understand what the student was doing
2. If it was a false positive, post a comment explaining and
   manually approve
3. If it looks like a deliberate attempt to do something bad, talk
   to the student offline

False positive rate is intentionally high here. Don't be alarmed by
seeing this fire occasionally.

## Symptom: I can't push because branch protection rejects me

If you're trying to push directly to `main`, that's expected — main
is protected. Open a PR instead.

If you're trying to merge a PR but the merge button is disabled:

- All 9 agents must be green
- Branch must be up to date with main (rebase if not)
- All conversations must be resolved
- Code-owner approval required if you touched `core/`, `.github/`,
  `docker/`, or `docs/wiki/`

## Symptom: docker build fails locally but the workflow says it works

You probably don't have `linux/amd64` as the build platform on an
ARM Mac. The Dockerfile pins `--platform=linux/amd64` so it builds
for the right target, but on some setups buildx needs an explicit
hint:

```bash
docker buildx build --platform=linux/amd64 -f docker/app/Dockerfile -t wize73-app:local .
```

## Symptom: my Codespace is slow

The default Codespace machine type is 2 cores. For this project that
should be fine — the heavy work happens on guapo, not in your dev
environment. If a specific operation is slow, it's usually because
mypy is type-checking everything for the first time. Subsequent runs
are cached and much faster.

## Symptom: I have no idea what I'm doing

Read [Your First PR](04-Your-First-PR) and walk through it
literally. By the end you'll have made one successful PR and you'll
know what every step does. Real work starts after that.

If you're stuck on a concept, the [Bidirectional Framing](03-Bidirectional-Framing)
page is the central mental model — most "what is this for" questions
have answers there.

## Last resort

Tag the instructor in your PR description with `@<their-handle>` or
open an issue tagged `help-wanted`. They're monitoring the ops
dashboard during class and will see new events as they happen.
