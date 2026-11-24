# Setting up the site

Done once by the owner. Until the last step, the build workflow skips every job (ADR 0008).

1. **Cloudflare Pages project.** Workers & Pages → Create → Pages → **Upload assets** (Direct Upload).
   Name it `slope-extracts`, production branch `main`. The first upload can be any placeholder file.
   Leave out `manifest.json`: the first run sees no manifest and builds from scratch.
2. **Custom domain.** In the project's Custom domains, add `slope.timzander.com`.
3. **API token.** My Profile → API Tokens → Create Token → Custom token with one permission,
   **Account → Cloudflare Pages → Edit**, on this account. Copy the token. Copy the **Account ID** too
   (Workers & Pages overview, right-hand side).
4. **GitHub Environment.** In this repository: Settings → Environments → New environment
   `pages-production`. Set Deployment branches to **Selected branches**, `main` only, with no required
   reviewers. Add the environment secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
5. **Turn building on.** Settings → Secrets and variables → Actions → Variables → New repository
   variable `BUILD_ENABLED` = `true`. Then Actions → build → Run workflow to start the Colorado
   backfill, or wait for the next 3-hourly run.

To pause the pipeline later, set `BUILD_ENABLED` to anything else.
