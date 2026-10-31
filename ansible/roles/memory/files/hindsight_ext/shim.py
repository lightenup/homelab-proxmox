"""Hindsight extensions for the shared memory store (spec 097, research R-001, R-002).

Translation only: every decision is made in memory_access.py, mounted next to this file. Both
are loaded from PYTHONPATH by the stock image through server.env:

    HINDSIGHT_API_TENANT_EXTENSION=shim:ClientKeyTenantExtension
    HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=shim:ClientScopeValidator

Decisions key on RequestContext.api_key_id, never on api_key: the async worker re-runs
validate_retain with the key dropped (internal=True, api_key_id kept).
"""

from __future__ import annotations

from pathlib import Path

import memory_access
from hindsight_api.config import get_config
from hindsight_api.extensions.operation_validator import OperationValidatorExtension, ValidationResult
from hindsight_api.extensions.tenant import AuthenticationError, Tenant, TenantContext, TenantExtension

# The Hindsight release these signatures were read against. Guard test: test_memory_config.py
# fails when hindsight_version moves without this (and the harness gate, FR-021) moving too.
HINDSIGHT_VERIFIED_VERSION = "1.1.0"


def _load(config: dict[str, str]) -> list[memory_access.Client]:
    return memory_access.load_clients(Path(config["clients_file"]).read_text())


class ClientKeyTenantExtension(TenantExtension):
    def __init__(self, config: dict[str, str]):
        super().__init__(config)
        self._clients = _load(config)

    async def authenticate(self, context):
        client = memory_access.authenticate(context.api_key, self._clients)
        if client is None:
            raise AuthenticationError("Invalid API key")
        context.api_key_id = client.id
        return TenantContext(schema_name=get_config().database_schema)

    async def list_tenants(self):
        return [Tenant(schema=get_config().database_schema)]


class ClientScopeValidator(OperationValidatorExtension):
    def __init__(self, config: dict[str, str]):
        super().__init__(config)
        self._clients = _load(config)

    def _result(self, request_context, operation: str) -> ValidationResult:
        decision = memory_access.authorize(
            self._clients,
            api_key_id=request_context.api_key_id,
            internal=request_context.internal,
            operation=operation,
        )
        return ValidationResult.accept() if decision.allowed else ValidationResult.reject(decision.reason, 403)

    async def validate_retain(self, ctx):
        rc = ctx.request_context
        decision, contents = memory_access.retain(
            self._clients, api_key_id=rc.api_key_id, internal=rc.internal, items=ctx.contents
        )
        if not decision.allowed:
            return ValidationResult.reject(decision.reason, 403)
        return ValidationResult.accept() if contents is None else ValidationResult.accept_with(contents=contents)

    async def validate_recall(self, ctx):
        return self._result(ctx.request_context, "recall")

    async def validate_reflect(self, ctx):
        return self._result(ctx.request_context, "reflect")

    async def validate_consolidate(self, ctx):
        return self._result(ctx.request_context, "consolidate")

    async def validate_memory_update(self, ctx):
        return self._result(ctx.request_context, "memory_update")

    async def validate_bank_read(self, ctx):
        return self._result(ctx.request_context, str(ctx.operation))

    async def validate_bank_write(self, ctx):
        return self._result(ctx.request_context, str(ctx.operation))

    async def validate_import(self, ctx):
        return self._result(ctx.request_context, "import")

    async def validate_create_bank(self, ctx):
        return self._result(ctx.request_context, "create_bank")

    async def validate_mental_model_get(self, ctx):
        return self._result(ctx.request_context, "mental_model_get")

    async def validate_mental_model_refresh(self, ctx):
        return self._result(ctx.request_context, "mental_model_refresh")
