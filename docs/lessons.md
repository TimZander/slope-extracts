# Lessons

## A Pages placeholder without a 404.html answers every path (2026-11-24)

The setup said "the first upload can be any placeholder file", and the first run failed: a Cloudflare
Pages project with no `404.html` treats itself as a single-page app and answers every missing path,
`manifest.json` included, with 200 and the placeholder's body. The pipeline was right to refuse it,
but the setup step had never been tried against a real project.

**Do differently:** when a pipeline's correctness rests on how a host answers a missing file, write
the setup step from a test against the real host (`curl -I` a path that doesn't exist), not from what
the host "should" do, and say what the placeholder must contain.
