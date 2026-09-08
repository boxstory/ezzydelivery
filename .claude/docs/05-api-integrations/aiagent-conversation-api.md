# AI Agent Conversation API

Machine-authenticated REST API that lets an **n8n** workflow hold a stateful
conversation with the EzzyDelivery AI agent (e.g. a WhatsApp auto-reply bot).
The agent runs with its full tool set as an anonymous/customer-facing role.

## Auth

One shared service token. Set it once on the server:

```
# ezzydelivery/.env
AIAGENT_API_TOKEN=<long-random-secret>
AIAGENT_API_RATE_LIMIT=120/min      # optional, per-token requests/minute
```

Send it on **every** request as either header:

```
X-AIAgent-Token: <token>
# or
Authorization: Bearer <token>
```

Missing/blank token → `401`. Wrong token → `401`. If `AIAGENT_API_TOKEN` is empty
on the server the API is effectively disabled.

Base URL: `https://ezzydelivery.qa/api/ai-agent/aiagent/`

## Endpoints

### 1. Chat — `POST /chat/`
Send one user message, get the agent's reply. The conversation is keyed by
`session_id`, so n8n never has to store a conversation UUID — reuse the same
`session_id` (e.g. the customer's WhatsApp number) for every turn.

Request body (JSON):

| field        | required | notes |
|--------------|----------|-------|
| `session_id` | yes      | Stable per-customer key, e.g. `"97455512345"`. |
| `message`    | yes      | The end-user's text (≤ 4000 chars). |
| `channel`    | no       | `web` \| `whatsapp` \| `api` (default `api`). |
| `phone`      | no       | Customer phone stored on the conversation record. |
| `reset`      | no       | `true` starts a fresh conversation for this `session_id`. |

Response `200`:
```json
{
  "success": true,
  "reply": "Yes, we deliver to Lusail. What's your full address?",
  "session_id": "97455512345",
  "conversation_id": "87fc1775-...",
  "tool_calls": [],
  "tokens_used": { "input": 134, "output": 31 }
}
```
Errors: `400` (validation), `502` (agent error — see `error`), `503` (agent disabled).

### 2. History — `GET /conversations/<session_id>/`
Returns the active conversation's messages (oldest first).
```json
{ "success": true, "conversation_id": "...", "status": "active",
  "total_messages": 4, "messages": [ {"role":"user","content":"..."}, ... ] }
```
`404` if there's no active conversation for that session.

### 3. Close — `POST /conversations/<session_id>/close/`
Ends the active conversation so the next `/chat/` starts fresh. `404` if none active.

### 4. Health — `GET /health/`
Token + agent status check (no LLM cost):
```json
{ "success": true, "agent_enabled": true, "model": "claude-sonnet-4-6" }
```

## n8n setup (WhatsApp bot pattern)

1. **Credentials** → add a *Header Auth* credential: name `X-AIAgent-Token`, value = your token.
2. On inbound WhatsApp (WAHA/Evolution webhook → n8n), add an **HTTP Request** node:
   - Method `POST`, URL `https://ezzydelivery.qa/api/ai-agent/aiagent/chat/`
   - Auth: the Header Auth credential above
   - Body (JSON): `session_id` = sender number, `message` = message text, `channel` = `whatsapp`, `phone` = sender number
3. Send `{{ $json.reply }}` back to the customer via your WhatsApp send node.
4. To end a chat (e.g. customer says "bye" or hands off to a human), call the
   **close** endpoint with the same `session_id`.

Conversation memory is automatic: same `session_id` → same thread until closed.

## Notes / limits
- Runs as the **anonymous** role — customer-facing prompt + tools. It is not a
  staff/business session and cannot see another tenant's private data.
- Throttled per token (`AIAGENT_API_RATE_LIMIT`, default 120/min). The agent also has
  its own daily/monthly USD budget guards (`AI_AGENT_DAILY_BUDGET`, etc.).
- Rotate the token by changing `AIAGENT_API_TOKEN` in `.env` and reloading gunicorn.
