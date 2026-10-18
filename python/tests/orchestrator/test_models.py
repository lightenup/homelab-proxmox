from homelab_proxmox_orchestrator.models import EvidencePointer, RunResponse, RunSummary


def test_run_response_json_shape():
    resp = RunResponse(
        run_id="r1",
        service="ntfy",
        environment="lab",
        action="plan",
        status="succeeded",
        exit_code=0,
        summary=RunSummary(
            title="ok",
            bounded=True,
            highlights=["h"],
            warnings=[],
            errors=[],
            next_steps=["n"],
        ),
        evidence=[EvidencePointer(label="pack", location="/tmp/pack")],
    )

    doc = resp.to_json_dict()
    assert doc["runId"] == "r1"
    assert doc["summary"]["bounded"] is True
    assert doc["evidence"][0]["label"] == "pack"
