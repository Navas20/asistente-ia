# Telegram Wizard Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize every Telegram wizard with scoped sessions, validated callbacks and inputs, safe message delivery, working command launchers, regression coverage, and a verified container deployment.

**Architecture:** Keep the existing function-based bot and `user_wizards` store. Add a short-lived session envelope and one callback-validation boundary, then preserve that envelope while existing handlers advance state. Pure validators cover Web targets and hashes; one bound-method wrapper handles Telegram Markdown fallback without a global bot object.

**Tech Stack:** Python 3.13, python-telegram-bot 21.9, `unittest.IsolatedAsyncioTestCase`, `unittest.mock`, Docker Compose.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-14-telegram-wizard-stabilization-design.md`.
- Keep wizard state in memory and keyed by Telegram user ID.
- Use an eight-hex-character session ID and a 1,800-second TTL.
- Use callback data `w:<session_id>:<wizard_type>:<action>:<value>` and stay below Telegram's 64-byte limit.
- Reject all legacy wizard callbacks; do not add compatibility execution paths.
- Consume a terminal session before task submission, tool execution, or other external I/O.
- Keep ZIP/RAR, documents, Rockyou, John, Hashcat, advanced SSRF protection, and `tests/test_api.py` modernization out of scope.
- Preserve `/nmap` direct execution and the current six-tool API allowlist.
- Use `unittest`, matching the existing Telegram test module; do not introduce pytest fixtures or pytest-only plugins.
- Do not commit implementation changes unless the user explicitly asks for a commit.
- Do not reset or discard the existing uncommitted wizard refactor.

---

## File Map

- Modify: `backend/telegram_bot.py` - all runtime behavior in this plan.
- Modify: `tests/test_telegram_wizards.py` - offline unit and async regression tests.
- Modify after deployment: `AGENTS.md` - verified state only.
- Reference only: `backend/hacking/crypto.py` - actual `hash_id()` and `hash_crack()` contracts.
- Reference only: `backend/tools_engine.py` - `validate_target()` and `validate_url_target()`.
- Reference only: `docker-compose.yml` - service name and deployment command.

### Shared Test Helpers

The first task extends the existing helpers instead of replacing the test
framework:

```python
def make_text_update(text, uid=7, chat_id=70):
    message = SimpleNamespace(
        text=text,
        chat=SimpleNamespace(id=chat_id),
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=uid, username="tester", full_name="Test User")
    chat = SimpleNamespace(id=chat_id)
    return SimpleNamespace(
        effective_user=user,
        effective_chat=chat,
        message=message,
    )


def make_callback_update(data, uid=7, chat_id=70):
    callback_message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=callback_message,
    )
    user = SimpleNamespace(id=uid, username="tester", full_name="Test User")
    chat = SimpleNamespace(id=chat_id)
    return SimpleNamespace(
        effective_user=user,
        effective_chat=chat,
        callback_query=query,
    ), query
```

---

### Task 1: Session Primitives

**Files:**
- Modify: `backend/telegram_bot.py:1-79`
- Modify: `tests/test_telegram_wizards.py:1-41`

**Interfaces:**
- Produces: `_new_wizard(uid: int, wizard_type: str, chat_id: int, step: str = "select_type", **state) -> dict`
- Produces: `_is_wizard_expired(uid: int, now: float | None = None) -> bool`
- Produces: `_consume_wizard(uid: int, session_id: str) -> dict | None`
- Produces: `_wizard_callback(wizard: dict, action: str, value: str) -> str`

- [ ] **Step 1: Update the shared test helpers and write failing session tests**

Add `import re` to the test module and add these methods to
`TelegramWizardTests`:

```python
def test_new_wizard_has_scoped_metadata(self):
    with patch.object(telegram_bot.secrets, "token_hex", return_value="abc123ef"):
        wizard = telegram_bot._new_wizard(7, "recon", 70)

    self.assertIs(wizard, telegram_bot.user_wizards[7])
    self.assertEqual(wizard["session_id"], "abc123ef")
    self.assertEqual(wizard["type"], "recon")
    self.assertEqual(wizard["step"], "select_type")
    self.assertEqual(wizard["chat_id"], 70)
    self.assertGreater(wizard["created_at"], 0)
    self.assertEqual(wizard["data"], {})

def test_wizard_expires_after_thirty_minutes(self):
    with patch.object(telegram_bot.time, "time", return_value=1000.0):
        telegram_bot._new_wizard(7, "recon", 70)

    self.assertFalse(telegram_bot._is_wizard_expired(7, now=2799.0))
    self.assertTrue(telegram_bot._is_wizard_expired(7, now=2801.0))
    self.assertNotIn(7, telegram_bot.user_wizards)

def test_consume_requires_exact_session(self):
    wizard = telegram_bot._new_wizard(7, "web", 70)

    self.assertIsNone(telegram_bot._consume_wizard(7, "stale000"))
    self.assertIs(wizard, telegram_bot.user_wizards[7])
    self.assertIs(wizard, telegram_bot._consume_wizard(7, wizard["session_id"]))
    self.assertNotIn(7, telegram_bot.user_wizards)

def test_wizard_callback_is_compact_and_scoped(self):
    wizard = telegram_bot._new_wizard(7, "payload", 70)
    data = telegram_bot._wizard_callback(wizard, "lang", "powershell")

    self.assertRegex(data, r"^w:[0-9a-f]{8}:payload:lang:powershell$")
    self.assertLessEqual(len(data.encode("utf-8")), 64)
```

- [ ] **Step 2: Run the four tests and verify RED**

Run:

```powershell
python -m unittest tests.test_telegram_wizards.TelegramWizardTests.test_new_wizard_has_scoped_metadata tests.test_telegram_wizards.TelegramWizardTests.test_wizard_expires_after_thirty_minutes tests.test_telegram_wizards.TelegramWizardTests.test_consume_requires_exact_session tests.test_telegram_wizards.TelegramWizardTests.test_wizard_callback_is_compact_and_scoped -v
```

Expected: errors because the new helpers and imports do not exist.

- [ ] **Step 3: Implement the minimal session primitives**

Add `import secrets` and `import time` near the top of `telegram_bot.py`, then
add this code after `user_wizards`:

```python
WIZARD_TTL_SECONDS = 30 * 60


def _new_wizard(uid, wizard_type, chat_id, step="select_type", **state):
    wizard = {
        "session_id": secrets.token_hex(4),
        "type": wizard_type,
        "step": step,
        "chat_id": chat_id,
        "created_at": time.time(),
        "target": None,
        "data": {},
    }
    wizard.update(state)
    user_wizards[uid] = wizard
    log.info(
        "Wizard session created: user=%s type=%s session=%s",
        uid,
        wizard_type,
        wizard["session_id"],
    )
    return wizard


def _is_wizard_expired(uid, now=None):
    wizard = user_wizards.get(uid)
    if not wizard:
        return False
    current_time = time.time() if now is None else now
    if current_time - wizard.get("created_at", 0) <= WIZARD_TTL_SECONDS:
        return False
    user_wizards.pop(uid, None)
    log.info("Wizard session expired: user=%s", uid)
    return True


def _consume_wizard(uid, session_id):
    wizard = user_wizards.get(uid)
    if not wizard or wizard.get("session_id") != session_id:
        return None
    return user_wizards.pop(uid)


def _wizard_callback(wizard, action, value):
    callback = (
        f"w:{wizard['session_id']}:{wizard['type']}:{action}:{value}"
    )
    if len(callback.encode("utf-8")) > 64:
        raise ValueError("Telegram callback_data exceeds 64 bytes")
    return callback
```

- [ ] **Step 4: Run the four tests and verify GREEN**

Run the command from Step 2. Expected: four tests pass.

---

### Task 2: Web Target Validation And Execution Boundary

**Files:**
- Modify: `backend/telegram_bot.py` imports, `_execute_web()`, and the Web branch in `handle_text()`
- Modify: `tests/test_telegram_wizards.py`

**Interfaces:**
- Consumes: `_consume_wizard()` from Task 1
- Produces: `_normalize_web_input(value: str) -> tuple[str | None, str | None, str | None]`, ordered as normalized URL, hostname, error
- Changes: `_execute_web(query, uid: int, wizard: dict, depth: str)`

- [ ] **Step 1: Write failing pure-validation tests**

Add:

```python
def test_web_normalization_accepts_valid_targets(self):
    cases = {
        "example.com/login?q=1": ("https://example.com/login?q=1", "example.com"),
        "HTTP://example.com:8080/a": ("http://example.com:8080/a", "example.com"),
    }
    for raw, expected in cases.items():
        with self.subTest(raw=raw):
            normalized, hostname, error = telegram_bot._normalize_web_input(raw)
            self.assertIsNone(error)
            self.assertEqual((normalized, hostname), expected)

def test_web_normalization_rejects_malformed_or_private_targets(self):
    values = [
        "",
        "https://",
        "not a url",
        "ftp://example.com",
        "https://[::1",
        "https://example.com:abc",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "https://example .com",
        "https://" + "a" * 2049,
    ]
    for raw in values:
        with self.subTest(raw=raw):
            normalized, hostname, error = telegram_bot._normalize_web_input(raw)
            self.assertIsNone(normalized)
            self.assertIsNone(hostname)
            self.assertTrue(error)
```

- [ ] **Step 2: Verify the validation tests fail for the missing helper**

Run:

```powershell
python -m unittest tests.test_telegram_wizards.TelegramWizardTests.test_web_normalization_accepts_valid_targets tests.test_telegram_wizards.TelegramWizardTests.test_web_normalization_rejects_malformed_or_private_targets -v
```

Expected: two errors for missing `_normalize_web_input`.

- [ ] **Step 3: Implement the pure Web normalizer**

Add `import re` and import both validators inside the function to retain the
current module-loading pattern:

```python
_EXPLICIT_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _normalize_web_input(value):
    raw = value.strip()
    if not raw:
        return None, None, "La URL no puede estar vacia."
    if len(raw) > 2048:
        return None, None, "La URL supera el limite de 2048 caracteres."
    if any(char.isspace() or ord(char) < 32 for char in raw):
        return None, None, "La URL no puede contener espacios o controles."

    scheme_match = _EXPLICIT_SCHEME_RE.match(raw)
    if scheme_match:
        supplied_scheme = scheme_match.group(0)[:-1].lower()
        if supplied_scheme not in ("http", "https"):
            return None, None, "Solo se permiten URLs HTTP o HTTPS."
    else:
        raw = "https://" + raw

    try:
        parsed = urlparse(raw)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return None, None, "La URL esta malformada."

    if scheme not in ("http", "https") or not hostname:
        return None, None, "La URL debe incluir un hostname valido."

    normalized = parsed._replace(scheme=scheme).geturl()
    from tools_engine import validate_target, validate_url_target

    error = validate_url_target(normalized)
    if error:
        return None, None, error
    error = validate_target(hostname)
    if error:
        return None, None, error
    return normalized, hostname, None
```

- [ ] **Step 4: Verify pure Web tests pass**

Run the command from Step 2. Expected: two tests pass.

- [ ] **Step 5: Write failing side-effect tests for text input and execution**

Add:

```python
async def test_invalid_web_input_keeps_step_and_has_no_side_effects(self):
    update = make_text_update("https://[")
    wizard = telegram_bot._new_wizard(
        7, "web", 70, step="awaiting_target", audit_type="vuln"
    )
    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        patch.object(telegram_bot, "target_engine") as target_engine,
        patch.object(telegram_bot, "task_queue") as task_queue,
    ):
        await telegram_bot.handle_text(update, None)

    self.assertIs(wizard, telegram_bot.user_wizards[7])
    self.assertEqual(wizard["step"], "awaiting_target")
    target_engine.set_target.assert_not_called()
    task_queue.submit.assert_not_called()

async def test_execute_web_revalidates_before_side_effects(self):
    _, query = make_callback_update("unused")
    wizard = telegram_bot._new_wizard(
        7,
        "web",
        70,
        step="awaiting_depth",
        audit_type="vuln",
        target="https://127.0.0.1",
    )
    with (
        patch.object(telegram_bot, "target_engine") as target_engine,
        patch.object(telegram_bot, "task_queue") as task_queue,
    ):
        await telegram_bot._execute_web(query, 7, wizard, "normal")

    self.assertNotIn(7, telegram_bot.user_wizards)
    target_engine.set_target.assert_not_called()
    task_queue.submit.assert_not_called()

async def test_web_brute_has_no_target_or_task_side_effect(self):
    _, query = make_callback_update("unused")
    wizard = telegram_bot._new_wizard(
        7,
        "web",
        70,
        step="awaiting_depth",
        audit_type="brute",
        target="https://example.com/login",
    )
    with (
        patch.object(telegram_bot, "target_engine") as target_engine,
        patch.object(telegram_bot, "task_queue") as task_queue,
    ):
        await telegram_bot._execute_web(query, 7, wizard, "normal")

    self.assertNotIn(7, telegram_bot.user_wizards)
    target_engine.set_target.assert_not_called()
    task_queue.submit.assert_not_called()
    self.assertIn("Hydra", query.edit_message_text.await_args.args[0])
```

- [ ] **Step 6: Run the three side-effect tests and verify RED**

Expected failures: `handle_text()` advances invalid input, and `_execute_web()`
still accepts a URL string rather than a wizard snapshot.

- [ ] **Step 7: Route Web text through the normalizer and revalidate execution**

In the Web `awaiting_target` branch, validate before mutation:

```python
normalized, hostname, error = _normalize_web_input(text)
if error:
    await update.message.reply_text(f"Error: {error}\nIntenta de nuevo.")
    return
wizard.update(
    target=normalized,
    hostname=hostname,
    step="awaiting_depth",
)
await update.message.reply_text(
    f"Objetivo web: `{normalized}`\nProfundidad?",
    parse_mode="Markdown",
    reply_markup=_depth_keyboard(),
)
return
```

Replace `_execute_web()` with a snapshot-based boundary. Do not persist the
unsupported brute path:

```python
async def _execute_web(query, uid, wizard, depth):
    url = wizard.get("target", "")
    audit_type = wizard.get("audit_type", "recon")
    normalized, hostname, error = _normalize_web_input(url)
    consumed = _consume_wizard(uid, wizard.get("session_id", ""))
    if not consumed:
        await query.edit_message_text("Este wizard expiro. Vuelve al menu.")
        return
    if error:
        await query.edit_message_text(f"Error: {error}")
        return
    if audit_type == "brute":
        await query.edit_message_text(
            "Fuerza bruta web estara disponible al integrar Hydra."
        )
        return

    try:
        target_engine.set_target(uid, normalized, "url")
        playbook = "recon_web" if audit_type == "recon" else "web_audit"
        playbook_target = hostname if audit_type == "recon" else normalized
        task_id = task_queue.submit(
            "playbook",
            playbook_target,
            {"playbook": playbook, "depth": depth},
        )
    except Exception as exc:
        audit_log.log(uid, str(uid), "wizard:web", normalized, "error", str(exc))
        await query.edit_message_text(f"Error al iniciar Web: {exc}")
        return

    audit_log.log(
        uid,
        str(uid),
        "wizard:web",
        normalized,
        "ok",
        f"task:{task_id} depth:{depth}",
    )
    await query.edit_message_text(
        f"Web audit iniciado: `{task_id}`\n{normalized}",
        parse_mode="Markdown",
    )
```

Temporarily update the existing legacy depth branch to pass `wizard` instead
of `target`; Task 5 replaces that branch completely. Delete the unused
`_handle_web_url()` so Web input has one validation path.

- [ ] **Step 8: Run all Web tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s tests -p "test_telegram_wizards.py" -k web -v
```

Expected: every test whose name contains `web` passes.

---

### Task 3: Crack Wizard Fail-Closed Behavior

**Files:**
- Modify: `backend/telegram_bot.py` Crack functions, Crack text branches, and document handler
- Modify: `tests/test_telegram_wizards.py`

**Interfaces:**
- Produces: `SUPPORTED_HASH_ALGORITHMS: frozenset[str]`
- Produces: `_validate_hash_algorithm(value: str) -> tuple[str | None, str | None]`, ordered as algorithm and error
- Changes: `_execute_crack(query, uid: int, wizard: dict, method: str, wordlist: list[str] | None = None)`

- [ ] **Step 1: Write failing hash-contract tests against the real API**

```python
def test_hash_validation_uses_real_hash_id_list_contract(self):
    algorithm, error = telegram_bot._validate_hash_algorithm(
        "5d41402abc4b2a76b9719d911017c592"
    )
    self.assertEqual(algorithm, "MD5")
    self.assertIsNone(error)

def test_hash_validation_rejects_identified_but_unimplemented_algorithm(self):
    bcrypt = "$2b12$" + "a" * 53
    algorithm, error = telegram_bot._validate_hash_algorithm(bcrypt)
    self.assertIsNone(algorithm)
    self.assertIn("no soportado", error.lower())

def test_hash_validation_rejects_unknown_input(self):
    algorithm, error = telegram_bot._validate_hash_algorithm("archive.zip")
    self.assertIsNone(algorithm)
    self.assertTrue(error)
```

- [ ] **Step 2: Verify the three tests fail for the missing helper**

Run the three fully-qualified test names. Expected: three errors.

- [ ] **Step 3: Implement the exact hash contract**

```python
SUPPORTED_HASH_ALGORITHMS = frozenset(
    {"MD5", "SHA1", "SHA224", "SHA256", "SHA384", "SHA512"}
)


def _validate_hash_algorithm(value):
    candidates = hacking.crypto.hash_id(value.strip())
    for candidate in candidates:
        algorithm = candidate.get("type", "")
        if algorithm in SUPPORTED_HASH_ALGORITHMS:
            return algorithm, None
    detected = ", ".join(
        candidate.get("type", "desconocido") for candidate in candidates
    )
    return None, (
        f"Algoritmo no soportado: {detected}. "
        "Usa MD5 o SHA1/224/256/384/512."
    )
```

- [ ] **Step 4: Verify the hash-contract tests pass**

Run the command from Step 2. Expected: three tests pass.

- [ ] **Step 5: Write failing Crack routing and consumption tests**

```python
async def test_crack_type_keyboard_exposes_only_hash(self):
    update = make_text_update("unused")
    await telegram_bot._start_crack_wizard(update, 7)
    markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    self.assertIn("Hash", " ".join(labels))
    self.assertNotIn("ZIP", " ".join(labels))
    self.assertNotIn("Documento", " ".join(labels))

async def test_integrated_crack_consumes_session_before_hash_io(self):
    _, query = make_callback_update("unused")
    wizard = telegram_bot._new_wizard(
        7,
        "crack",
        70,
        step="select_dict",
        crack_type="hash",
        target="5d41402abc4b2a76b9719d911017c592",
        algorithm="MD5",
    )

    def crack_after_consume(value):
        self.assertNotIn(7, telegram_bot.user_wizards)
        return {
            "hash": value,
            "identified": [{"type": "MD5"}],
            "cracked": True,
            "plaintext": "hello",
            "algorithm": "MD5",
        }

    with (
        patch.object(
            telegram_bot.hacking.crypto,
            "hash_crack",
            side_effect=crack_after_consume,
        ) as hash_crack,
        patch.object(telegram_bot.audit_log, "log"),
    ):
        await telegram_bot._execute_crack(query, 7, wizard, "integrated")

    hash_crack.assert_called_once_with(wizard["target"])

async def test_document_does_not_mutate_hash_wizard(self):
    update = make_text_update("unused")
    update.message.document = SimpleNamespace(file_name="archive.zip")
    wizard = telegram_bot._new_wizard(
        7, "crack", 70, step="awaiting_value", crack_type="hash"
    )
    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
    ):
        await telegram_bot.handle_document(update, None)

    self.assertIs(wizard, telegram_bot.user_wizards[7])
    hash_crack.assert_not_called()
```

- [ ] **Step 6: Verify these three tests fail for current behavior**

Expected: ZIP/Document labels remain, `_execute_crack` has the old signature,
and document handling consumes file-oriented state incorrectly.

- [ ] **Step 7: Implement Hash-only flow and terminal consumption**

Make these exact behavior changes:

1. `_start_crack_wizard()` calls `_new_wizard(uid, "crack",
   update.effective_chat.id)` and renders only the Hash type option.
2. `_handle_crack_type()` rejects every subtype except `hash` and updates the
   existing state instead of replacing it.
3. The `awaiting_value` text branch calls `_validate_hash_algorithm()` before
   storing `target`, `algorithm`, and `step="select_dict"`.
4. Its dictionary keyboard exposes only `integrated` and `custom`.
5. The custom-word branch validates non-empty words, validates the stored hash
   again, consumes the exact session, then calls
   `hash_crack(hash_value, words)`.
6. `handle_document()` reports that file cracking is unavailable and never
   pops or mutates `user_wizards`.

Replace `_execute_crack()` with:

```python
async def _execute_crack(query, uid, wizard, method, wordlist=None):
    if wizard.get("crack_type") != "hash" or method not in (
        "integrated",
        "custom",
    ):
        await query.edit_message_text("Metodo de crack no permitido.")
        return
    algorithm, error = _validate_hash_algorithm(wizard.get("target", ""))
    if error:
        await query.edit_message_text(error)
        return
    consumed = _consume_wizard(uid, wizard.get("session_id", ""))
    if not consumed:
        await query.edit_message_text("Este wizard expiro. Vuelve al menu.")
        return

    hash_value = consumed["target"]
    status = "error"
    try:
        if wordlist is None:
            result = hacking.crypto.hash_crack(hash_value)
        else:
            result = hacking.crypto.hash_crack(hash_value, wordlist)
        status = "ok" if result.get("cracked") else "fail"
        message = _format_crack(result)
    except Exception as exc:
        message = f"Error: {exc}"
    audit_log.log(uid, str(uid), "wizard:crack", hash_value, status, method)
    await query.edit_message_text(message, parse_mode="Markdown")
```

- [ ] **Step 8: Run all Crack tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s tests -p "test_telegram_wizards.py" -k crack -v
```

Expected: every Crack test passes.

---

### Task 4: Telegram Safe Delivery Primitive

**Files:**
- Modify: `backend/telegram_bot.py:61-69` and dynamic Markdown call sites
- Modify: `tests/test_telegram_wizards.py`

**Interfaces:**
- Produces: `_safe_telegram_call(method, text: str, **kwargs)`
- Produces: `_safe_reply_text(message, text: str, **kwargs)`
- Keeps: `_safe_edit_text(message, text: str, **kwargs)`
- Produces: `_safe_edit_message(query, text: str, **kwargs)`

- [ ] **Step 1: Write failing positive and negative fallback tests**

```python
async def test_safe_delivery_retries_only_entity_parse_errors(self):
    method = AsyncMock(side_effect=[BadRequest("Can't parse entities"), None])
    markup = object()
    await telegram_bot._safe_telegram_call(
        method,
        "bad_markdown",
        parse_mode="Markdown",
        reply_markup=markup,
    )
    self.assertEqual(method.await_count, 2)
    self.assertNotIn("parse_mode", method.await_args_list[1].kwargs)
    self.assertIs(method.await_args_list[1].kwargs["reply_markup"], markup)

async def test_safe_delivery_does_not_retry_unrelated_bad_request(self):
    method = AsyncMock(side_effect=BadRequest("Message is not modified"))
    with self.assertRaises(BadRequest):
        await telegram_bot._safe_telegram_call(
            method, "same", parse_mode="Markdown"
        )
    self.assertEqual(method.await_count, 1)

async def test_safe_delivery_without_parse_mode_does_not_retry(self):
    method = AsyncMock(side_effect=BadRequest("Can't parse entities"))
    with self.assertRaises(BadRequest):
        await telegram_bot._safe_telegram_call(method, "plain")
    self.assertEqual(method.await_count, 1)
```

- [ ] **Step 2: Verify RED**

Run the three test names. Expected: missing `_safe_telegram_call` errors.

- [ ] **Step 3: Implement one bound-method primitive and three adapters**

Replace the old `_safe_edit_text()` implementation with:

```python
def _is_markdown_parse_error(exc):
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "can't parse entities",
            "cannot parse entities",
            "can not parse entities",
        )
    )


async def _safe_telegram_call(method, text, **kwargs):
    try:
        return await method(text, **kwargs)
    except BadRequest as exc:
        if "parse_mode" not in kwargs or not _is_markdown_parse_error(exc):
            log.error("Telegram BadRequest: %s", exc)
            raise
        fallback = dict(kwargs)
        fallback.pop("parse_mode", None)
        log.warning("Telegram Markdown parse failed; retrying as plain text")
        try:
            return await method(text, **fallback)
        except BadRequest as fallback_exc:
            log.error("Telegram plain-text fallback failed: %s", fallback_exc)
            raise


async def _safe_reply_text(message, text, **kwargs):
    return await _safe_telegram_call(message.reply_text, text, **kwargs)


async def _safe_edit_text(message, text, **kwargs):
    return await _safe_telegram_call(message.edit_text, text, **kwargs)


async def _safe_edit_message(query, text, **kwargs):
    return await _safe_telegram_call(query.edit_message_text, text, **kwargs)
```

- [ ] **Step 4: Verify the primitive tests pass**

Run the command from Step 2. Expected: three tests pass.

- [ ] **Step 5: Route every dynamic Markdown call through the adapters**

Replace direct Markdown sends in these functions, preserving text and all
other keyword arguments:

- `_safe_reply_text`: `start`, `objetivo`, `tarea`, `tareas`,
  `nmap_shortcut`, every wizard target confirmation in `handle_text`, Crack and
  Payload text results, `_show_playbooks`, `_send_report`, `_system_status`,
  `_chat_api`, `handle_voice`.
- `_safe_edit_message`: `_execute_recon`, `_execute_web`, `_execute_crack`,
  `_handle_payload_lang`, `_execute_payload`, `_handle_red_type`,
  `_execute_osint`, and callback completion summaries.
- `_safe_edit_text`: every Nmap polling edit.

Remove the broad `except Exception: plain-text retry` inside `_chat_api()`.
Keep HTTP request handling separate from Telegram delivery: catch HTTP/client
errors around the request, then call `_safe_reply_text()` outside that catch.
Remove the silent `except Exception: pass` blocks around Nmap edits; the shared
primitive already logs non-recoverable `BadRequest` errors.

- [ ] **Step 6: Run the Telegram suite**

Run:

```powershell
python -m unittest discover -s tests -p "test_telegram_wizards.py" -v
```

Expected: all tests implemented through Task 4 pass. If a test still asserts a
direct mock call, update it to assert the same text and arguments through the
adapter; do not weaken behavior assertions.

---

### Task 5: Scoped Keyboards, Callback Validation, And Terminal Routing

**Files:**
- Modify: all wizard start/transition functions and `handle_callback()` in `backend/telegram_bot.py`
- Modify: `handle_text()` terminal branches in `backend/telegram_bot.py`
- Modify: `tests/test_telegram_wizards.py`

**Interfaces:**
- Changes: `_wizard_keyboard(wizard: dict, options: list[tuple[str, str, str]])`
- Changes: `_depth_keyboard(wizard: dict)`
- Produces: `_validate_wizard_callback(uid: int, chat_id: int, data: str) -> tuple[dict | None, str | None, str | None, str | None]`
- Produces: `_send_expired_callback(query)`

- [ ] **Step 1: Write failing stale-session and Red tests**

```python
async def test_old_depth_callback_cannot_execute_new_web_wizard(self):
    old = telegram_bot._new_wizard(
        7, "recon", 70, step="awaiting_depth", target="8.8.8.8"
    )
    old_data = telegram_bot._wizard_callback(old, "depth", "normal")
    current = telegram_bot._new_wizard(
        7,
        "web",
        70,
        step="awaiting_depth",
        target="https://example.com",
        audit_type="vuln",
    )
    update, query = make_callback_update(old_data)
    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        patch.object(telegram_bot.task_queue, "submit") as submit,
    ):
        await telegram_bot.handle_callback(update, None)
    submit.assert_not_called()
    self.assertIs(current, telegram_bot.user_wizards[7])
    self.assertIn("expir", query.edit_message_text.await_args.args[0].lower())

async def test_old_back_and_cancel_leave_new_session_untouched(self):
    old = telegram_bot._new_wizard(7, "recon", 70)
    callbacks = [
        telegram_bot._wizard_callback(old, "back", "main"),
        telegram_bot._wizard_callback(old, "cancel", "now"),
    ]
    for data in callbacks:
        current = telegram_bot._new_wizard(7, "osint", 70)
        update, _ = make_callback_update(data)
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)
        self.assertIs(current, telegram_bot.user_wizards[7])

async def test_cross_user_and_cross_chat_callbacks_are_rejected(self):
    wizard = telegram_bot._new_wizard(7, "recon", 70)
    data = telegram_bot._wizard_callback(wizard, "type", "dominio")
    for uid, chat_id in ((8, 70), (7, 71)):
        with self.subTest(uid=uid, chat_id=chat_id):
            update, _ = make_callback_update(data, uid=uid, chat_id=chat_id)
            with (
                patch.object(telegram_bot, "_check_role", return_value=True),
                patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            ):
                await telegram_bot.handle_callback(update, None)
    self.assertIs(wizard, telegram_bot.user_wizards[7])

async def test_red_uses_target_snapshot_and_consumes_before_submit(self):
    update = make_text_update("unused")
    with patch.object(
        telegram_bot.target_engine,
        "get_target",
        return_value={"target": "8.8.8.8", "target_type": "ip"},
    ):
        await telegram_bot._start_red_wizard(update, 7)
    wizard = telegram_bot.user_wizards[7]
    data = telegram_bot._wizard_callback(wizard, "type", "scan")
    callback_update, _ = make_callback_update(data)

    def submit_after_consume(task_type, target, params):
        self.assertNotIn(7, telegram_bot.user_wizards)
        self.assertEqual(target, "8.8.8.8")
        return "ABC123"

    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        patch.object(
            telegram_bot.target_engine,
            "get_target",
            return_value={"target": "1.1.1.1", "target_type": "ip"},
        ),
        patch.object(telegram_bot.task_queue, "submit", side_effect=submit_after_consume),
        patch.object(telegram_bot.audit_log, "log"),
        patch.object(telegram_bot, "_poll_nmap_task", new=Mock(return_value=None)),
        patch.object(asyncio, "create_task"),
    ):
        await telegram_bot.handle_callback(callback_update, None)
```

- [ ] **Step 2: Verify RED**

Run the four test names. Expected: failures because callbacks are still legacy
and Red creates no state.

- [ ] **Step 3: Implement scoped keyboard builders**

```python
def _wizard_keyboard(wizard, options):
    buttons = [
        InlineKeyboardButton(
            label,
            callback_data=_wizard_callback(wizard, action, value),
        )
        for label, action, value in options
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                "Atras",
                callback_data=_wizard_callback(wizard, "back", "main"),
            ),
            InlineKeyboardButton(
                "Cancelar",
                callback_data=_wizard_callback(wizard, "cancel", "now"),
            ),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _depth_keyboard(wizard):
    return _wizard_keyboard(
        wizard,
        [
            ("Rapido", "depth", "rapido"),
            ("Normal", "depth", "normal"),
            ("Profundo", "depth", "profundo"),
        ],
    )
```

Every `_start_*_wizard()` must call `_new_wizard()` with
`update.effective_chat.id`. Every transition helper must call `wizard.update()`
instead of assigning a new dictionary, preserving `session_id`, `chat_id`, and
`created_at`. Convert each option to the `(label, action, value)` shape:

Change `_objetivo_wizard()` to call `_new_wizard(uid, "objetivo",
update.effective_chat.id, step="awaiting_target")` so its text-only state also
receives TTL metadata.

```python
recon = [("Dominio", "type", "dominio"), ("IP", "type", "ip"), ("Rango", "type", "red")]
web = [("Recon", "type", "recon"), ("Vulnerabilidades", "type", "vuln"), ("Fuerza bruta", "type", "brute")]
crack = [("Hash", "type", "hash")]
payload = [("Reverse Shell", "type", "reverse"), ("Meterpreter", "type", "meterp"), ("Webshell", "type", "webshell")]
red = [("Escaneo Red", "type", "scan"), ("Ataque Dirigido", "type", "attack")]
osint = [("Email", "type", "email"), ("Dominio", "type", "domain"), ("Persona", "type", "person")]
```

For Red, create the state with immutable target fields:

```python
target_info = target_engine.get_target(uid)
wizard = _new_wizard(
    uid,
    "red",
    update.effective_chat.id,
    target_snapshot=dict(target_info) if target_info else None,
)
```

- [ ] **Step 4: Implement the centralized allowlist validator**

```python
_CALLBACK_RULES = {
    ("recon", "select_type", "type"): {"dominio", "ip", "red"},
    ("recon", "awaiting_depth", "depth"): {"rapido", "normal", "profundo"},
    ("web", "select_type", "type"): {"recon", "vuln", "brute"},
    ("web", "awaiting_depth", "depth"): {"rapido", "normal", "profundo"},
    ("crack", "select_type", "type"): {"hash"},
    ("crack", "select_dict", "method"): {"integrated", "custom"},
    ("payload", "select_type", "type"): {"reverse", "meterp", "webshell"},
    ("payload", "select_lang", "lang"): {
        "bash", "python", "php", "powershell", "asp", "aspx", "jsp", "py"
    },
    ("red", "select_type", "type"): {"scan", "attack"},
    ("osint", "select_type", "type"): {"email", "domain", "person"},
    ("osint", "awaiting_depth", "depth"): {"rapido", "normal", "profundo"},
}


def _validate_wizard_callback(uid, chat_id, data):
    if not _check_role(uid):
        return None, None, None, "No autorizado"
    rate_limit_error = _rate_limit_msg(uid)
    if rate_limit_error:
        return None, None, None, rate_limit_error
    parts = data.split(":")
    if len(parts) != 5 or parts[0] != "w":
        return None, None, None, "expired"
    _, session_id, wizard_type, action, value = parts
    if _is_wizard_expired(uid):
        return None, None, None, "expired"
    wizard = user_wizards.get(uid)
    if (
        not wizard
        or wizard.get("session_id") != session_id
        or wizard.get("type") != wizard_type
        or wizard.get("chat_id") != chat_id
    ):
        return None, None, None, "expired"
    if action == "back" and value == "main":
        return wizard, action, value, None
    if action == "cancel" and value == "now":
        return wizard, action, value, None
    allowed = _CALLBACK_RULES.get((wizard_type, wizard.get("step"), action))
    if not allowed or value not in allowed:
        return None, None, None, "expired"
    if wizard_type == "payload" and action == "lang":
        language_sets = {
            "reverse": {"bash", "python", "php", "powershell"},
            "meterp": {"bash", "python", "php", "powershell"},
            "webshell": {"php", "asp", "aspx", "jsp", "py"},
        }
        if value not in language_sets.get(wizard.get("payload_type"), set()):
            return None, None, None, "expired"
    return wizard, action, value, None


async def _send_expired_callback(query):
    try:
        await query.edit_message_text(
            "Este boton ya expiro. Abre un nuevo wizard desde el menu."
        )
    except Exception:
        log.warning("Could not mark expired Telegram callback", exc_info=True)
```

- [ ] **Step 5: Replace `handle_callback()` with scoped routing**

The handler must use only the parsed values returned by the validator:

```python
async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    wizard, action, value, error = _validate_wizard_callback(
        uid, chat_id, query.data
    )
    if error:
        if error != "expired":
            await query.edit_message_text(error)
        else:
            await _send_expired_callback(query)
        return

    if action == "back":
        _consume_wizard(uid, wizard["session_id"])
        await query.edit_message_text("Operacion cerrada.")
        await query.message.reply_text("Menu principal:", reply_markup=MAIN_KEYBOARD)
        return
    if action == "cancel":
        _consume_wizard(uid, wizard["session_id"])
        await query.edit_message_text("Operacion cancelada.")
        return

    wizard_type = wizard["type"]
    if action == "type":
        handlers = {
            "recon": _handle_recon_type,
            "web": _handle_web_type,
            "crack": _handle_crack_type,
            "payload": _handle_payload_type,
            "red": _handle_red_type,
            "osint": _handle_osint_type,
        }
        await handlers[wizard_type](query, uid, wizard, value)
        return
    if wizard_type == "crack" and action == "method":
        if value == "custom":
            wizard["step"] = "awaiting_dictionary"
            await query.edit_message_text("Introduce palabras separadas por comas:")
        else:
            await _execute_crack(query, uid, wizard, value)
        return
    if wizard_type == "payload" and action == "lang":
        await _handle_payload_lang(query, uid, wizard, value)
        return
    if action == "depth":
        if wizard_type == "recon":
            await _execute_recon(query, uid, wizard, value)
        elif wizard_type == "web":
            await _execute_web(query, uid, wizard, value)
        elif wizard_type == "osint":
            await _execute_osint(query, uid, wizard, value)
        return
```

Change the six `_handle_*_type` signatures to `(query, uid, wizard, value)`.
Red is terminal and must consume its exact session before reading the snapshot,
submitting Nmap, or reporting the unavailable attack path.

- [ ] **Step 6: Make every remaining terminal path consume before I/O**

Apply these exact signature and ordering changes:

- `_execute_recon(query, uid, wizard, depth)`: validate `wizard["target"]`,
  consume `wizard["session_id"]`, then call `target_engine`, `task_queue`, audit,
  and Telegram. Read `target_type` from the snapshot.
- `_execute_osint(query, uid, wizard, depth)`: consume before
  `target_engine`, `asyncio.to_thread`, or `task_queue`. Use the snapshot's
  `osint_type`.
- `_handle_payload_lang(query, uid, wizard, lang)`: Webshell and Meterpreter
  consume before generator/tool calls; Reverse Shell only advances state.
- The `awaiting_port` text branch: validate the port, copy the state, consume
  the exact session, then call `reverse_shell()` and audit.
- The custom Crack text branch: validate words and hash, copy the state,
  consume, then call `hash_crack()`.
- Remove result-message inline Back buttons because their session has already
  been consumed. The persistent reply keyboard remains available.
- Delete `_execute_wizard()` and the legacy `wizard:*`, `depth:*`, `menu:main`,
  and `action:cancel` branches.

For each post-consumption task/tool block, catch `Exception`, call
`log.exception()`, write an `audit_log.log()` entry with status `"error"`, and
send a restart message through the safe Telegram adapter. Write status `"ok"`
only after task submission or tool execution returns successfully; never mark
an exception path successful.

At the start of message-state processing in `handle_text()`, add:

```python
if uid in user_wizards and _is_wizard_expired(uid):
    await update.message.reply_text(
        "Este wizard expiro. Abre uno nuevo desde el menu."
    )
    return
```

- [ ] **Step 7: Update existing tests to scoped state and run focused security tests**

Replace manually constructed wizard dictionaries with `_new_wizard()` and use
`_wizard_callback()` for every active callback. Keep one explicit legacy
callback test and assert it expires without changing a newly created state.

Run the four tests from Step 1 plus the existing callback, payload, Recon,
OSINT, Crack, and Back tests. Expected: all pass.

- [ ] **Step 8: Run the complete Telegram suite**

```powershell
python -m unittest discover -s tests -p "test_telegram_wizards.py" -v
```

Expected: all tests pass with no un-awaited coroutine warnings.

---

### Task 6: Restore Command Launchers

**Files:**
- Modify: `backend/telegram_bot.py` before `ayuda()` and in `main()`
- Modify: `tests/test_telegram_wizards.py`

**Interfaces:**
- Produces: `recon_command`, `web_command`, `crack_command`, `payload_command`, `osint_command`

- [ ] **Step 1: Write a failing registration and routing test**

Extend the existing fake-application test:

```python
def test_wizard_commands_and_media_handlers_are_registered(self):
    fake_app = SimpleNamespace(handlers=[], run_polling=Mock())
    fake_app.add_handler = fake_app.handlers.append
    builder = Mock()
    builder.token.return_value = builder
    builder.build.return_value = fake_app
    with (
        patch.object(telegram_bot.Application, "builder", return_value=builder),
        patch.dict(os.environ, {"TELEGRAM_TOKEN": "test-token"}),
        patch("builtins.print"),
    ):
        telegram_bot.main()

    commands = {
        command
        for handler in fake_app.handlers
        for command in getattr(handler, "commands", frozenset())
    }
    self.assertTrue(
        {"recon", "webscan", "web", "crack", "payload", "osint", "nmap"}
        <= commands
    )
    callbacks = {handler.callback for handler in fake_app.handlers}
    self.assertIn(telegram_bot.handle_photo, callbacks)
    self.assertIn(telegram_bot.handle_voice, callbacks)
    self.assertIn(telegram_bot.handle_document, callbacks)

async def test_recon_command_opens_fresh_wizard(self):
    update = make_text_update("/recon")
    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        patch.object(telegram_bot, "_start_recon_wizard", new=AsyncMock()) as start,
    ):
        await telegram_bot.recon_command(update, None)
    start.assert_awaited_once_with(update, 7)
```

- [ ] **Step 2: Verify RED**

Expected: restored command names and adapters are missing.

- [ ] **Step 3: Implement one shared authorization gate and adapters**

```python
async def _open_wizard_command(update, starter):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("No autorizado")
        return
    rate_limit_error = _rate_limit_msg(uid)
    if rate_limit_error:
        await update.message.reply_text(rate_limit_error)
        return
    user_wizards.pop(uid, None)
    await starter(update, uid)


async def recon_command(update, context):
    await _open_wizard_command(update, _start_recon_wizard)


async def web_command(update, context):
    await _open_wizard_command(update, _start_web_wizard)


async def crack_command(update, context):
    await _open_wizard_command(update, _start_crack_wizard)


async def payload_command(update, context):
    await _open_wizard_command(update, _start_payload_wizard)


async def osint_command(update, context):
    await _open_wizard_command(update, _start_osint_wizard)
```

Register both `webscan` and `web` to `web_command`; register the other four
adapters by name. Leave `CommandHandler("nmap", nmap_shortcut)` unchanged.

- [ ] **Step 4: Verify command tests and complete Telegram suite pass**

Run the two tests from Step 1, then the complete Telegram command from Task 5.

---

### Task 7: Close Coverage Gaps And Run Related Unit Suites

**Files:**
- Modify: `tests/test_telegram_wizards.py`
- Inspect only: production files changed by Tasks 1-6

**Interfaces:**
- Verifies every approved design behavior; produces no runtime API.

- [ ] **Step 1: Add the remaining regression cases**

Add tests with these exact assertions:

```python
async def test_expired_callback_removes_only_expired_session(self):
    wizard = telegram_bot._new_wizard(7, "recon", 70)
    wizard["created_at"] -= telegram_bot.WIZARD_TTL_SECONDS + 1
    data = telegram_bot._wizard_callback(wizard, "type", "dominio")
    update, query = make_callback_update(data)
    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
    ):
        await telegram_bot.handle_callback(update, None)
    self.assertNotIn(7, telegram_bot.user_wizards)
    self.assertIn("expir", query.edit_message_text.await_args.args[0].lower())

async def test_manipulated_crack_type_and_method_never_execute(self):
    with patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack:
        for action, value, step in (
            ("type", "zip", "select_type"),
            ("type", "doc", "select_type"),
            ("method", "rockyou", "select_dict"),
            ("method", "bogus", "select_dict"),
        ):
            wizard = telegram_bot._new_wizard(
                7,
                "crack",
                70,
                step=step,
                crack_type="hash",
                target="5d41402abc4b2a76b9719d911017c592",
            )
            data = (
                f"w:{wizard['session_id']}:crack:{action}:{value}"
            )
            update, _ = make_callback_update(data)
            with (
                patch.object(telegram_bot, "_check_role", return_value=True),
                patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            ):
                await telegram_bot.handle_callback(update, None)
    hash_crack.assert_not_called()

async def test_valid_scoped_recon_routes_selected_target_type(self):
    wizard = telegram_bot._new_wizard(
        7,
        "recon",
        70,
        step="awaiting_depth",
        target="8.8.8.8",
        target_type="ip",
    )
    data = telegram_bot._wizard_callback(wizard, "depth", "normal")
    update, _ = make_callback_update(data)
    task_queue = Mock()
    task_queue.submit.return_value = "ABC123"
    with (
        patch.object(telegram_bot, "_check_role", return_value=True),
        patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        patch.object(telegram_bot, "target_engine") as target_engine,
        patch.object(telegram_bot, "task_queue", task_queue),
        patch.object(telegram_bot.audit_log, "log"),
        patch.object(telegram_bot, "_poll_nmap_task", new=Mock(return_value=None)),
        patch.object(asyncio, "create_task"),
    ):
        await telegram_bot.handle_callback(update, None)
    target_engine.set_target.assert_called_once_with(7, "8.8.8.8", "ip")
    task_queue.submit.assert_called_once()
```

Retain and update the existing tests for Webshell, selected payload language,
OSINT email, custom dictionary words, main-menu routing, media registration,
and Nmap Markdown fallback. Together with Tasks 1-6, the module must cover all
13 design categories, not merely contain 13 total tests.

- [ ] **Step 2: Run syntax and whitespace checks**

```powershell
python -m py_compile backend/telegram_bot.py tests/test_telegram_wizards.py
```

Expected: both commands exit 0. A Git LF/CRLF notice is informational; actual
whitespace errors are not.

- [ ] **Step 3: Run the complete offline Telegram suite**

```powershell
python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v
```

Expected: all Telegram tests pass.

- [ ] **Step 4: Run every related isolated unit suite**

```powershell
python -X utf8 -m unittest discover -s tests -p "test_kali_server.py" -v
python -X utf8 -m unittest discover -s tests -p "test_tools_engine.py" -v
python -X utf8 -m unittest discover -s tests -p "test_task_queue_tools.py" -v
python -X utf8 -m unittest discover -s tests -p "test_tools_router.py" -v
python -X utf8 -m unittest discover -s tests -p "test_kali_dockerfile.py" -v
python -X utf8 -m unittest discover -s tests -p "test_prompt_limits.py" -v
```

Expected: all related unit tests pass. Do not run `tests/test_api.py` as a
release gate for this change; its stale token, form, upload, and workflow
contracts are documented separately.

- [ ] **Step 5: Inspect the final diff for unintended files and secrets**

```powershell
git status --short
```

Expected before deployment: runtime and test changes only; `AGENTS.md` remains
unchanged until deployment evidence exists. Do not stage or commit secrets.

---

### Task 8: Rebuild, Verify, And Document Deployment

**Files:**
- Modify after evidence: `AGENTS.md`
- Inspect: `docker-compose.yml`, container logs and status

**Interfaces:**
- Operational result: one healthy/stable Telegram polling container using the verified source.

- [ ] **Step 1: Build only the Telegram service image**

```powershell
docker compose build artenisa-telegram-bot
```

Expected: build exits 0. If Docker fails, preserve the output and do not claim
deployment.

- [ ] **Step 2: Recreate only the Telegram container**

```powershell
docker compose up -d --no-deps --force-recreate artenisa-telegram-bot
```

Expected: `artenisa-telegram-bot` is recreated without replacing Backend or
Kali containers.

- [ ] **Step 3: Verify runtime state and logs**

Run separately:

```powershell
docker compose ps artenisa-telegram-bot
```

Expected evidence:

- Container state is `Up` and remains up across two checks separated by at
  least 30 seconds.
- Log contains `Bot de Telegram iniciado`.
- Log does not contain `Conflict`, duplicate polling, traceback, or import
  errors.
- Exactly one `artenisa-telegram-bot` service container is listed.

- [ ] **Step 4: Perform non-destructive Telegram smoke checks if access is available**

Verify `/start`, `/recon`, `/web`, `/crack`, `/payload`, `/osint`, and one old
button. The old button must report expiration; no smoke test should launch an
attack or unsupported tool. If interactive Telegram access is unavailable,
record that limitation instead of claiming manual verification.

- [ ] **Step 5: Update `AGENTS.md` with facts only**

Replace the old disk blocker with the current free-space/rebuild result. Record:

- Exact test commands and pass counts.
- Telegram image/container rebuild result.
- Container state and relevant startup-log result.
- Whether interactive smoke checks were or were not performed.
- Current uncommitted/committed state.
- Advanced Kali binaries remain installed but not API-exposed.

- [ ] **Step 6: Re-run final verification after the documentation edit**

```powershell
python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v
```

Expected: Telegram suite remains green; documentation is the only post-test
source change; status contains no generated secrets or unexpected files.
