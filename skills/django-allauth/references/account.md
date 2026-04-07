# Django-Allauth Regular Accounts

Use this file for signup, login, logout, password reset, email verification, email management, phone support, decorators, forms, signals, adapters, and account-specific settings.

## Owns

- Account configuration and rate limits
- Signup/login/logout/password reset/email confirmation/email management flows
- Forms, views, decorators, signals, email behavior, phone support, adapter hooks, and advanced usage

## Boundary Rules

- Prefer existing account extension points before overriding built-in views.
- When the question is about collecting extra signup fields, start with forms and adapters, not view replacement.
- Keep email verification behavior explicit; do not talk about signup customization as if verification were irrelevant.
- Treat account enumeration prevention and rate limits as first-class behavior, not optional trivia.

## Read This First For

- "How do I customize signup/login?"
- "Where do I plug into email verification or password reset?"
- "Should I change a form, adapter, signal, template, or setting?"

## Routing

- Social provider login or account linking -> `references/socialaccount-core.md`
- Shared templates/messages/email delivery -> `references/common-customization.md`
- Broken confirmation links or failing tests -> `references/testing-and-troubleshooting.md`
