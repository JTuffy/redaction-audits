# Publishing the site

The site has two builds.

- **Private** (`redaction site`): everything, served on the tailnet. This is the working space.
- **Public** (`redaction site --public`): what may be shown outside. It drops the Questions page
  and the Inspect transcripts, never includes the test split, replaces names with roles, and drops
  any notes line marked `<!-- private -->`. A lint then fails the build on anything that still
  looks private: names, amounts of money, local paths, hostnames, e-mail addresses, key-shaped
  strings, named third-party data sources.

## Before the first publish

- Ask the mentor. The notes, findings and question summaries on the site are largely written by
  Claude, and the mentor has asked that AI-written text not be sent to other people. A public
  page is that, at scale. Options: publish only data, runs and figures; or rewrite the notes and
  question answers by hand first.
- The repo itself stays private until the paper (Decisions, 2026-10-22). The public site shows
  prompts, blueprints and scenarios, so publishing it releases those early. The test split stays
  sealed either way.
- Create an empty public GitHub repo for the built site only (for example
  `redaction-audits-site`), turn on Pages from its `main` branch, and set
  `REDACTION_PUBLIC_REPO` in `.env` to its HTTPS URL. A separate repo keeps the research repo
  private and needs no paid plan.

## Each publish

```
uv run redaction publish            # builds site-public/, lints it, prints what it would push
uv run redaction publish --push     # same, then commits and pushes to the Pages repo
```

`publish` refuses to push when the lint finds anything. Fix the source (the notes, the direction
file) rather than the output.

## Google Sites

Google Sites has no API for writing pages, so it can't be a step in this pipeline. Set it up once
by hand: a new Site with one page holding a full-width **Embed → By URL** block pointing at the
Pages URL. Every `publish --push` then updates what the Site shows. Limits: the embed is an
iframe, so links into the site (`#/runs/…`) don't show in the Site's address bar; sharing the
Pages URL directly gives readers working links.
