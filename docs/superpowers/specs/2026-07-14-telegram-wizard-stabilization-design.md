# Telegram Wizard Stabilization Design

## Status

Approved on 2026-07-14.

## Objective

Stabilize the uncommitted Telegram wizard refactor before deployment. The
change must prevent stale inline buttons from mutating or executing a newer
wizard, validate Web targets before side effects, deliver dynamic Telegram
output safely, expose only working Crack options, and restore command entry
points as wizard launchers.

## Scope

This design changes `backend/telegram_bot.py` and its offline regression tests.
It also updates the session notes after deployment.

The following are explicitly outside this change:

- John, Hashcat, Rockyou, ZIP, RAR, or document cracking integration.
- A full class-based wizard state-machine rewrite.
- Persistent wizard sessions across bot restarts.
- Modernization of the stale live integration suite in `tests/test_api.py`.
- DNS-resolution and redirect-based SSRF protection beyond the current target
  policy.
- Backward execution compatibility for old unscoped inline callbacks.

## 1. Wizard Sessions

### State

Every wizard starts through one helper that creates a fresh short session ID.
The in-memory state remains keyed by Telegram user ID and has this shape:

```python
user_wizards[uid] = {
    "session_id": "abc123ef",
    "type": "recon",
    "step": "awaiting_depth",
    "chat_id": 123456,
    "created_at": 1784050000.0,
    "target": "example.com",
    "data": {},
}
```

Session IDs use eight hexadecimal characters generated from a cryptographically
secure random source. A new wizard replaces any prior wizard for that user.
The stored `chat_id` prevents a callback from another chat from using the
current session.

Sessions expire 30 minutes after `created_at`. Expiration is checked whenever a
message or callback attempts to continue a wizard. Expired state is removed and
the user receives the same clear expiration response used for stale buttons.

### Callback Format

All new inline wizard buttons use:

```text
w:<session_id>:<wizard_type>:<action>:<value>
```

Examples:

```text
w:abc123ef:recon:type:domain
w:abc123ef:web:depth:normal
w:abc123ef:crack:method:custom
w:abc123ef:recon:back:main
w:abc123ef:recon:cancel:now
```

The format stays below Telegram's 64-byte callback-data limit because each
component is short and every value comes from a fixed allowlist.

The following legacy callback forms are expired and never applied to active
state:

- `wizard:*`
- `depth:*`
- `menu:main`
- `action:cancel`

### Validation

`_validate_wizard_callback()` is the single validation boundary for scoped
callbacks. Before state mutation or execution, it verifies:

1. The user is authorized and within the existing callback rate limit.
2. The callback has exactly the scoped format.
3. An active, non-expired wizard exists for the effective user.
4. The callback session ID matches the active session.
5. The callback chat matches the stored chat.
6. The wizard type and expected step match.
7. The action and value are explicitly allowed for that wizard and step.

A failed check logs the reason, edits the old message with an expiration or
invalid-action response, and leaves any newer active session untouched.

Back, Cancel, type selection, dictionary selection, language selection, and
depth selection all pass through this validation. There are no generic depth,
Back, or Cancel callbacks outside the session model.

### Terminal Actions

A valid terminal action removes its exact session before task submission or
tool I/O. This prevents a double click from creating duplicate work. If the
subsequent operation fails, the failure is logged and audited and the user must
start a new wizard; the consumed state is not restored.

Red initializes a normal session and stores a snapshot of the displayed target.
Execution uses this snapshot rather than re-reading mutable global target state.
Both its scan and unavailable attack path consume the session.

## 2. Web Target Validation

One helper normalizes and validates Web wizard input and returns both the full
normalized URL and its hostname. It performs these checks in order:

1. Strip surrounding whitespace and reject an empty value.
2. Reject input longer than 2,048 characters.
3. Reject internal whitespace and control characters.
4. Add `https://` only when no explicit scheme is present.
5. Accept only HTTP or HTTPS, case-insensitively.
6. Parse safely, catching malformed IPv6 and invalid-port `ValueError` cases.
7. Require a hostname and a valid numeric port when a port is present.
8. Apply the existing URL target policy, including private literal IP checks.
9. Apply existing hostname/domain validation to the parsed hostname.

Message handling validates before changing the wizard target or step. The Web
executor repeats the same validation before persisting a target, writing a
success audit record, or submitting a task. This provides defense in depth for
tampered or stale in-memory state.

Recon Web submits only the validated hostname to its recon playbook. Web Audit
submits the normalized full URL. The unavailable brute-force path performs no
target persistence and submits no substitute playbook.

Invalid input keeps the same active session and step so the user can retry.

## 3. Telegram Message Delivery

A shared async primitive accepts a bound Telegram send/edit method, text, and
keyword arguments. Thin wrappers support:

- `Message.reply_text()`
- `Message.edit_text()`
- `CallbackQuery.edit_message_text()`

When Telegram raises `BadRequest`, the primitive retries once without
`parse_mode` only if all of the following are true:

- A parse mode was requested.
- The normalized error text says that Telegram cannot parse entities.

The retry preserves all other arguments, including reply markup. The fallback
is logged at warning level. Unrelated errors such as "message is not modified",
"message is too long", or "message cannot be edited" are logged and re-raised.
Generic exceptions are not converted into Markdown fallbacks.

All dynamic Markdown output in the wizard paths, Nmap polling, task output,
payload/crack formatters, and chat responses uses the shared wrappers. This
guarantees delivery after malformed legacy Markdown without hiding unrelated
Telegram failures.

This is a delivery fallback, not a switch to MarkdownV2 and not a promise to
semantically escape every valid Markdown sequence in tool output.

## 4. Crack Wizard

The visible Crack type keyboard contains only Hash. ZIP/RAR and Document remain
hidden until their actual engines are integrated.

After hash input, validation calls the real `hacking.crypto.hash_id()` API,
which returns a list of candidates. Input is accepted only when the first
supported candidate is one of the algorithms currently implemented by
`hash_crack()`:

- MD5
- SHA1
- SHA224
- SHA256
- SHA384
- SHA512

Bcrypt, SHA-Crypt, MySQL, NTLM-only, unknown, and future identifiers are not
presented as crackable. Invalid or unsupported input leaves the user at the hash
input step with a precise retry message.

The dictionary keyboard contains only:

- Integrated dictionary: call `hash_crack(hash_value)`.
- Custom: collect comma- or newline-separated words and call
  `hash_crack(hash_value, words)`.

Rockyou remains hidden until it is installed and wired. Manipulated callbacks
for ZIP, RAR, documents, Rockyou, or an unknown type/method fail closed and
never call `hash_crack()`. The execution boundary also verifies the validated
type snapshot and supported hash before calling the cracking function.

The document handler remains registered so uploads cannot fall through to
another handler, but it does not download files or invoke a cracking tool. It
reports that file cracking is unavailable and leaves any current Hash or
unrelated wizard session unchanged.

## 5. Command Compatibility

The following command handlers are restored as adapters with the standard
`(update, context)` signature. They perform normal authorization/rate-limit
checks and open a fresh wizard rather than executing legacy shortcuts:

| Command | Behavior |
|---|---|
| `/recon` | Open Recon wizard |
| `/webscan` | Open Web wizard |
| `/web` | Open Web wizard alias |
| `/crack` | Open Crack wizard |
| `/payload` | Open Payload wizard |
| `/osint` | Open OSINT wizard |

`/nmap <target>` retains its current direct execution behavior.

## 6. Error And Audit Behavior

- Invalid user input: send a precise error and retain the current step.
- Expired, cross-user, cross-chat, or mismatched callback: log the rejection,
  leave current state unchanged, and mark only the clicked message expired.
- Unsupported operation: submit no task, invoke no substitute tool, and report
  the limitation explicitly.
- Tool or task failure after session consumption: log the exception, write a
  failed audit entry where an operation was attempted, and tell the user to
  restart the wizard.
- Markdown entity error: retry plain text once.
- Other Telegram `BadRequest`: log and propagate.

Existing role checks, callback/message rate limits, target auditing, and tool
allowlists remain in force.

## 7. Test Strategy

Tests are written and observed failing before each production behavior change.
The offline Telegram suite covers:

1. Red creates state, snapshots its target, executes once, and consumes state.
2. A changed global target cannot change an active Red operation.
3. Old cross-type and same-type callbacks cannot affect a newer session.
4. A callback for user A cannot operate on user B's state.
5. Cross-chat, expired-TTL, old Back, and old Cancel callbacks are rejected.
6. Current-session callbacks continue to route selected parameters correctly.
7. Missing/malformed Web hosts, unsupported schemes, whitespace, invalid ports,
   malformed IPv6, overlong URLs, and private literal IPs are rejected without
   side effects.
8. Valid bare hosts and HTTP/HTTPS URLs normalize correctly and reach the right
   playbook target shape.
9. Entity parse errors retry once without Markdown while unrelated
   `BadRequest` instances do not retry.
10. Only supported hash algorithms reach dictionary selection and
    `hash_crack()`.
11. Manipulated Crack types and methods fail closed.
12. Integrated and custom dictionaries pass the intended arguments.
13. All restored commands and media/document handlers are registered.

Verification commands cover the Telegram suite plus the current isolated unit
suites for Kali Server, ToolsEngine, TaskQueue, tools routing, and the Kali
Dockerfile. `tests/test_api.py` is excluded because it is a stale live-server
integration suite: it defaults to the wrong token and still asserts removed
request formats, routes, and workflow names. Its failures predate and are
independent of this Telegram working-tree change.

## 8. Deployment

Deployment occurs only after the targeted and related unit suites pass.

1. Rebuild and recreate only `artenisa-telegram-bot`.
2. Confirm the container is running and remains stable.
3. Inspect startup logs for successful initialization and handler registration.
4. Confirm there is one polling instance and no Telegram conflict errors.
5. Run non-destructive smoke checks for `/start` and command-to-wizard routing
   when Telegram access is available.
6. Update `AGENTS.md` to remove the resolved disk blocker and record exactly
   which code and containers were verified.

The deployment does not expose the future Kali tools that remain outside the
current six-tool API allowlist.

## 9. Files

| File | Change |
|---|---|
| `backend/telegram_bot.py` | Session model, scoped callbacks, validation, safe delivery, command adapters, and wizard fixes |
| `tests/test_telegram_wizards.py` | Offline regression coverage for all approved behavior |
| `AGENTS.md` | Final verified session and deployment state |
