# Django-Allauth Headless

Use this file for `allauth.headless` installation, configuration, documented API surface, CORS, adapters, and token strategies.

## Owning Surface

- `allauth.headless` owns SPA, mobile, and API-first authentication guidance.
- Do not answer these questions with only server-rendered account-view advice.

## Token Strategies

### Session Tokens

- For non-browser contexts, allauth uses the `X-Session-Token` request header to track authentication state.
- The docs recommend reusing `X-Session-Token` for your own API as the simplest path if you do not need another strategy.
- Documented integrations exist for Django Ninja and Django REST framework.

### JWT Tokens

- The user still sends `X-Session-Token` until they become fully authenticated.
- Once fully authenticated, the response includes an access-token and refresh-token pair in `meta`.
- Important settings include `HEADLESS_JWT_ALGORITHM`, `HEADLESS_JWT_PRIVATE_KEY`, `HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN`, `HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN`, `HEADLESS_JWT_AUTHORIZATION_HEADER_SCHEME`, `HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED`, and `HEADLESS_JWT_ROTATE_REFRESH_TOKEN`.
- JWT is not truly stateless when you need logout to invalidate outstanding access tokens; the docs say state is still required in that case.

## Boundary Rules

- Keep CORS explicit for SPA/mobile setups.
- Distinguish browser session auth from headless session-token auth.
- Distinguish session-token and JWT-token strategies explicitly.
- Release notes matter here because `HEADLESS_CLIENTS`, spec serving, and JWT support changed recently.

## Routing

- Server-rendered signup/login/email flows -> `references/account.md`
- DRF architecture outside documented allauth headless support -> pair `drf`
- Release-sensitive token strategy behavior -> `references/version-notes.md`
