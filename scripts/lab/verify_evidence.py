#!/usr/bin/env python3
import argparse
import json
import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Constants
REQUIRED_FILES = [
    "checks.json",
    "summary.json",
    "provenance.json",
    "evidence_manifest.json",
    "logs/events.jsonl"
]


def _required_files_for_profile(profile_id: str) -> List[str]:
    # Profile-specific required inputs.
    # Note: reports/verify.json is produced by the verifier itself and must not be
    # required to exist before verification runs.
    if profile_id == "service-deploy":
        return [
            "reports/plan/plan.txt",
            "reports/plan/plan.json",
            "preflight.txt",
            "blast-radius.json",
        ]

    return []


def _parse_condition(condition: str) -> Optional[Dict[str, str]]:
    """Parse simple conditions like: environment == 'prod' or environment != 'prod'."""
    m = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(==|!=)\s*'([^']*)'\s*$", condition)
    if not m:
        return None
    return {"var": m.group(1), "op": m.group(2), "value": m.group(3)}


def _eval_condition(condition: str, context: Dict[str, Any]) -> bool:
    parsed = _parse_condition(condition)
    if not parsed:
        return False
    actual = str(context.get(parsed["var"], ""))
    if parsed["op"] == "==":
        return actual == parsed["value"]
    if parsed["op"] == "!=":
        return actual != parsed["value"]
    return False


def _is_rfc3339_datetime(value: str) -> bool:
    try:
        # Accept trailing Z
        if value.endswith("Z"):
            datetime.fromisoformat(value[:-1] + "+00:00")
        else:
            datetime.fromisoformat(value)
        return True
    except Exception:
        return False


def _validate_schema_subset(schema: Dict[str, Any], instance: Any, path: str = "$") -> List[str]:
    """Validate instance against a small subset of JSON Schema draft-07.

    Supported: type, required, properties, patternProperties, items, enum, minimum,
    minLength, pattern, additionalProperties:false, format:date-time.
    """
    errors: List[str] = []

    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append(f"{path}: value {instance!r} not in enum {schema['enum']!r}")
            return errors

    expected_type = schema.get("type")
    if expected_type:
        if expected_type == "object":
            if not isinstance(instance, dict):
                return [f"{path}: expected object"]
        elif expected_type == "array":
            if not isinstance(instance, list):
                return [f"{path}: expected array"]
        elif expected_type == "string":
            if not isinstance(instance, str):
                return [f"{path}: expected string"]
        elif expected_type == "integer":
            if not (isinstance(instance, int) and not isinstance(instance, bool)):
                return [f"{path}: expected integer"]
        elif expected_type == "number":
            if not (isinstance(instance, (int, float)) and not isinstance(instance, bool)):
                return [f"{path}: expected number"]
        elif expected_type == "boolean":
            if not isinstance(instance, bool):
                return [f"{path}: expected boolean"]

    if expected_type == "string":
        if "minLength" in schema and len(instance) < int(schema["minLength"]):
            errors.append(f"{path}: string length < {schema['minLength']}")
        if "pattern" in schema:
            if re.match(schema["pattern"], instance) is None:
                errors.append(f"{path}: string does not match pattern {schema['pattern']!r}")
        if schema.get("format") == "date-time":
            if not _is_rfc3339_datetime(instance):
                errors.append(f"{path}: string is not valid date-time")

    if expected_type == "integer":
        if "minimum" in schema and instance < int(schema["minimum"]):
            errors.append(f"{path}: value {instance} < minimum {schema['minimum']}")

    if expected_type == "object":
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")

        properties = schema.get("properties", {})
        pattern_properties = schema.get("patternProperties", {})

        for key, sub_schema in properties.items():
            if key in instance:
                errors.extend(_validate_schema_subset(sub_schema, instance[key], f"{path}.{key}"))

        compiled_patterns: List[tuple[re.Pattern[str], Dict[str, Any]]] = []
        for pat, sub_schema in pattern_properties.items():
            try:
                compiled_patterns.append((re.compile(pat), sub_schema))
            except re.error:
                errors.append(f"{path}: invalid patternProperties regex {pat!r}")

        for key, value in instance.items():
            if key in properties:
                continue
            matched = False
            for regex_obj, sub_schema in compiled_patterns:
                if regex_obj.match(key):
                    matched = True
                    errors.extend(_validate_schema_subset(sub_schema, value, f"{path}.{key}"))
            if schema.get("additionalProperties") is False and not matched:
                errors.append(f"{path}: additional property {key!r} not allowed")

    if expected_type == "array":
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(instance):
                errors.extend(_validate_schema_subset(items_schema, item, f"{path}[{i}]"))

    return errors


def _load_evidence_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    script_dir = Path(__file__).parent
    profile_path = script_dir / "profiles.d" / f"{profile_id}.json"
    if not profile_path.exists():
        return None
    try:
        with open(profile_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _profile_required_paths(profile: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
    required: List[str] = []
    for entry in profile.get("required_fields", []) or []:
        path = entry.get("path")
        if path:
            required.append(path)

    for entry in profile.get("conditional_fields", []) or []:
        path = entry.get("path")
        cond = entry.get("condition", "")
        if path and cond and _eval_condition(cond, context):
            required.append(path)

    return required

class VerificationError(Exception):
    def __init__(self, code: str, message: str, remediation: str):
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"[{code}] {message}")

class EvidenceVerifier:
    def __init__(self, pack_path: str, strict_catalog: bool = True):
        self.pack_path = Path(pack_path)
        self.strict_catalog = strict_catalog
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []
        self.data: Dict[str, Any] = {}
        self.catalog: Dict[str, Any] = {}

    def add_error(self, code: str, message: str, remediation: str):
        self.errors.append({
            "code": code,
            "message": message,
            "remediation": remediation
        })

    def add_warning(self, code: str, message: str, remediation: str):
        self.warnings.append({
            "code": code,
            "message": message,
            "remediation": remediation
        })

    def load_json(self, filename: str) -> Optional[Any]:
        path = self.pack_path / filename
        if not path.exists():
            return None
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            self.add_error(
                "JSON-001",
                f"Failed to parse {filename}: {str(e)}",
                f"Fix JSON syntax in {filename}"
            )
            return None
        except Exception as e:
            self.add_error(
                "JSON-002",
                f"Error reading {filename}: {str(e)}",
                f"Check file permissions and integrity for {filename}"
            )
            return None

    def load_catalog(self) -> bool:
        # Assuming catalog is at scripts/lab/checks.d/catalog.json relative to repo root
        # We need to find repo root. Assuming script is in scripts/lab/
        script_dir = Path(__file__).parent
        catalog_path = script_dir / "checks.d" / "catalog.json"

        if not catalog_path.exists():
            self.add_error(
                "CAT-001",
                f"Catalog not found at {catalog_path}",
                "Ensure scripts/lab/checks.d/catalog.json exists"
            )
            return False

        try:
            with open(catalog_path, 'r') as f:
                self.catalog = json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.add_error(
                "CAT-002",
                f"Failed to parse catalog: {str(e)}",
                "Fix JSON syntax in catalog.json"
            )
            return False

    def validate_structure(self):
        missing_files = []
        for filename in REQUIRED_FILES:
            if not (self.pack_path / filename).exists():
                missing_files.append(filename)

        # If critical files are missing, we might not be able to proceed with other checks,
        # but we try to load what we can to surface more actionable errors.

        self.data['summary'] = self.load_json("summary.json")
        self.data['checks'] = self.load_json("checks.json")
        self.data['provenance'] = self.load_json("provenance.json")
        self.data['evidence_manifest'] = self.load_json("evidence_manifest.json")

        # If summary is missing or invalid, we can't do much coherence checking
        if not self.data.get('summary'):
            return

        summary = self.data['summary']

        contract_version = summary.get('contract_version')
        if not contract_version:
            self.add_error("CONTRACT-002", "Missing contract_version in summary.json", "Update pve-lab to inject contract_version")
        else:
            try:
                major, minor, patch = map(int, contract_version.split('.'))
                if major != 1:
                    self.add_error("CONTRACT-001", f"Unsupported contract major version: {major}", "Verifier supports version 1.x.x")
            except ValueError:
                self.add_error("CONTRACT-003", f"Invalid contract_version format: {contract_version}", "Use SemVer format MAJOR.MINOR.PATCH")

        run_id = summary.get('run_id')
        profile_id = summary.get('profile_id')

        provenance = self.data.get('provenance') or {}
        environment = provenance.get('environment') or "lab"
        context = {"environment": environment}

        if profile_id:
            evidence_profile = _load_evidence_profile(profile_id)
            if evidence_profile:
                for filename in _profile_required_paths(evidence_profile, context):
                    if not (self.pack_path / filename).exists():
                        missing_files.append(filename)
            else:
                for filename in _required_files_for_profile(profile_id):
                    if not (self.pack_path / filename).exists():
                        missing_files.append(filename)

        if missing_files:
            self.add_error(
                "STRUCT-001",
                f"Missing required files: {', '.join(sorted(set(missing_files)))}",
                "Ensure evidence pack contains all required files for its profile"
            )

        # Schema validation for new reports
        if profile_id == "service-deploy":
            self._validate_report_schema(
                report_relpath="reports/lab-snapshot.json",
                schema_filename="evidence-lab-snapshot.schema.json",
                error_code="SCHEMA-001",
                remediation="Regenerate reports/lab-snapshot.json to match schema"
            )

            if environment in ("prod", "lab"):
                env_tfvars_dir = f"reports/{environment}-tfvars"
                env_upper = environment.upper()

                self._validate_report_schema(
                    report_relpath=f"{env_tfvars_dir}/validation.json",
                    schema_filename="evidence-tfvars-proof.schema.json",
                    error_code="SCHEMA-002",
                    remediation=f"Regenerate {env_tfvars_dir}/validation.json to match schema"
                )

                proof = self.load_json(f"{env_tfvars_dir}/validation.json")
                if isinstance(proof, dict):
                    if proof.get("validation_status") != "pass":
                        self.add_error(
                            "TFVARS-001",
                            f"{env_upper} tfvars validation_status is not 'pass'",
                            f"Fix {environment}.tfvars provisioning/inputs and re-run so validation_status becomes 'pass'"
                        )

                    if proof.get("secret_present") is not True:
                        self.add_error(
                            "TFVARS-002",
                            f"{env_upper} tfvars secret_present is false",
                            "Ensure PROXMOX_API_TOKEN_SECRET (or PROXMOX_TOKEN_SECRET) is set and not a placeholder"
                        )

                sha_path = self.pack_path / f"{env_tfvars_dir}/{environment}.tfvars.sha256"
                if sha_path.exists():
                    try:
                        sha = sha_path.read_text(encoding="utf-8").strip()
                    except Exception:
                        sha = ""
                    if re.fullmatch(r"[a-f0-9]{64}", sha or "") is None:
                        self.add_error(
                            "TFVARS-003",
                            f"{env_upper} tfvars sha256 file is invalid (expected 64 lowercase hex chars)",
                            f"Regenerate {env_tfvars_dir}/{environment}.tfvars.sha256 from a valid {environment}.tfvars"
                        )

        dir_name = self.pack_path.name
        if run_id != dir_name:
            self.add_error(
                "EVID-002",
                f"Run ID mismatch: summary.run_id '{run_id}' != directory name '{dir_name}'",
                "Rename directory to match run_id or fix summary.json"
            )

        if self.data.get('provenance'):
            prov_run_id = self.data['provenance'].get('run_id')
            if prov_run_id and prov_run_id != run_id:
                self.add_error(
                    "EVID-002",
                    f"Run ID mismatch: summary.run_id '{run_id}' != provenance.run_id '{prov_run_id}'",
                    "Ensure all artifacts belong to the same run"
                )

        # checks.json is a list of checks; run_id is validated via summary/provenance.
        if not profile_id:
            self.add_error(
                "EVID-003",
                "Missing profile_id in summary.json",
                "Ensure summary.json includes profile_id"
            )
        else:
            if self.data.get('provenance'):
                prov_profile_id = self.data['provenance'].get('profile_id')
                if prov_profile_id and prov_profile_id != profile_id:
                    self.add_error(
                        "EVID-003",
                        f"Profile ID mismatch: summary.profile_id '{profile_id}' != provenance.profile_id '{prov_profile_id}'",
                        "Ensure all artifacts belong to the same profile"
                    )

    def _validate_report_schema(self, report_relpath: str, schema_filename: str, error_code: str, remediation: str):
        report_path = self.pack_path / report_relpath
        if not report_path.exists():
            return

        schema_path = Path(__file__).parent / "contracts" / schema_filename
        if not schema_path.exists():
            self.add_error(
                error_code,
                f"Schema file missing: {schema_path}",
                f"Ensure {schema_filename} exists under scripts/lab/contracts/"
            )
            return

        report_data = self.load_json(report_relpath)
        if report_data is None:
            return

        try:
            with open(schema_path, "r") as f:
                schema = json.load(f)
        except Exception as exc:
            self.add_error(
                error_code,
                f"Failed to load schema {schema_filename}: {exc}",
                f"Fix schema JSON: {schema_filename}"
            )
            return

        schema_errors = _validate_schema_subset(schema, report_data)
        if schema_errors:
            self.add_error(
                error_code,
                f"Schema validation failed for {report_relpath}: " + "; ".join(schema_errors[:5]),
                remediation
            )

    def validate_catalog(self):
        if not self.data.get('checks'):
            return

        checks_data = self.data['checks']
        if isinstance(checks_data, dict) and 'checks' in checks_data:
            checks = checks_data['checks']
        elif isinstance(checks_data, list):
            checks = checks_data
        else:
            self.add_error("JSON-003", "checks.json must be a list or object with 'checks' array", "Fix checks.json structure")
            return

        # Handle missing/None summary gracefully to avoid AttributeError
        summary = self.data.get('summary') or {}
        allow_deprecated = summary.get('allow_deprecated_checks', False)

        for check in checks:
            check_id = check.get('check_id')
            if not check_id:
                self.add_error("EVID-004", "Check missing check_id", "Ensure all checks have check_id")
                continue

            if check_id not in self.catalog:
                self.add_error(
                    "CAT-003",
                    f"Unknown check_id: {check_id}",
                    f"Add {check_id} to catalog.json or fix typo"
                )
                continue

            catalog_entry = self.catalog[check_id]

            if catalog_entry.get('deprecated', False) and not allow_deprecated:
                self.add_error(
                    "CAT-004",
                    f"Deprecated check_id: {check_id}",
                    f"Remove {check_id} or set allow_deprecated_checks=true in summary.json"
                )

            source = check.get('source')
            catalog_owner = catalog_entry.get('owner')

            if not source:
                self.add_error("OWN-002", f"Check {check_id} missing source field", "Ensure emitter adds source field")
            else:
                if source not in ["ansible", "harness"]:
                    self.add_error("OWN-003", f"Invalid source '{source}' for {check_id}", "Source must be 'ansible' or 'harness'")

                if catalog_owner == "ansible" and source != "ansible":
                    self.add_error("OWN-003", f"Owner mismatch for {check_id}: catalog says 'ansible' but source is '{source}'", "Fix source in emitter or owner in catalog")
                elif catalog_owner == "harness" and source != "harness":
                    self.add_error("OWN-002", f"Owner mismatch for {check_id}: catalog says 'harness' but source is '{source}'", "Fix source in emitter or owner in catalog")

                evidence_refs = check.get('evidence_refs', [])
                if catalog_owner == "ansible":
                    # Must include assertions report
                    has_report = any("reports/assertions" in ref for ref in evidence_refs)
                    if not has_report:
                        self.add_error(
                            "OWN-004",
                            f"Ansible check {check_id} missing assertion report ref",
                            "Ensure ansible checks reference reports/assertions.<phase>.json"
                        )

                elif catalog_owner == "harness":
                    # Should not rely on assertion reports
                    has_report = any("reports/assertions" in ref for ref in evidence_refs)
                    if has_report:
                        self.add_error(
                            "OWN-005",
                            f"Harness check {check_id} references assertion report",
                            "Harness checks should not rely on Ansible assertion reports"
                        )

            title = check.get('title')
            catalog_title = catalog_entry.get('title')
            if title and title != catalog_title:
                self.add_error(
                    "CAT-005",
                    f"Title mismatch for {check_id}",
                    f"Expected: '{catalog_title}', Got: '{title}'. Update emitter to match catalog."
                )

            phase = check.get('phase')
            catalog_phase = catalog_entry.get('phase')
            if not phase:
                self.add_error("CAT-007", f"Check {check_id} missing phase", "Ensure emitter adds phase field")
            elif phase != catalog_phase:
                self.add_error(
                    "CAT-006",
                    f"Phase mismatch for {check_id}",
                    f"Expected: '{catalog_phase}', Got: '{phase}'. Update emitter or catalog."
                )

            severity = check.get('severity')
            catalog_severity = catalog_entry.get('severity')
            if severity and severity != catalog_severity:
                self.add_error(
                    "CAT-008",
                    f"Severity mismatch for {check_id}",
                    f"Expected: '{catalog_severity}', Got: '{severity}'. Update emitter or catalog."
                )

    def validate_integrity(self):
        if not self.data.get('checks'):
            return

        checks_data = self.data['checks']
        if isinstance(checks_data, dict) and 'checks' in checks_data:
            checks = checks_data['checks']
        elif isinstance(checks_data, list):
            checks = checks_data
        else:
            # Already reported in validate_catalog
            return

        seen_ids = set()

        for check in checks:
            check_id = check.get('check_id')
            if not check_id:
                continue

            if check_id in seen_ids:
                self.add_error(
                    "DEDUP-001",
                    f"Duplicate check_id found: {check_id}",
                    "Ensure check_ids are unique within the pack"
                )
            seen_ids.add(check_id)

            evidence_refs = check.get('evidence_refs', [])
            result = check.get('result')

            # Get allow_missing_evidence from catalog
            catalog_entry = self.catalog.get(check_id, {})
            allow_missing = catalog_entry.get('allow_missing_evidence', False)

            for ref in evidence_refs:
                clean_ref = ref
                if ref.startswith('file:'):
                    clean_ref = ref[5:].strip()
                elif ref.startswith('source:'):
                    # Metadata ref, skip file check
                    continue

                if clean_ref.startswith('/') or '..' in clean_ref:
                    if clean_ref.startswith('collision_id:'):
                        continue

                    self.add_error(
                        "REF-001",
                        f"Invalid evidence ref '{ref}' in {check_id}",
                        "Evidence refs must be relative paths without '..'"
                    )
                    continue

                ref_path = self.pack_path / clean_ref
                if not ref_path.exists():
                    if result == "PASS":
                        self.add_error(
                            "REF-002",
                            f"Missing evidence '{ref}' for PASS check {check_id}",
                            "Ensure all evidence files exist for passing checks"
                        )
                    elif result == "FAIL":
                        if not allow_missing:
                            self.add_error(
                                "REF-003",
                                f"Missing evidence '{ref}' for FAIL check {check_id}",
                                f"Ensure evidence exists or set allow_missing_evidence=true in catalog for {check_id}"
                            )

    def run(self) -> bool:
        if not self.load_catalog():
            return False

        self.validate_structure()

        self.validate_catalog()

        self.validate_integrity()

        return len(self.errors) == 0

    def report(self):
        summary = self.data.get('summary') or {}
        contract_version = summary.get('contract_version', '1.0.0')

        status = "PASS" if not self.errors else "FAIL"
        reason = ""
        if status != "PASS":
            reason = "; ".join(err.get('message', '') for err in self.errors if err.get('message'))

        report_data = {
            "status": status,
            "errors": self.errors,
            "warnings": self.warnings,
            "contract_version": contract_version,
            "verifier_version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "reasons": [reason] if reason else []
        }

        # Write report
        report_path = self.pack_path / "reports" / "verify.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2)
            f.write('\n')

        # Update summary with verification block
        try:
            summary_path = self.pack_path / "summary.json"
            summary_content = summary if summary else {}
            summary_content.setdefault("contract_version", contract_version)
            summary_content["verification"] = {
                "status": status,
                "report_path": "reports/verify.json",
                "verifier_version": "1.0.0",
                "reason": reason
            }
            with open(summary_path, 'w') as sf:
                json.dump(summary_content, sf, indent=2)
                sf.write('\n')
        except Exception as exc:
            # Non-fatal; emit warning
            self.add_warning("SUMMARY-001", f"Failed to update summary.json: {exc}", "Manually add verification block to summary.json")

        # Console Output
        print(f"Verification Status: {report_data['status']}")
        if self.errors:
            print("\nErrors:")
            for err in self.errors:
                print(f"  [{err['code']}] {err['message']}")
                print(f"    -> Remediation: {err['remediation']}")

        if self.warnings:
            print("\nWarnings:")
            for warn in self.warnings:
                print(f"  [{warn['code']}] {warn['message']}")

def main():
    parser = argparse.ArgumentParser(description="Verify Evidence Pack")
    parser.add_argument("pack_path", help="Path to evidence pack directory")
    parser.add_argument("--strict-catalog", action="store_true", default=True, help="Enforce strict catalog validation")
    parser.add_argument("--no-strict-catalog", action="store_false", dest="strict_catalog", help="Disable strict catalog validation")

    args = parser.parse_args()

    verifier = EvidenceVerifier(args.pack_path, args.strict_catalog)
    success = verifier.run()
    verifier.report()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
