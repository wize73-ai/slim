# Repository Setup

One-time configuration steps for the `wize73-ai/slim` repository. Run
these once after the initial commits land. Most of it is automated by
`.github/configure-repo.sh`; the manual parts are flagged.

## Prerequisites

- Repo admin permissions on `wize73-ai/slim`
- `gh` CLI installed and authenticated (`gh auth login`)
- Slim deploy box reachable on Tailscale (see Slim Setup below)
- Cloudflare account with the `wize73.com` zone
- Cloudflare Tunnel `class-wize73` already created and routing
  `class.wize73.com` (this happened in task #2)

## 1. Branch Protection

Run the configure script:

```bash
bash .github/configure-repo.sh --branch-only
```

This applies the following rules to `main`:

- **All 9 PR agent checks must pass**: secrets-scan, code-quality,
  red-team, blue-team, classroom-safety, version-discipline,
  build-and-smoke, slop-and-scope, malicious-code-review.
- **Branch must be up to date** with main before merge.
- **CODEOWNERS approval required** on locked paths (`core/`,
  `.github/`, `docker/`, `docs/wiki/` — see `.github/CODEOWNERS`).
- **Stale reviews dismissed** when new commits are pushed.
- **Linear history** required (no merge commits).
- **Conversation resolution** required (all PR comments must be
  marked resolved before merge).
- **Force pushes disabled**, branch deletion disabled.

Verify:

```bash
gh api repos/wize73-ai/slim/branches/main/protection | jq .
```

## 2. Repository Secrets

Run:

```bash
bash .github/configure-repo.sh --secrets-only
```

You'll be prompted for each secret value. Skipped secrets can be set
later with `gh secret set <NAME> -R wize73-ai/slim`.

| Secret | Used by | How to obtain |
|---|---|---|
| `TAILSCALE_OAUTH_CLIENT_ID` | `deploy-on-main` | Tailscale admin console → Settings → OAuth clients → New client. Scope to `tag:gh-deploy`. |
| `TAILSCALE_OAUTH_SECRET` | `deploy-on-main` | Same screen as above (shown once on creation). |
| `AGENT_PROXY_TOKEN` | LLM-based PR agents (1, 2, 4, 5, 8, 9) | Random 32-char hex (`openssl rand -hex 32`). Same value goes into the agent-proxy container's env on slim. |
| `AGENT_PROXY_URL` | LLM-based PR agents | Optional. Defaults to `https://class.wize73.com/agents-llm`. Set to override. |

`GITHUB_TOKEN` is auto-provisioned by GH Actions for the GHCR push —
no manual setup needed.

## 3. Tailscale ACL — allow gh-deploy to SSH slim

In the Tailscale admin console, edit your tailnet ACL JSON to add:

```json
{
  "tagOwners": {
    "tag:gh-deploy": ["jawarm24@gmail.com"],
    "tag:deploy-slim": ["jawarm24@gmail.com"]
  },
  "ssh": [
    {
      "action": "accept",
      "src":    ["tag:gh-deploy"],
      "dst":    ["tag:deploy-slim"],
      "users":  ["james"]
    }
  ]
}
```

This grants the `tag:gh-deploy` identity (which the OAuth client uses)
SSH access to slim as the `james` user. Tailscale SSH handles auth via
tailnet identity — no SSH key in repo secrets needed.

After updating the ACL, tag slim manually in the admin console UI
(`Devices → slim → Edit tags → tag:deploy-slim`) if it isn't already.

## 4. Cloudflare Access policy on /ops

The `/ops` instructor dashboard must be gated to your email only. In
the Cloudflare dashboard:

1. Go to **Zero Trust → Access → Applications**
2. **Add an application → Self-hosted**
3. Application name: `wize73 ops dashboard`
4. Application domain: `class.wize73.com`
5. Path: `/ops`
6. **Add a policy**: name `instructor only`, action `allow`, include
   `Emails → jawarm24@gmail.com`
7. Save

The chatbot at `class.wize73.com/` and `class.wize73.com/metrics`
should NOT be gated by Access — those are the student-facing surfaces
(metrics is locked but readable). The student email allow-list goes
on the `/` path application.

## 5. (Optional) Cloudflare Access policy for students on /

For the class session, gate the chatbot itself to the 12 student emails:

1. Same flow as above but path `/`
2. Application name: `wize73 chatbot — class`
3. Policy: `class students`, action `allow`, include `Emails →
   <list-of-12-student-emails>`
4. Optionally a second policy `instructor`, action `allow`, include
   your own email so you can also access the student view.

## 6. Slim setup (already done — for reference)

These steps are already complete from task #2. Listed here for
completeness:

- Docker engine + Compose plugin installed
- Tailscale installed and authorized as `slim`
- cloudflared installed and the `class-wize73` tunnel registered
- nftables egress firewall applied (run `bash docker/firewall/setup.sh`
  on slim if not yet)
- `bash docker/deploy/install.sh` run as root to install
  `/opt/wize73/deploy.sh`, `/opt/wize73/rollback.sh`, the compose file,
  and the firewall scripts.

## 7. First deploy

After all of the above is in place, push any change to main and the
`deploy-on-main` workflow will:

1. Build the image
2. Push to GHCR
3. SSH to slim via Tailscale
4. Run `/opt/wize73/deploy.sh <sha>` which does the blue/green swap
5. Verify `https://class.wize73.com/healthz` returns 200

If it fails at step 5, the workflow auto-rolls back to `:previous` and
the workflow exits non-zero. Check the run logs in the GitHub Actions
tab.

## Verification commands

```bash
# Branch protection
gh api repos/wize73-ai/slim/branches/main/protection | jq .

# Required status checks listed
gh api repos/wize73-ai/slim/branches/main/protection \
    --jq '.required_status_checks.checks[].context'

# Repository secrets (names only, values are write-only)
gh secret list -R wize73-ai/slim

# Tailscale device list (run on your local machine)
tailscale status

# Slim is online and reachable
ssh james@slim 'docker ps'

# Public URL is healthy
curl -i https://class.wize73.com/healthz

# Ops dashboard is gated (should redirect to Cloudflare login)
curl -i https://class.wize73.com/ops/healthz
```
