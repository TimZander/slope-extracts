# Setting up the site

Done once by the owner. Until the last step, the build workflow skips every job (ADR 0008).

1. **Cloudflare Pages project.** Workers & Pages → Create → Pages → **Upload assets** (Direct Upload).
   Name it `slope-extracts`, production branch `main`. Upload a placeholder folder holding a file named
   `404.html` (any content) and no `manifest.json`: the first run then sees no manifest and builds from
   scratch. Without a `404.html`, Pages answers every missing path with 200, and the first run stops
   with "the live manifest is not valid"; see *A placeholder with no 404.html* below.
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

## A placeholder with no 404.html

If the first run stopped with "the live manifest is not valid" because the placeholder had no
`404.html` (ADR 0009):

1. Settings → Secrets and variables → Actions → Variables → New repository variable `FIRST_DEPLOY` =
   `true`.
2. Actions → build → Run workflow. The run reads the placeholder as an empty site and deploys the
   first real one, with its own `404.html`.
3. Check that `https://slope.timzander.com/manifest.json` is the new manifest, then **delete**
   `FIRST_DEPLOY`. It is for one run only.
