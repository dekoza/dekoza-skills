# dekoza-skills

This repository is a collection of curated AI coding skills.
It focuses on Django, HTMX, and Tabler UI.
The goal is simple: share knowledge and good practices while working with AI code assistants.

### Why this exists

I am disillusioned with the current state of AI in coding.
We were promised reasoning, but we received sycophancy.
We were promised efficiency, but we often spend hours fixing "hallucinations" and broken abstractions.
Despite this, some patterns are worth preserving.
These skills encode what actually works in production, not just what looks good in a chat window.

### What is inside

You will find structured skills for:
- [Django](django/SKILL.md): Models, views, and architecture patterns.
- [HTMX](htmx/SKILL.md): Hypermedia-driven interactions.
- [Tabler UI](tabler/SKILL.md): Clean, functional interfaces.

These files are designed to be loaded by agents to guide their execution.

### The AGENTS.md and Anti-Sycophancy

The [AGENTS.md](AGENTS.md) file contains non-negotiable rules for any agent working in this context.
It is not a suggestion.
It is a technical constraint.

The most critical part is the **Hardline Review and Honesty Policy**.
This clause is a countermeasure against the single most dangerous property of AI code assistants: the tendency to agree with the user even when the user is wrong.
I have seen too much code fail because an AI was too "polite" to point out a flaw.
In this repo, disagreement is not a failure.
Unearned agreement is.

### License

This project is licensed under the [LICENSE](LICENSE) (Unlicense).
It is in the public domain.
Use it.
Improve it.
Don't expect it to be a magical solution.
It's just a set of tools for a difficult job.
