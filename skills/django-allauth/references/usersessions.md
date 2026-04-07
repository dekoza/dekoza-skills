# Django-Allauth User Sessions

Use this file for `allauth.usersessions` installation, configuration, signals, adapters, session tracking, and session revocation/listing behavior.

## Owns

- User session tracking and listing behavior
- Session revocation and related adapter or signal hooks
- `usersessions` installation and enablement boundaries

## Boundary Rules

- Do not pretend this functionality exists unless the `usersessions` app is actually enabled.
- Treat session listing/revocation as a `usersessions` question first, not generic middleware theory.

## Read This First For

- "How do I show a user's active sessions?"
- "How do I revoke another session?"
- "Where do `usersessions` adapter or signal customizations belong?"

## Routing

- Core account login/logout behavior -> `references/account.md`
- SPA/mobile/API auth -> `references/headless.md`
- Release-sensitive session behavior -> `references/version-notes.md`
