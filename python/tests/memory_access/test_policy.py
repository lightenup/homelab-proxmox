"""Unit tests for the memory access policy (spec 097, task T005; research R-001, R-002).

The policy decides who may do what on the shared memory store. It is pure: the Hindsight shim
(ansible/roles/memory/files/hindsight_ext/shim.py) only translates Hindsight's contexts into
these calls. The scope matrix is data-model.md § Scope matrix; refusal reasons are
contracts/memory-access.md § Responses to refusals.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from homelab_proxmox_orchestrator import memory_access as ma
from homelab_proxmox_orchestrator.memory_access import (
    REFUSED_FOR_ALL,
    SCOPE_ALLOWLISTS,
    Client,
    ClientFileError,
    authenticate,
    authorize,
    decide,
    load_clients,
    retain,
    rewrite_retain_tags,
    split_retain_turns,
)

HERMES_KEY = "hmem_test_hermes_0123456789abcdefghijklmnop"
BACKUP_KEY = "hmem_test_backup_0123456789abcdefghijklmnop"
READONLY_KEY = "hmem_test_readonly_0123456789abcdefghijklm"


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _entry(cid: str, key: str, scope: str) -> dict[str, str]:
    return {"id": cid, "sha256": _sha(key), "scope": scope}


def _text(*entries: dict[str, str]) -> str:
    return json.dumps(list(entries))


@pytest.fixture
def clients() -> list[Client]:
    return load_clients(
        _text(
            _entry("hermes", HERMES_KEY, "readwrite"),
            _entry("claude-code", READONLY_KEY, "readonly"),
            _entry("backup", BACKUP_KEY, "admin"),
        )
    )


def _client(cid: str, scope: str) -> Client:
    return Client(id=cid, sha256=_sha(cid), scope=scope)


# --------------------------------------------------------------------------- (a) client list


def test_load_clients_returns_every_entry_in_order(clients):
    assert [(c.id, c.scope) for c in clients] == [
        ("hermes", "readwrite"),
        ("claude-code", "readonly"),
        ("backup", "admin"),
    ]
    assert clients[0].sha256 == _sha(HERMES_KEY)


@pytest.mark.parametrize("cid", ["ab", "hermes", "open-webui", "a" + "b" * 31, "c2"])
def test_valid_client_ids_load(cid):
    load_clients(_text(_entry(cid, "hmem_x" + cid, "readwrite"), _entry("backup", BACKUP_KEY, "admin")))


@pytest.mark.parametrize("cid", ["a", "Hermes", "1abc", "-abc", "a_b", "a" + "b" * 32, "", "a b"])
def test_invalid_client_ids_are_rejected(cid):
    with pytest.raises(ClientFileError, match="id"):
        load_clients(_text(_entry(cid, "hmem_x", "readwrite"), _entry("backup", BACKUP_KEY, "admin")))


def test_duplicate_client_ids_are_rejected():
    with pytest.raises(ClientFileError, match="duplicate id"):
        load_clients(
            _text(
                _entry("hermes", HERMES_KEY, "readwrite"),
                _entry("hermes", READONLY_KEY, "readonly"),
                _entry("backup", BACKUP_KEY, "admin"),
            )
        )


def test_duplicate_hashes_are_rejected():
    with pytest.raises(ClientFileError, match="duplicate sha256"):
        load_clients(
            _text(
                _entry("hermes", HERMES_KEY, "readwrite"),
                _entry("open-webui", HERMES_KEY, "readwrite"),
                _entry("backup", BACKUP_KEY, "admin"),
            )
        )


@pytest.mark.parametrize("admins", [0, 2])
def test_exactly_one_admin_client(admins):
    entries = [_entry("hermes", HERMES_KEY, "readwrite")]
    entries += [_entry(f"backup{i}", f"hmem_admin{i}", "admin") for i in range(admins)]
    with pytest.raises(ClientFileError, match="exactly one admin"):
        load_clients(_text(*entries))


def test_unknown_scope_is_rejected():
    with pytest.raises(ClientFileError, match="scope"):
        load_clients(_text(_entry("hermes", HERMES_KEY, "owner"), _entry("backup", BACKUP_KEY, "admin")))


def test_plaintext_key_is_rejected():
    entry = {"id": "hermes", "sha256": HERMES_KEY, "scope": "readwrite"}
    with pytest.raises(ClientFileError, match="plaintext"):
        load_clients(_text(entry, _entry("backup", BACKUP_KEY, "admin")))


def test_plaintext_key_in_any_field_is_rejected():
    entry = _entry("hermes", HERMES_KEY, "readwrite") | {"note": HERMES_KEY}
    with pytest.raises(ClientFileError, match="plaintext"):
        load_clients(_text(entry, _entry("backup", BACKUP_KEY, "admin")))


@pytest.mark.parametrize("digest", ["abc", "G" * 64, _sha("x").upper(), _sha("x") + "0"])
def test_sha256_must_be_lowercase_hex_digest(digest):
    entry = {"id": "hermes", "sha256": digest, "scope": "readwrite"}
    with pytest.raises(ClientFileError, match="sha256"):
        load_clients(_text(entry, _entry("backup", BACKUP_KEY, "admin")))


@pytest.mark.parametrize(
    "text",
    ["not json", "{}", '"x"', json.dumps([["hermes"]]), json.dumps([{"id": "hermes", "scope": "admin"}])],
)
def test_malformed_client_file_is_rejected(text):
    with pytest.raises(ClientFileError):
        load_clients(text)


# --------------------------------------------------------------------------- (b) authentication


def test_authenticate_returns_the_matching_client(clients):
    assert authenticate(HERMES_KEY, clients).id == "hermes"
    assert authenticate(BACKUP_KEY, clients).id == "backup"


def test_authenticate_compares_in_constant_time(clients, monkeypatch):
    calls: list[tuple[str, str]] = []

    def spy(a, b):
        calls.append((a, b))
        return a == b

    monkeypatch.setattr(ma.hmac, "compare_digest", spy)
    assert authenticate(READONLY_KEY, clients).id == "claude-code"
    # Every client is compared, so the time taken does not reveal which entry matched.
    assert len(calls) == len(clients)


@pytest.mark.parametrize("bearer", [None, "", "hmem_test_unknown_000000000000000000000", HERMES_KEY + " "])
def test_unknown_or_empty_keys_do_not_authenticate(clients, bearer):
    assert authenticate(bearer, clients) is None


def test_revoked_key_does_not_authenticate(clients):
    revoked = [c for c in clients if c.id != "claude-code"]
    assert authenticate(READONLY_KEY, revoked) is None


# --------------------------------------------------------------------------- (c) scope matrix

READ = [
    "recall",
    "list_memory_units",
    "get_memory_unit",
    "list_documents",
    "get_document",
    "list_document_chunks",
    "get_chunk",
    "list_tags",
    "get_bank_stats",
    "get_bank_profile",
    "get_operation_status",
    "list_operations",
    "get_memories_timeseries",
    "get_entity_graph",
    "list_entities",
    "list_mental_models",
    "list_directives",
    "get_graph_data",
    "get_knowledge_base_tree",
    "get_knowledge_page",
    "search_knowledge_base",
    "get_document_history",
    "mental_model_get",
]
RETAIN = ["retain"]
CURATE = [
    "memory_update",
    "update_memory_unit",
    "submit_async_graph_maintenance",
    "submit_async_vector_index_maintenance",
]
DELETE_RETRY = ["delete_document", "retry_operation", "get_bank_config"]
WHOLE_BANK = ["import", "import_documents", "create_bank", "update_bank_config", "delete_bank"]
NEVER = [
    "create_webhook",
    "update_webhook",
    "reflect",
    "consolidate",
    "run_consolidation",
    "submit_async_consolidation",
    "retry_failed_consolidation",
    "create_mental_model",
    "mental_model_refresh",
    "create_directive",
    "update_directive",
    "reprocess_document",
    "create_knowledge_page",
    "update_knowledge_page",
    "create_knowledge_folder",
    "reset_bank_config",
    "set_bank_mission",
]

MATRIX = {
    "readonly": READ,
    "readwrite": READ + RETAIN + CURATE,
    "curator": READ + RETAIN + CURATE + DELETE_RETRY,
    "admin": READ + RETAIN + CURATE + DELETE_RETRY + WHOLE_BANK,
}
EVERY_ROW = READ + RETAIN + CURATE + DELETE_RETRY + WHOLE_BANK + NEVER


@pytest.mark.parametrize("scope", list(MATRIX))
@pytest.mark.parametrize("operation", EVERY_ROW)
def test_scope_matrix(scope, operation):
    decision = decide(_client("c1", scope), operation)
    assert decision.allowed is (operation in MATRIX[scope]), (scope, operation, decision)
    if decision.allowed:
        assert decision.reason is None


@pytest.mark.parametrize("scope", list(MATRIX))
@pytest.mark.parametrize("operation", NEVER)
def test_refused_for_every_scope_names_the_operation_as_disabled(scope, operation):
    decision = decide(_client("c1", scope), operation)
    assert decision == ma.Decision(False, f"{operation} is disabled")


def test_scopes_are_strictly_nested():
    order = ["readonly", "readwrite", "curator", "admin"]
    for lower, higher in zip(order, order[1:]):
        assert SCOPE_ALLOWLISTS[lower] < SCOPE_ALLOWLISTS[higher], (lower, higher)


def test_no_operation_is_both_allowed_and_refused_for_all():
    allowed = frozenset().union(*SCOPE_ALLOWLISTS.values())
    assert not allowed & REFUSED_FOR_ALL
    assert set(SCOPE_ALLOWLISTS) == {"readonly", "readwrite", "curator", "admin"}


# --------------------------------------------------------------------------- (d) unlisted operations


@pytest.mark.parametrize("scope", list(MATRIX))
def test_unlisted_operation_is_refused_with_the_scope_reason(scope):
    decision = decide(_client("c1", scope), "operation_added_upstream")
    assert decision == ma.Decision(False, f"scope {scope} may not operation_added_upstream")


def test_scope_too_low_names_scope_and_operation():
    assert decide(_client("c1", "readonly"), "retain").reason == "scope readonly may not retain"
    assert decide(_client("c1", "readwrite"), "delete_bank").reason == "scope readwrite may not delete_bank"


# --------------------------------------------------------------------------- (e) tag rewrite


def test_forged_client_tag_is_replaced():
    items = [{"content": "x", "tags": ["client:other", "session:s1"]}]
    assert rewrite_retain_tags(_client("hermes", "readwrite"), items)[0]["tags"] == [
        "session:s1",
        "client:hermes",
    ]


def test_missing_tag_list_gets_the_client_tag():
    out = rewrite_retain_tags(_client("hermes", "readwrite"), [{"content": "x"}])
    assert out == [{"content": "x", "tags": ["client:hermes"]}]


def test_null_tag_list_gets_the_client_tag():
    out = rewrite_retain_tags(_client("hermes", "readwrite"), [{"content": "x", "tags": None}])
    assert out[0]["tags"] == ["client:hermes"]


def test_every_item_is_rewritten():
    items = [
        {"content": "a", "tags": ["client:a"]},
        {"content": "b", "tags": ["client:b", "client:c"]},
        {"content": "c"},
    ]
    out = rewrite_retain_tags(_client("open-webui", "readwrite"), items)
    assert [i["tags"] for i in out] == [["client:open-webui"]] * 3
    assert [i["content"] for i in out] == ["a", "b", "c"]


def test_session_and_other_tags_are_kept_in_order():
    items = [{"content": "x", "tags": ["session:owui-1", "origin:x", "client:x", "topic:car"]}]
    out = rewrite_retain_tags(_client("hermes", "readwrite"), items)
    assert out[0]["tags"] == ["session:owui-1", "origin:x", "topic:car", "client:hermes"]


def test_rewrite_does_not_mutate_the_input():
    items = [{"content": "x", "tags": ["client:other"]}]
    rewrite_retain_tags(_client("hermes", "readwrite"), items)
    assert items == [{"content": "x", "tags": ["client:other"]}]


def test_admin_keeps_a_supplied_client_tag():
    items = [{"content": "x", "tags": ["client:open-webui", "origin:open-webui-memory"]}]
    assert rewrite_retain_tags(_client("backup", "admin"), items) == items


def test_admin_without_a_client_tag_gets_its_own():
    out = rewrite_retain_tags(_client("backup", "admin"), [{"content": "x", "tags": ["origin:y"]}])
    assert out[0]["tags"] == ["origin:y", "client:backup"]


# --------------------------------------------------------------------------- (f) request-level calls


def test_internal_calls_are_accepted_without_a_rewrite(clients):
    items = [{"content": "x", "tags": ["client:anything"]}]
    decision, out = retain(clients, api_key_id="hermes", internal=True, items=items)
    assert decision.allowed and out is None


def test_internal_calls_are_accepted_for_any_operation(clients):
    assert authorize(clients, api_key_id="hermes", internal=True, operation="consolidate").allowed
    assert authorize(clients, api_key_id=None, internal=True, operation="get_bank_stats").allowed


def test_external_retain_is_rewritten(clients):
    decision, out = retain(clients, api_key_id="hermes", internal=False, items=[{"content": "x"}])
    assert decision.allowed
    assert out == [{"content": "x", "tags": ["client:hermes"]}]


def test_external_retain_from_readonly_is_refused(clients):
    decision, out = retain(clients, api_key_id="claude-code", internal=False, items=[{"content": "x"}])
    assert decision == ma.Decision(False, "scope readonly may not retain")
    assert out is None


@pytest.mark.parametrize("api_key_id", [None, "", "revoked-client"])
def test_external_call_without_a_known_client_is_refused(clients, api_key_id):
    decision = authorize(clients, api_key_id=api_key_id, internal=False, operation="recall")
    assert decision == ma.Decision(False, "unknown client")
    decision, out = retain(clients, api_key_id=api_key_id, internal=False, items=[{"content": "x"}])
    assert not decision.allowed and out is None


def test_authorize_applies_the_scope(clients):
    assert authorize(clients, api_key_id="hermes", internal=False, operation="recall").allowed
    assert not authorize(clients, api_key_id="hermes", internal=False, operation="delete_bank").allowed
    assert authorize(clients, api_key_id="backup", internal=False, operation="delete_bank").allowed


# --- one document per turn (T071, research R-012) ---


def _msg(role: str, text: str, ts: str = "2026-11-01T12:00:00+01:00") -> dict[str, str]:
    return {"role": role, "content": f"{role.capitalize()}: {text}", "timestamp": ts}


def _conversation(*pairs: tuple[str, str], doc: str = "api-abc", **extra) -> dict:
    messages = [m for u, a in pairs for m in (_msg("user", u), _msg("assistant", a))]
    item = {"content": json.dumps(messages), "document_id": doc, "update_mode": "append",
            "tags": [f"session:{doc}", "client:hermes"], "metadata": {"platform": "hermes"}}
    item.update(extra)
    return item


def test_each_turn_becomes_its_own_document_without_append():
    out = split_retain_turns([_conversation(("a", "b"), ("c", "d"))])
    assert len(out) == 2
    for item in out:
        assert re.fullmatch(r"api-abc--[0-9a-f]{16}", item["document_id"])
        assert "update_mode" not in item
        assert item["tags"] == ["session:api-abc", "client:hermes"]
        assert item["metadata"] == {"platform": "hermes"}
    assert [[m["content"] for m in json.loads(i["content"])] for i in out] == [
        ["User: a", "Assistant: b"], ["User: c", "Assistant: d"]]


def test_the_key_is_stable_when_a_turn_is_sent_again():
    """A restart or the plugin's full-session resend repeats turns: same key, so an identical replace."""
    first = split_retain_turns([_conversation(("a", "b"))])
    resent = split_retain_turns([_conversation(("a", "b"), ("c", "d"), doc="api-abc-1730000000",
                                               tags=["session:api-abc"])])
    assert resent[0]["document_id"] == first[0]["document_id"]
    assert split_retain_turns(first) == first


def test_the_session_tag_names_the_document_before_the_document_id():
    [item] = split_retain_turns([_conversation(("a", "b"), doc="per-process-id", tags=["session:stable"])])
    assert item["document_id"].startswith("stable--")


def test_a_missing_session_tag_is_added_from_the_document_id():
    [item] = split_retain_turns([_conversation(("a", "b"), doc="owui-chat1", tags=[])])
    assert item["tags"] == ["session:owui-chat1"]
    assert item["document_id"].startswith("owui-chat1--")


def test_repeated_turns_in_one_request_are_sent_once():
    """Hindsight refuses duplicate document ids in one batch (400)."""
    item = _conversation(("a", "b"))
    assert len(split_retain_turns([item, item])) == 1
    assert len(split_retain_turns([_conversation(("a", "b"), ("a", "b"))])) == 1


def test_different_turns_with_the_same_words_differ_by_timestamp():
    one = _conversation(("ok", "fine"))
    two = dict(one, content=json.dumps([_msg("user", "ok", "2026-11-01T13:00:00+01:00"),
                                         _msg("assistant", "fine", "2026-11-01T13:00:00+01:00")]))
    assert len(split_retain_turns([one, two])) == 2


def test_consecutive_user_messages_stay_in_one_turn_and_a_leading_reply_is_its_own():
    messages = [_msg("assistant", "hello"), _msg("user", "x"), _msg("user", "y"), _msg("assistant", "z")]
    out = split_retain_turns([{"content": json.dumps(messages), "document_id": "s", "tags": ["session:s"]}])
    assert [[m["role"] for m in json.loads(i["content"])] for i in out] == [["assistant"], ["user", "user", "assistant"]]


@pytest.mark.parametrize("item", [
    {"content": "Open WebUI saved memory: likes tea", "document_id": "owui-memory-1", "tags": []},
    {"content": "plain text", "tags": ["session:s"]},
    {"content": json.dumps([{"no": "role"}]), "document_id": "d", "tags": []},
    {"content": "[]", "document_id": "d", "tags": []},
    {"content": json.dumps([_msg("user", "a")]), "tags": []},                              # no session at all
    {**_conversation(("a", "b")), "attachment_filenames": {"f": "x.pdf"}},
])
def test_other_items_pass_unchanged(item):
    assert split_retain_turns([item]) == [item]


def test_the_input_is_not_mutated():
    item = _conversation(("a", "b"))
    before = json.dumps(item, sort_keys=True)
    split_retain_turns([item])
    assert json.dumps(item, sort_keys=True) == before


def test_retain_splits_turns_and_then_stamps_the_client(clients):
    item = _conversation(("a", "b"), ("c", "d"), tags=["session:api-abc", "client:forged"])
    decision, out = retain(clients, api_key_id="hermes", internal=False, items=[item])
    assert decision.allowed and len(out) == 2
    assert all(i["tags"] == ["session:api-abc", "client:hermes"] for i in out)
