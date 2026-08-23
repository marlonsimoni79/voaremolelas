# AGENTS.md

## Project
Paragliding weather analyzer web app for Almargem (Portugal). `prompt.md` is the spec and source of truth for requirements — read it first.

## Stack (per spec)
- Python backend with Jinja templates; frontend via AJAX + JavaScript + CSS
- Data sources (scraped third-party pages — markup can change, centralize parsing and treat selectors as fragile):
  - windguru.cz — Almargem wind, direction, conditions
  - https://www.ipma.pt/pt/otempo/obs.sondagens/ — tephigram soundings (thermal ceiling, wind from ground to cloudbase)
- Deployment: Podman with quadlet units; build/deploy steps must be documented in README.md

## Conventions
- Web app serves on localhost port **5555**
- Code, variables, and comments in English
- Clear separation: UI / business logic / data fetching

## Current state
No code, tests, or CI exist yet. There are no build/test/lint commands to run; verify intent against `prompt.md` when in doubt.
