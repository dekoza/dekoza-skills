# Django-Allauth MFA

Use this file for `allauth.mfa` installation, configuration, forms, adapters, WebAuthn-related features, and upgrade notes from older add-ons.

## Owns

- MFA app enablement and configuration boundaries
- MFA form and adapter customization
- WebAuthn, authenticator setup, reauthentication, and migration context from older MFA add-ons

## Boundary Rules

- Do not assume MFA is enabled in projects that use only `account` or `socialaccount`.
- Treat WebAuthn as part of the documented MFA surface, not an unrelated plugin concern.
- Keep legacy `django-allauth-2fa` notes in migration context, not as the primary implementation path.

## Read This First For

- "How do I enable or customize allauth MFA?"
- "Where do MFA form or adapter changes belong?"
- "How does WebAuthn fit into django-allauth MFA?"

## Routing

- Core signup/login/email behavior -> `references/account.md`
- Session listing or revocation -> `references/usersessions.md`
- Release-sensitive MFA behavior -> `references/version-notes.md`
