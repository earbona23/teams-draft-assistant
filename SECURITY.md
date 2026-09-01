# Security policy

## Reporting a vulnerability

Open a [private security advisory](https://github.com/earbona23/teams-draft-assistant/security/advisories/new)
on this repository. Please do not open a public issue for a vulnerability.

You will get an acknowledgement within 72 hours and an assessment within seven days. There
is no bounty programme — this is a single-maintainer project — but every report is credited
in the advisory unless you ask me not to.

## What counts as a vulnerability here

`teams-draft-assistant` drafts replies for your Microsoft Teams 1:1 chats. **You review
and send.** It does not auto-reply and it does not impersonate you.

That sentence is the product, and the threat model is built around defending it.

| Class | Why it matters |
|---|---|
| **Anything that sends without you** | A path that dispatches a message without an explicit human action is the most serious bug this project can have. The entire justification for this tool existing is that a person decided, every time. |
| **Anything that impersonates you** | Presenting generated text as authored by you, anywhere, without the review step. |
| **Conversation content leaving the machine unexpectedly** | Chat contents are other people's words, and they never consented to anything. Any transmission beyond what the operator explicitly configured is in scope. |
| **Token or credential mishandling** | An access token written to disk, printed, logged, or included in a crash report. |
| **A scope request wider than the work** | Asking for Graph permission the tool does not need — including any write scope beyond what sending a reviewed message requires. |

## Out of scope

- Draft quality. That is a feature request, not a vulnerability.
- Requests for automatic replies. That is a deliberate design decision and it will not
  change; it is the difference between an assistant and an impersonator.
