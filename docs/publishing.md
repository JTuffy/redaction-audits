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

## The update pipeline

`uv run redaction deploy` is the one command for an update: it redraws the figures, regenerates the paper's tables and compiles it, rebuilds the private site, then builds and lints the public profile. Every recorded run (`p1 run`, `p1 ablate`) does the site part of this by itself.

The public build is made and linted on every update even while nothing is published, so a private detail that slips into the notes fails the day it is written, not the day of the first publish. It is pushed only with `--push` or with `REDACTION_PUBLISH_ON_UPDATE=true` in `.env`; that one setting is the switch that turns on automatic public deploys.

```
uv run redaction deploy              # everything; public build linted, not pushed
uv run redaction deploy --push       # same, and push the public build to the target
uv run redaction publish [--push]    # only the public build
```

## Targets

`REDACTION_PUBLIC_TARGET` picks where the public build goes.

- **`pages`** (default): a separate public GitHub repo holding only the built site, with Pages on. Set `REDACTION_PUBLIC_REPO` to its HTTPS URL. A separate repo keeps the research repo private and needs no paid plan.
- **`firebase`**: Firebase Hosting, Google's static host. Set `REDACTION_FIREBASE_PROJECT` to a Firebase project id and run `npx firebase-tools login` once on this PC. The deploy runs the Firebase CLI through `npx`, so nothing is added to the repo.

## Google Sites

Google Sites has no API for writing pages, so it can't be a step in the pipeline. It is a one-time manual setup: a new Site with one page holding a full-width **Embed → By URL** block pointing at the Pages or Firebase URL. Every push then updates what the Site shows, with no further work. Limits: the embed is an iframe, so links into the site (`#/runs/…`) don't show in the Site's address bar, and some readers will see Google's frame around it; sharing the hosting URL directly gives working links.

To switch on, in order: get the mentor's go-ahead (above); create the target; set the two settings; run `uv run redaction deploy --push` once and check the result; embed the URL in the Site; then set `REDACTION_PUBLISH_ON_UPDATE=true`.
