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
        # FR-002: Check required files
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
        
        # FR-002a: Parse JSON files
        self.data['summary'] = self.load_json("summary.json")
        self.data['checks'] = self.load_json("checks.json")
        self.data['provenance'] = self.load_json("provenance.json")
        self.data['evidence_manifest'] = self.load_json("evidence_manifest.json")
        
        # If summary is missing or invalid, we can't do much coherence checking
        if not self.data.get('summary'):
            return

        summary = self.data['summary']
        
        # FR-001: Contract Version
        contract_version = summary.get('contract_version')
        if not contract_version:
            self.add_error("CONTRACT-002", "Missing contract_version in summary.json", "Update pve-lab to inject contract_version")
        else:
            # FR-001b: Version check
            try:
                major, minor, patch = map(int, contract_version.split('.'))
                if major != 1:
                    self.add_error("CONTRACT-001", f"Unsupported contract major version: {major}", "Verifier supports version 1.x.x")
            except ValueError:
                self.add_error("CONTRACT-003", f"Invalid contract_version format: {contract_version}", "Use SemVer format MAJOR.MINOR.PATCH")

        run_id = summary.get('run_id')
        profile_id = summary.get('profile_id')

        # FR-002b: Run ID Coherence
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

        # checks.json is a list, so we can't check run_id easily unless it's in the list items or metadata
        # The spec says "matches checks.run_id (if present)". 
        # Usually checks.json is a list of checks. 
        # If it's a dict with metadata, we check it.
        # Based on checks.sh, it's a list of check objects.
        # Check objects don't seem to have run_id.
        # So we skip checks.run_id check for now unless we find it.

        # FR-002c: Profile ID Coherence
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

        summary = self.data.get('summary', {})
        allow_deprecated = summary.get('allow_deprecated_checks', False)

        for check in checks:
            check_id = check.get('check_id')
            if not check_id:
                self.add_error("EVID-004", "Check missing check_id", "Ensure all checks have check_id")
                continue

            # FR-006: Check existence in catalog
            if check_id not in self.catalog:
                self.add_error(
                    "CAT-003",
                    f"Unknown check_id: {check_id}",
                    f"Add {check_id} to catalog.json or fix typo"
                )
                continue

            catalog_entry = self.catalog[check_id]

            # FR-006a: Deprecation
            if catalog_entry.get('deprecated', False) and not allow_deprecated:
                self.add_error(
                    "CAT-004",
                    f"Deprecated check_id: {check_id}",
                    f"Remove {check_id} or set allow_deprecated_checks=true in summary.json"
                )

            # FR-007: Ownership
            source = check.get('source')
            catalog_owner = catalog_entry.get('owner')
            
            if not source:
                self.add_error("OWN-002", f"Check {check_id} missing source field", "Ensure emitter adds source field")
            else:
                # FR-007a: source must be ansible or harness
                if source not in ["ansible", "harness"]:
                    self.add_error("OWN-003", f"Invalid source '{source}' for {check_id}", "Source must be 'ansible' or 'harness'")
                
                # FR-007b: Source vs Catalog Owner
                if catalog_owner == "ansible" and source != "ansible":
                    self.add_error("OWN-003", f"Owner mismatch for {check_id}: catalog says 'ansible' but source is '{source}'", "Fix source in emitter or owner in catalog")
                elif catalog_owner == "harness" and source != "harness":
                    self.add_error("OWN-002", f"Owner mismatch for {check_id}: catalog says 'harness' but source is '{source}'", "Fix source in emitter or owner in catalog")

                # FR-007c: Ansible Provenance Proof
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
                    # TODO: Parse assertion report to confirm check_id exists (FR-007c part 2)
                
                # FR-007d: Harness Ownership Guard
                elif catalog_owner == "harness":
                    # Should not rely on assertion reports
                    has_report = any("reports/assertions" in ref for ref in evidence_refs)
                    if has_report:
                        self.add_error(
                            "OWN-005",
                            f"Harness check {check_id} references assertion report",
                            "Harness checks should not rely on Ansible assertion reports"
                        )

            # FR-005b: Title Strictness
            title = check.get('title')
            catalog_title = catalog_entry.get('title')
            if title and title != catalog_title:
                self.add_error(
                    "CAT-005",
                    f"Title mismatch for {check_id}",
                    f"Expected: '{catalog_title}', Got: '{title}'. Update emitter to match catalog."
                )

            # FR-005c: Phase Required
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

            # FR-005d: Severity Handling
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

            # FR-004: Uniqueness
            if check_id in seen_ids:
                self.add_error(
                    "DEDUP-001",
                    f"Duplicate check_id found: {check_id}",
                    "Ensure check_ids are unique within the pack"
                )
            seen_ids.add(check_id)

            # FR-003: Evidence Refs
            evidence_refs = check.get('evidence_refs', [])
            result = check.get('result')
            
            # Get allow_missing_evidence from catalog
            catalog_entry = self.catalog.get(check_id, {})
            allow_missing = catalog_entry.get('allow_missing_evidence', False)

            for ref in evidence_refs:
                # Handle prefixes (019e1)
                clean_ref = ref
                if ref.startswith('file:'):
                    clean_ref = ref[5:].strip()
                elif ref.startswith('source:'):
                    # Metadata ref, skip file check
                    continue

                # FR-003a: Relative paths
                if clean_ref.startswith('/') or '..' in clean_ref:
                    # Special case for collision_id (see T001 discussion)
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
                    # FR-003b: Missing evidence
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
        # 1. Load Catalog
        if not self.load_catalog():
            return False

        # 2. Validate Structure (T006)
        self.validate_structure()

        # 3. Validate Catalog Compliance (T007)
        self.validate_catalog()

        # 4. Validate Integrity (T008)
        self.validate_integrity()

        return len(self.errors) == 0

    def report(self):
        summary = self.data.get('summary', {})
        contract_version = summary.get('contract_version', '1.0.0')
        
        report_data = {
            "status": "PASS" if not self.errors else "FAIL",
            "errors": self.errors,
            "warnings": self.warnings,
            "contract_version": contract_version,
            "verifier_version": "1.0.0",
            "timestamp": datetime.now().isoformat()
        }
        
        # Write report
        report_path = self.pack_path / "reports" / "verify.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2)
            
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
