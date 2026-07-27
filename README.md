# creator-skill

`creator-skill` is a local-first CLI orchestrator that turns a public TikTok
profile into a portable [Agent Skill](https://agentskills.io/specification).
It deliberately delegates the hard work to existing tools:

- `yt-dlp` discovers public videos.
- `summarizer` from
  [martinopiaggi/summarize](https://github.com/martinopiaggi/summarize)
  transcribes video and produces Markdown.
- [OpenKB](https://github.com/VectifyAI/OpenKB) compiles the knowledge and
  generates/evaluates the skill.
- OpenAI's official `quick_validate.py` performs an additional structural
  validation.
- Anthropic's skill tooling is used for evaluation/packaging when installed.

No frontend, scraper, transcription engine, vector database, or proprietary
skill format is included.

## Current status

This first delivery implements the complete orchestration layer, resumable
state, deterministic Markdown conversion, ZIP/`.skill` exports, subprocess
auditing, and an offline end-to-end test using three local video-result
fixtures. Production execution needs the external tools and provider
credentials reported by `creator-skill doctor`.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
pip install yt-dlp martino-summarize openkb
```

OpenKB needs an LLM provider configured according to its documentation.
`ffmpeg` is required by `summarizer`.

## Commands

```bash
creator-skill doctor
creator-skill discover --profile "https://www.tiktok.com/@creator"
creator-skill build \
  --profile "https://www.tiktok.com/@creator" \
  --name creator-expert \
  --intent "Aplicar el conocimiento documentado del creador" \
  --max-videos 20 \
  --batch-size 10
creator-skill resume --project creator-expert
creator-skill update --project creator-expert
creator-skill validate --project creator-expert
creator-skill eval --project creator-expert
creator-skill export --project creator-expert
creator-skill status --project creator-expert
```

Use `--workspace-root PATH` on any command to store projects somewhere other
than `./workspaces`. Use `creator-skill build --fixture-dir tests/fixtures/videos`
for the deterministic offline demonstration.

## Project layout

Each project is isolated below the workspace root:

```text
workspaces/creator-expert/
├── project.json
├── profile.json
├── state.json
├── raw-results/
├── sources/
├── kb/
│   ├── wiki/
│   └── output/skills/creator-expert/
├── exports/
└── reports/
```

Every external command is recorded in `reports/commands.jsonl`. State writes
are atomic. A source hash prevents duplicate processing; `update` rediscovers
the profile and schedules only new or changed entries.

## External command contracts

The adapters invoke these public CLIs:

```text
yt-dlp --flat-playlist --dump-single-json PROFILE_URL
summarizer --source URL... --output-dir RAW_RESULTS --output-format json
openkb init
openkb add SOURCES_DIR
openkb skill new NAME INTENT
openkb skill validate NAME
openkb skill eval NAME
python quick_validate.py SKILL_DIR
python package_skill.py SKILL_DIR EXPORT_DIR   # when discovered
```

The summarize adapter enables its documented persistent transcript cache and
reads the cached transcript text. The upstream cache currently stores plain
text, not word-level timestamps, so the adapter never invents timing data:
timestamp precision is retained when the upstream/fixture result provides
segments, otherwise the full transcript is cited as one video-level segment.

Because external projects evolve, executable names and validator paths can be
overridden with environment variables:

```text
CREATOR_SKILL_YTDLP
CREATOR_SKILL_SUMMARIZER
CREATOR_SKILL_OPENKB
CREATOR_SKILL_OPENAI_VALIDATOR
CREATOR_SKILL_ANTHROPIC_PACKAGER
```

## Tests

```bash
pytest
```

The suite never accesses TikTok or the network. It covers URL normalization,
yt-dlp JSON variants, batching, state resumption, deduplication, Markdown,
subprocess failures, strict skill validation, export, update behavior, and a
three-video end-to-end orchestration test.

## Licensing

This repository is MIT licensed and does not vendor third-party code. External
tools keep their own licenses. OpenKB is Apache-2.0 and summarize is MIT at the
time of writing. Skills copied or used from `openai/skills` must be checked
individually because their licenses may differ.
