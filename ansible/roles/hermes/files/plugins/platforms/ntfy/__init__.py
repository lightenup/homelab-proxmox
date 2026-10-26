"""ntfy adapter override that splits long replies instead of cutting them (spec 095, research R-018).

Why this exists: the bundled ntfy adapter (nousresearch/hermes-agent v0.21.6,
plugins/platforms/ntfy/adapter.py:280-284) slices every chat reply to 4096 characters and only logs
a WARNING, so the reader never learns the end is missing (T008 step 7, US1 AS-4). The base class
already has the splitter other adapters use (`truncate_message`, (n/m) indicators, code fences
kept); the ntfy adapter just doesn't call it.

What it changes: only how a long reply is cut. Each chunk goes through the bundled adapter's own
send(), so auth, markdown, the HTTP call and error handling stay upstream's code. register() is
the bundled one with only `adapter_factory` replaced.

How it's loaded: Hermes lets a user plugin with the same directory name override a bundled one
(hermes_cli/plugins_discovery.py resolve_manifest_winners). This directory is mounted read-only
at /opt/data/plugins/platforms/ntfy and enabled by `plugins.enabled` in the read-only config.yaml,
so the agent can neither edit it nor turn it off.

Remove when: an upstream release chunks natively (T076); then delete this directory, its compose
mount and the plugins.enabled entry. Static file, standard library only, copied (not templated) so
pytest can import it (python/tests/hermes_hooks/test_ntfy_chunking_shim.py).
"""

from plugins.platforms.ntfy import adapter as _bundled


class ChunkingNtfyAdapter(_bundled.NtfyAdapter):
    """The bundled adapter, but long replies are split into (n/m) messages, not truncated."""

    splits_long_messages = True

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        result = None
        for chunk in self.truncate_message(content, self.MAX_MESSAGE_LENGTH):
            result = await super().send(chat_id, chunk, reply_to=reply_to, metadata=metadata)
            if not result.success:
                return result
        return result


class _FactoryOverride:
    """Passes everything through to the real plugin context, except that register_platform()
    gets our adapter factory instead of the bundled one."""

    def __init__(self, ctx):
        self._ctx = ctx

    def __getattr__(self, name):
        return getattr(self._ctx, name)

    def register_platform(self, **kwargs):
        kwargs["adapter_factory"] = lambda cfg: ChunkingNtfyAdapter(cfg)
        return self._ctx.register_platform(**kwargs)


def register(ctx) -> None:
    """Plugin entry point: the bundled registration, with the chunking adapter."""
    _bundled.register(_FactoryOverride(ctx))
