from homelab_proxmox_orchestrator.bounds import redact_secrets, truncate_text


def test_truncate_text_by_lines():
    text = "".join([f"line{i}\n" for i in range(10)])
    out, truncated = truncate_text(text, max_lines=3, max_bytes=10_000)
    assert truncated is True
    assert out.count("\n") == 3


def test_truncate_text_by_bytes():
    text = "x" * 1000
    out, truncated = truncate_text(text, max_lines=10_000, max_bytes=10)
    assert truncated is True
    assert len(out.encode("utf-8")) <= 10


def test_redact_hinty_key_value_pairs():
    text = "ANSIBLE_VAULT_PASSWORD=supersecret\napi_key: abc123\nfoo=ok\n"
    out = redact_secrets(text)
    assert "supersecret" not in out
    assert "abc123" not in out
    assert "foo=ok" in out
