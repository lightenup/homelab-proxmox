#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

class EvidenceDiff:
    def __init__(self, path_a: str, path_b: str):
        self.path_a = Path(path_a)
        self.path_b = Path(path_b)
        self.data_a: Dict[str, Any] = {}
        self.data_b: Dict[str, Any] = {}
        self.diff_report: Dict[str, Any] = {}

    def load_pack(self, path: Path) -> Optional[Dict[str, Any]]:
        data = {}
        try:
            with open(path / "summary.json", 'r') as f:
                data['summary'] = json.load(f)
            with open(path / "checks.json", 'r') as f:
                data['checks'] = json.load(f)
            return data
        except Exception as e:
            print(f"Error loading pack {path}: {e}", file=sys.stderr)
            return None

    def run(self) -> bool:
        self.data_a = self.load_pack(self.path_a)
        self.data_b = self.load_pack(self.path_b)

        if not self.data_a or not self.data_b:
            return False

        # FR-010: Profile Mismatch Check
        profile_a = self.data_a['summary'].get('profile_id')
        profile_b = self.data_b['summary'].get('profile_id')

        if profile_a != profile_b:
            print(f"Error: Profile mismatch. {self.path_a.name} ({profile_a}) != {self.path_b.name} ({profile_b})", file=sys.stderr)
            return False

        # Compare Checks
        raw_checks_a = self.data_a['checks']
        checks_list_a = raw_checks_a['checks'] if isinstance(raw_checks_a, dict) and 'checks' in raw_checks_a else raw_checks_a
        
        raw_checks_b = self.data_b['checks']
        checks_list_b = raw_checks_b['checks'] if isinstance(raw_checks_b, dict) and 'checks' in raw_checks_b else raw_checks_b

        checks_a = {c['check_id']: c for c in checks_list_a}
        checks_b = {c['check_id']: c for c in checks_list_b}

        all_ids = set(checks_a.keys()) | set(checks_b.keys())
        
        new_checks = []
        missing_checks = []
        status_changes = []
        
        for check_id in sorted(all_ids):
            if check_id not in checks_a:
                new_checks.append({
                    "check_id": check_id,
                    "result": checks_b[check_id]['result']
                })
            elif check_id not in checks_b:
                missing_checks.append({
                    "check_id": check_id,
                    "result": checks_a[check_id]['result']
                })
            else:
                res_a = checks_a[check_id]['result']
                res_b = checks_b[check_id]['result']
                if res_a != res_b:
                    status_changes.append({
                        "check_id": check_id,
                        "from": res_a,
                        "to": res_b
                    })

        self.diff_report = {
            "run_a": self.path_a.name,
            "run_b": self.path_b.name,
            "profile_id": profile_a,
            "new_checks": new_checks,
            "missing_checks": missing_checks,
            "status_changes": status_changes
        }
        
        return True

    def report(self):
        # Write report
        # FR-009a: Output to artifacts/019-lab/diff-<runA>-<runB>/
        # We need to find repo root or use a relative path.
        # Assuming script is in scripts/lab/, repo root is ../..
        repo_root = Path(__file__).parent.parent.parent
        diff_dir = repo_root / "artifacts" / "019-lab" / f"diff-{self.path_a.name}-{self.path_b.name}"
        diff_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = diff_dir / "reports" / "diff.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w') as f:
            json.dump(self.diff_report, f, indent=2)
            
        print(f"Diff Report generated at: {report_path}")
        print("\n=== Diff Summary ===")
        print(f"Run A: {self.path_a.name}")
        print(f"Run B: {self.path_b.name}")
        print(f"Profile: {self.diff_report['profile_id']}")
        print("")
        
        if self.diff_report['status_changes']:
            print("Status Changes:")
            for change in self.diff_report['status_changes']:
                print(f"  {change['check_id']}: {change['from']} -> {change['to']}")
        else:
            print("No status changes.")
            
        if self.diff_report['new_checks']:
            print("\nNew Checks:")
            for check in self.diff_report['new_checks']:
                print(f"  {check['check_id']} ({check['result']})")
                
        if self.diff_report['missing_checks']:
            print("\nMissing Checks:")
            for check in self.diff_report['missing_checks']:
                print(f"  {check['check_id']} ({check['result']})")

def main():
    parser = argparse.ArgumentParser(description="Diff Evidence Packs")
    parser.add_argument("run_a", help="Path to first evidence pack")
    parser.add_argument("run_b", help="Path to second evidence pack")
    
    args = parser.parse_args()
    
    diff = EvidenceDiff(args.run_a, args.run_b)
    if diff.run():
        diff.report()
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
