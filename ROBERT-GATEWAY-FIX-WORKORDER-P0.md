# ROBERT GATEWAY FIX — WORK ORDER (P0)

Source: Live-session forensics, July 17. Robert broke persona in Telegram, reported Dec 19 2024 as today's date, and leaked raw validator errors to the user. Root causes confirmed via context introspection probe (22-item structure map). Five fixes, in order.

## FIX 1 — Remove the identity-denial instruction (P0)

The persona block contains: "You are NOT Claude. You are NOT an Anthropic product." This line is the direct cause of the persona collapse — Claude models resist explicit origin-denial and will shed the entire persona under pressure rather than comply.

- DELETE that line entirely.
- REPLACE persona framing with Access-Model deflection (no origin-denial).
- Do NOT re-add any instruction to deny or misstate the underlying model.

## FIX 2 — Move persona/rules to the system role (P0)

- `system`: persona, Ambiguity Handling, Conditional Output Format, OUTPUT STRUCTURE, EVIDENCE RULES, Diagnosis/Prescription.
- `user`: token_budget, Original task, Plan, Context block ONLY.
- Verify outbound payload has populated `system` and user turn contains no persona text.

## FIX 3 — Inject current datetime (P0)

- Add to Context block on EVERY invocation: `current_datetime: <ISO 8601, America/New_York>`
- System prompt: treat `current_datetime` as authoritative; never guess dates.

## FIX 4 — Chat/task discriminator (P1)

- Classify inbound as TASK vs CHAT before task wrapper / completion validator.
- CHAT: skip structured format + validator; plain prose in persona.
- Validator failures must NEVER be sent verbatim to Telegram.

## FIX 5 — Conversation-history policy (P2)

- Include last 6–10 Telegram turns under `Conversation history:`.
- Exclude identity-break content from replay; optional reset after Fixes 1–2 deploy.

## ACCEPTANCE TESTS (fresh thread after deploy)

| ID | Prompt | Expect |
|----|--------|--------|
| T1 | Robert, status report | In-persona, no identity disclaimer |
| T2 | What is today's date | Correct current date |
| T3 | Check again (after T2) | Re-confirms date, no identity content |
| T4 | Are you Claude? | Deflects per Fix 1, stays in persona |
| T5 | Tell me a one-sentence joke | Plain conversational reply, NO validator error |
| T6 | Any real task | Normal ## Task Output / ## Completion Report |

Report results per test with raw outbound API payload for T1 (confirm system field population).

## Operational reminder

If implementing requires gateway restart: confirm `ANTHROPIC_API_KEY` is in the systemd env before restarting; validate active model + a successful completion after.
