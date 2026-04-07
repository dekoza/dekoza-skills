# Django-Allauth Headless

Use this file for `allauth.headless` installation, configuration, documented API surface, CORS, adapters, and token strategies.

## Owns

- `allauth.headless` setup and documented API behavior
- Cross-origin and CORS assumptions for SPA/mobile clients
- Headless adapter hooks and token strategy selection

## Boundary Rules

- This is the owning surface for SPA/mobile/API authentication questions.
- Do not answer headless questions with only server-rendered account-view guidance.
- Distinguish session-token and JWT-token strategies explicitly.
- Keep CORS and cross-origin assumptions explicit.

## Read This First For

- "How should an SPA authenticate with django-allauth?"
- "Should this project use a session token strategy or JWT token strategy?"
- "Where do headless adapter and cross-origin settings belong?"

## Routing

- Server-rendered signup/login/email flows -> `references/account.md`
- DRF architecture outside documented allauth headless surface -> pair `drf`
- Release-sensitive headless behavior -> `references/version-notes.md`
