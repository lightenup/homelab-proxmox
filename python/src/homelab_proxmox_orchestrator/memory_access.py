"""Access policy for the shared memory store (spec 097, research R-001, R-002).

Every decision about who may do what on the Hindsight server lives here, as pure functions over
plain data. The shim in ansible/roles/memory/files/hindsight_ext/shim.py subclasses Hindsight's
tenant and operation-validator extensions and only translates their contexts into these calls.

This file is mounted on its own into the stock Hindsight container next to the shim, so it uses
the standard library only and imports nothing else from this package.

Scope matrix: data-model.md § Scope matrix. It is an allowlist: an operation not listed for a
scope is refused. Operation names are Hindsight's (the BankReadOperation and BankWriteOperation
enum values plus the per-hook names). The guard test test_memory_config.py checks every name here
against the pinned snapshot ansible/roles/memory/files/hindsight_ext/operations-<version>.txt,
and that every name in the snapshot is either allowed to some scope or in REFUSED_FOR_ALL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any

KEY_PREFIX = "hmem_"
CLIENT_TAG_PREFIX = "client:"
CLIENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Browse: recall and every bank read except the two below (R-001, R-020). Every key can already
# read the whole bank through recall, and none of these reads runs an LLM, writes or sends
# anything out; the web UI needs most of them (refused one view at a time in the first PROD
# click-through, 2026-10-31). Kept back: get_bank_config (curator and up, the UI's settings
# page) and export_knowledge_base (a bulk export, refused for every scope). Writes stay a strict
# allowlist, and an operation a Hindsight bump adds is refused until someone classifies it.
_READ = frozenset(
    {
        "recall",
        "mental_model_get",
        "get_bank_profile",
        "get_bank_stats",
        "get_chunk",
        "get_directive",
        "get_document",
        "get_document_history",
        "get_entity",
        "get_entity_graph",
        "get_entity_state",
        "get_graph_data",
        "get_knowledge_base_tree",
        "get_knowledge_page",
        "get_memories_timeseries",
        "get_memory_unit",
        "get_mental_model_history",
        "get_observation_history",
        "get_operation_status",
        "list_bank_aliases",
        "list_directives",
        "list_document_chunks",
        "list_documents",
        "list_entities",
        "list_memory_units",
        "list_mental_model_tags",
        "list_mental_models",
        "list_observation_scopes",
        "list_operations",
        "list_tags",
        "list_webhook_deliveries",
        "list_webhooks",
        "search_knowledge_base",
    }
)
# Retain, plus curation of one unit (edit, invalidate, revert). Hindsight fires the bank write
# update_memory_unit before the memory_update hook, so both are needed. An edit or a delete then
# submits graph and vector-index maintenance in the caller's own context (relink, prune orphaned
# entities, index upkeep; no LLM, no egress). Refusing those left stale links after every delete
# (first PROD deletes, 2026-10-31; research R-019).
_WRITE = frozenset(
    {
        "retain",
        "memory_update",
        "update_memory_unit",
        "submit_async_graph_maintenance",
        "submit_async_vector_index_maintenance",
    }
)
# Hard delete of a conversation and retry of a failed operation (owner choice 2026-10-31), and
# reading the bank's settings for the web UI's settings page. Changing them stays admin-only.
_CURATE = frozenset({"delete_document", "retry_operation", "get_bank_config"})
# Whole-bank operations for the backup, restore drill, deploy probe and import task only.
# Creating a bank through PUT also fires update_bank.
_WHOLE_BANK = frozenset(
    {
        "import",
        "import_documents",
        "create_bank",
        "update_bank",
        "update_bank_config",
        "delete_bank",
    }
)

SCOPE_ALLOWLISTS: dict[str, frozenset[str]] = {
    "readonly": _READ,
    "readwrite": _READ | _WRITE,
    "curator": _READ | _WRITE | _CURATE,
    "admin": _READ | _WRITE | _CURATE | _WHOLE_BANK,
}

# Refused for every scope, admin included (FR-004 and exfiltration, research R-001): outbound
# webhooks, anything that runs an inference pass (reflect, consolidation, mental models,
# directives, reprocess), knowledge-base writes, bank settings that could switch extraction or
# consolidation back on, and the unused entity, graph and observation surfaces. Listed in full
# so a refusal names the operation as disabled rather than as above the caller's scope.
REFUSED_FOR_ALL = frozenset(
    {
        "cancel_operation",
        "clear_mental_model",
        "clear_observations",
        "clear_observations_for_memory",
        "consolidate",
        "create_bank_alias",
        "create_directive",
        "create_knowledge_folder",
        "create_knowledge_page",
        "create_mental_model",
        "create_webhook",
        "delete_bank_alias",
        "delete_directive",
        "delete_knowledge_node",
        "delete_mental_model",
        "delete_operation",
        "delete_webhook",
        "export_knowledge_base",
        "mental_model_refresh",
        "merge_bank_mission",
        "move_knowledge_node",
        "reflect",
        "rename_knowledge_node",
        "reprocess_document",
        "reset_bank_config",
        "retry_failed_consolidation",
        "run_consolidation",
        "set_bank_mission",
        "submit_async_consolidation",
        "update_bank_disposition",
        "update_directive",
        "update_document",
        "update_knowledge_page",
        "update_mental_model",
        "update_webhook",
    }
)


class ClientFileError(ValueError):
    """The client file is malformed or breaks a validation rule (data-model.md § Client)."""


@dataclass(frozen=True)
class Client:
    id: str
    sha256: str
    scope: str


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None


ALLOW = Decision(True)


def load_clients(text: str) -> list[Client]:
    """Parse and validate clients.json: a JSON list of {"id", "sha256", "scope"}."""
    if KEY_PREFIX in text:
        raise ClientFileError(f"client file holds a plaintext key ({KEY_PREFIX}…); store sha256 only")
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClientFileError(f"client file is not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ClientFileError("client file must be a JSON list")
    clients: list[Client] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ClientFileError(f"client entry is not an object: {entry!r}")
        cid, digest, scope = entry.get("id"), entry.get("sha256"), entry.get("scope")
        if not isinstance(cid, str) or not CLIENT_ID_RE.match(cid):
            raise ClientFileError(f"client id {cid!r} does not match {CLIENT_ID_RE.pattern}")
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            raise ClientFileError(f"client {cid}: sha256 must be 64 lowercase hex characters")
        if scope not in SCOPE_ALLOWLISTS:
            raise ClientFileError(f"client {cid}: scope {scope!r} is not one of {sorted(SCOPE_ALLOWLISTS)}")
        clients.append(Client(id=cid, sha256=digest, scope=scope))
    ids = [c.id for c in clients]
    if len(set(ids)) != len(ids):
        raise ClientFileError(f"duplicate id in client file: {ids}")
    if len({c.sha256 for c in clients}) != len(clients):
        raise ClientFileError("duplicate sha256 in client file: two clients share a key")
    if sum(c.scope == "admin" for c in clients) != 1:
        raise ClientFileError("client file must hold exactly one admin client")
    return clients


def authenticate(bearer: str | None, clients: list[Client]) -> Client | None:
    """Return the client whose key hashes to sha256(bearer), or None.

    Every entry is compared with hmac.compare_digest, so the time taken does not reveal which
    entry matched. A revoked client is simply absent from the list.
    """
    if not bearer:
        return None
    digest = hashlib.sha256(bearer.encode()).hexdigest()
    match: Client | None = None
    for client in clients:
        if hmac.compare_digest(digest, client.sha256):
            match = client
    return match


def decide(client: Client, operation: str) -> Decision:
    """Allow or refuse one operation for a client (contracts/memory-access.md § Responses)."""
    if operation in REFUSED_FOR_ALL:
        return Decision(False, f"{operation} is disabled")
    if operation in SCOPE_ALLOWLISTS[client.scope]:
        return ALLOW
    return Decision(False, f"scope {client.scope} may not {operation}")


def rewrite_retain_tags(client: Client, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stamp client:<id> on every retained item (research R-002).

    Any client-supplied client:* tag is dropped first, so attribution cannot be forged. Admin
    keeps a supplied client tag (the one-shot import attributes Open WebUI's old memories), and
    gets its own only when none is supplied. The input is not mutated.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        tags = list(item.get("tags") or [])
        if client.scope == "admin" and any(t.startswith(CLIENT_TAG_PREFIX) for t in tags):
            out.append(dict(item))
            continue
        kept = [t for t in tags if not t.startswith(CLIENT_TAG_PREFIX)]
        out.append({**item, "tags": [*kept, CLIENT_TAG_PREFIX + client.id]})
    return out


def _client_by_id(clients: list[Client], api_key_id: str | None) -> Client | None:
    return next((c for c in clients if api_key_id and c.id == api_key_id), None)


def authorize(clients: list[Client], *, api_key_id: str | None, internal: bool, operation: str) -> Decision:
    """Decide a request as the shim sees it.

    Internal calls come from Hindsight's own worker, which re-runs validators on work that was
    validated at submit time and drops the key (it keeps api_key_id), so they are accepted.
    External calls are keyed on api_key_id, which the tenant extension set from the key.
    """
    if internal:
        return ALLOW
    client = _client_by_id(clients, api_key_id)
    if client is None:
        return Decision(False, "unknown client")
    return decide(client, operation)


def retain(
    clients: list[Client], *, api_key_id: str | None, internal: bool, items: list[dict[str, Any]]
) -> tuple[Decision, list[dict[str, Any]] | None]:
    """Decide a retain and return the rewritten items, or None to keep them unchanged."""
    decision = authorize(clients, api_key_id=api_key_id, internal=internal, operation="retain")
    if internal or not decision.allowed:
        return decision, None
    client = _client_by_id(clients, api_key_id)
    assert client is not None  # authorize() refused an unknown client above
    return decision, rewrite_retain_tags(client, items)
