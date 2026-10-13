# Operator steps (nothing here was run by the build worker)

Source: `docs/learning-center/deploy.md` section 9 of the orchestrator repository, adapted to this repository. Prerequisites: `gh`
logged in (`gh auth status`; confirm `karthik446` is the GitHub login), a Cloudflare account, Node for `npx`.

## 1. Create the GitHub repository and push

```sh
cd /Users/kar/orca/workspaces/gigai/scout.edgelab.one
gh repo create karthik446/scout-learning-center --public --source . --push --description "Scout site and learning center: public lessons and practice paths, static, no tracking"
```

## 2. Create the Cloudflare Pages project and the API token

Create the project with wrangler only (done on 2026-10-13: the dashboard's **Create > Upload assets** path now creates a
Worker on workers.dev, not a Pages project, so the dashboard route is out):

```sh
npx -y wrangler login
npx -y wrangler pages project create scout-edgelab --production-branch main
```

The token: an **account-owned** token (dashboard > the account > **Manage Account** > **Account API Tokens**, or My Profile >
API Tokens with the account scoped) with the single permission **Account > Cloudflare Pages > Edit**; verify it with
`curl -s -H "Authorization: Bearer $TOKEN" https://api.cloudflare.com/client/v4/accounts/<account id>/tokens/verify`
before storing it. The account ID is on the Workers & Pages overview page, right column. Leave **Web Analytics** off in the
project's Metrics tab (turning it on injects a beacon).

## 3. The two repository secrets

```sh
cd /Users/kar/orca/workspaces/gigai/scout.edgelab.one
printf %s "$TOKEN" | gh secret set CLOUDFLARE_API_TOKEN          # printf %s: no trailing newline or stray character (a pasted value once failed with code 6111)
printf %s "$ACCOUNT_ID" | gh secret set CLOUDFLARE_ACCOUNT_ID
gh api -X PUT repos/karthik446/scout-learning-center/environments/production    # the deploy job uses environment "production"
```

## 4. First deploy

The push of step 1 starts `.github/workflows/deploy.yml` (job `check`, then job `deploy`).

```sh
gh run watch
curl -sI https://scout-edgelab.pages.dev/ | grep -i -E 'content-security-policy|referrer-policy|permissions-policy|x-content-type-options|x-frame-options|set-cookie'
```

## 5. The custom domain, then DNS (in this order)

1. Cloudflare dashboard: project `scout-edgelab` > **Custom domains** > **Set up a custom domain** > `scout.edgelab.one` > **Continue**.
   Do this before DNS: a CNAME without it answers 522.
2. netcup Customer Control Panel > **Domains** > magnifying glass next to `edgelab.one` > **DNS** tab > new row, then **Save DNS Records**:

   | Host | Type | Destination |
   |---|---|---|
   | `scout` | `CNAME` | `scout-edgelab.pages.dev` |

   No trailing dot on the destination: netcup rejects `scout-edgelab.pages.dev.`.

   Expect about 10 minutes. The zone also has a wildcard A record (`*.edgelab.one` -> 152.53.54.202); the explicit CNAME takes precedence. If the
   panel refuses a CNAME beside the wildcard, delete the wildcard and add explicit records for the names the cluster serves.
3. The domain turns **Active** in the Cloudflare dialog once the CNAME is seen and the certificate is issued.

## 6. Verify

```sh
dig scout.edgelab.one CNAME +short            # scout-edgelab.pages.dev.
dig scout.edgelab.one A +short                # Cloudflare addresses, no longer 152.53.54.202
curl -sI https://scout.edgelab.one/ | grep -i -E 'HTTP/|content-security-policy|referrer-policy|permissions-policy|x-content-type-options|x-frame-options|strict-transport|set-cookie'
curl -s -o /dev/null -w '%{http_code}\n' https://scout.edgelab.one/no-such-page/   # 404
curl -s https://scout.edgelab.one/robots.txt; curl -s https://scout.edgelab.one/sitemap.xml | head -5
lychee --no-progress https://scout.edgelab.one/
curl -sI https://scout.edgelab.one/_assets/site.css | grep -i cache-control        # expect: public, max-age=86400 (see "Fixed before the first deploy")
```

The request-log proof of one host: `python3 tools/chrome_check.py --base https://scout.edgelab.one --out /tmp/verify` and read
`netlog_hosts_page_initiated` in `chrome-summary.json` (expected: only `scout.edgelab.one`).

## 7. Rollback

- A bad deploy: Cloudflare dashboard > the project > **Deployments** > the previous production deployment > **Rollback**; or
  `git revert <sha> && git push` (redeploys through the gate).
- The DNS step: delete the `scout` CNAME row at netcup and save; the wildcard takes over again within about 10 minutes. Remove the custom
  domain from the Pages project too.
- Everything: delete the Pages project (Settings > Delete project), revoke the API token, keep the repository.

## Fixed before the first deploy

- `static/_headers` detaches `Cache-Control` under `/_assets/*` and `/learn/pagefind/*` (`! Cache-Control`, then one day), so Cloudflare does not join the `/*` value with the path value, and the unhashed assets are no longer marked `immutable` for a year (commit aa0029e). After the first deploy, `curl -sI https://scout.edgelab.one/_assets/site.css | grep -i cache-control` should show exactly `public, max-age=86400`.
