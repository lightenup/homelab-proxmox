#!/usr/bin/env python3
import argparse
import json
import sys
import os
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
        
        if missing_files:
            self.add_error(
                "STRUCT-001",
                f"Missing required files: {', '.join(missing_files)}",
                "Ensure evidence pack contains all required files"
            )
            # If critical files are missing, we might not be able to proceed with other checks
            # But we try to load what we can
        
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
