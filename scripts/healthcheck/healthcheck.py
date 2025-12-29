#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import concurrent.futures
import urllib.request
import urllib.error
import ssl
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Dict, List, Any, Optional

def get_inventory(inventory_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get inventory from file or by executing ansible-inventory.
    """
    if inventory_path:
        try:
            with open(inventory_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading inventory file {inventory_path}: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        # Run ansible-inventory from the ansible directory to ensure host_vars are picked up correctly
        cmd = ["ansible-inventory", "-i", "inventories/generated/hosts.yml", "-i", "inventories/static/hosts.yml", "--list"]
        result = subprocess.run(cmd, cwd="ansible", capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running ansible-inventory: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing inventory JSON: {e}", file=sys.stderr)
        sys.exit(1)

def resolve_host_vars(inventory: Dict[str, Any], hostname: str) -> Dict[str, Any]:
    if "_meta" in inventory and "hostvars" in inventory["_meta"]:
        return inventory["_meta"]["hostvars"].get(hostname, {})
    return {}

def get_target_ip(host_vars: Dict[str, Any], profile: str) -> Optional[str]:
    if profile == "tailscale":
        return host_vars.get("tailscale_ip")
    else:
        return host_vars.get("ansible_host")

def perform_check(hostname: str, host_vars: Dict[str, Any], profile: str) -> Dict[str, Any]:
    path = host_vars.get("healthcheck_path")
    port = host_vars.get("healthcheck_port", 80)
    scheme = host_vars.get("healthcheck_scheme", "http")
    verify_ssl = host_vars.get("healthcheck_verify_ssl", True)
    expect_status = host_vars.get("healthcheck_expect_status", 200)
    expect_json_str = host_vars.get("healthcheck_expect_json")
    
    ip = get_target_ip(host_vars, profile)
    
    result = {
        "hostname": hostname,
        "target_ip": ip,
        "status": "FAIL",
        "details": "",
        "url": ""
    }

    if not ip:
        result["details"] = f"No IP found for profile '{profile}'"
        return result

    url = f"{scheme}://{ip}:{port}{path}"
    result["url"] = url

    # SSL Context
    ctx = ssl.create_default_context()
    if not verify_ssl:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(url)
        # Set a timeout
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            status_code = response.getcode()
            
            if status_code != expect_status:
                result["details"] = f"Status {status_code} != {expect_status}"
                return result

            if expect_json_str:
                body = response.read().decode('utf-8')
                try:
                    expect_json = json.loads(expect_json_str)
                    actual_json = json.loads(body)
                    # Simple subset check
                    for k, v in expect_json.items():
                        if actual_json.get(k) != v:
                            result["details"] = f"JSON mismatch: {k}={actual_json.get(k)} != {v}"
                            return result
                except json.JSONDecodeError:
                    result["details"] = "Response was not valid JSON"
                    return result
                except Exception as e:
                    result["details"] = f"JSON validation error: {str(e)}"
                    return result

            result["status"] = "PASS"
            return result

    except urllib.error.HTTPError as e:
        # HTTPError is also a valid response (e.g. 404, 500), check if it matches expectation
        if e.code == expect_status:
             result["status"] = "PASS"
             return result
        result["details"] = f"HTTP Error: {e.code} {e.reason}"
        return result
    except urllib.error.URLError as e:
        result["details"] = f"Connection error: {str(e.reason)}"
        return result
    except Exception as e:
        result["details"] = f"Error: {str(e)}"
        return result

def load_previous_history() -> Dict[str, str]:
    """
    Load the previous run's results to determine state changes.
    Returns a dict mapping hostname -> status (PASS/FAIL).
    """
    history_path = "artifacts/healthcheck/history/latest.json"
    if not os.path.exists(history_path):
        return {}
    
    try:
        with open(history_path, 'r') as f:
            data = json.load(f)
            # Handle both list of results and wrapped structure if we change it later
            if isinstance(data, list):
                return {r["hostname"]: r["status"] for r in data}
            return {}
    except Exception as e:
        print(f"Warning: Could not load history: {e}", file=sys.stderr)
        return {}

def send_email_notification(current_results: List[Dict[str, Any]], previous_states: Dict[str, str], coverage_failures: List[str]):
    """
    Send email notification if state changed from Success -> Failure or if coverage gaps exist.
    """
    smtp_host = os.environ.get("SMTP_HOST")
    if not smtp_host:
        return

    smtp_port = int(os.environ.get("SMTP_PORT", 25))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    smtp_from = os.environ.get("SMTP_FROM", "healthcheck@homelab.local")
    smtp_to = os.environ.get("SMTP_TO")

    if not smtp_to:
        print("Warning: SMTP_HOST set but SMTP_TO missing. Skipping email.", file=sys.stderr)
        return

    failures = []
    
    # Check for service regressions (Success -> Failure)
    for r in current_results:
        hostname = r["hostname"]
        status = r["status"]
        prev_status = previous_states.get(hostname, "PASS") # Default to PASS so we don't alert on first run unless it fails? 
        # Actually, if it's a new host and it fails, we probably want to know.
        # But spec says "State change only (Success -> Failure)".
        # If prev is unknown, maybe we shouldn't alert? Or maybe we should?
        # Let's stick to: Alert if Current is FAIL and (Prev was PASS or Unknown).
        # Wait, "Success -> Failure" implies we knew it was Success.
        # But if I deploy a new broken service, I want to know.
        # Let's alert if Status is FAIL.
        # Wait, the requirement is "State change only (Success -> Failure) ... prevents alert fatigue from repeated failures".
        # So if it was FAIL last time and is FAIL this time -> NO Alert.
        # If it was PASS last time and is FAIL this time -> Alert.
        # If it is New and FAIL -> Alert (treat missing history as PASS for the purpose of "it wasn't failing before").
        
        if status != "PASS" and prev_status == "PASS":
            failures.append(f"Service Regression: {hostname} ({r['details']})")

    # Check for coverage gaps (Always alert)
    for host in coverage_failures:
        failures.append(f"Coverage Gap: {host} (Missing healthcheck_path)")

    if not failures:
        return

    # Hooks for future integrations
    # notify_failure(failures) 

    msg = EmailMessage()
    msg.set_content("\n".join(failures))
    msg["Subject"] = f"Healthcheck Alert: {len(failures)} Issues Detected"
    msg["From"] = smtp_from
    msg["To"] = smtp_to

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_user and smtp_pass:
                server.starttls()
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Sent email notification to {smtp_to}")
    except Exception as e:
        print(f"Error sending email: {e}", file=sys.stderr)

def check_coverage(inventory: Dict[str, Any]) -> List[str]:
    """
    Check if hosts in enforced groups have healthcheck_path defined.
    Returns list of missing hosts.
    """
    missing_hosts = []
    
    # Get enforced groups from 'all' vars or default
    # Note: ansible-inventory --list puts group vars in the group dict or _meta
    # We might need to look up 'all' group vars.
    # Usually inventory['all']['vars']
    
    enforced_groups = ["services"] # Default
    if "all" in inventory and "vars" in inventory["all"]:
        enforced_groups = inventory["all"]["vars"].get("healthcheck_enforced_groups", enforced_groups)
    
    # Also check _meta hostvars for 'all' group vars if not in inventory['all']['vars']?
    # Ansible JSON format can vary. Let's assume standard.
    
    hostvars = inventory.get("_meta", {}).get("hostvars", {})
    
    # Generate baseline.json artifact (FR-008)
    baseline = {
        "timestamp": datetime.now().isoformat(),
        "targets": []
    }

    for group in enforced_groups:
        if group not in inventory:
            continue
            
        hosts = inventory[group].get("hosts", [])
        for hostname in hosts:
            hv = hostvars.get(hostname, {})
            if "healthcheck_path" not in hv:
                missing_hosts.append(hostname)
            else:
                baseline["targets"].append({
                    "hostname": hostname,
                    "url": f"{hv.get('healthcheck_scheme','http')}://{hv.get('ansible_host')}:{hv.get('healthcheck_port',80)}{hv.get('healthcheck_path')}"
                })

    # Save baseline artifact
    os.makedirs("artifacts/healthcheck", exist_ok=True)
    with open("artifacts/healthcheck/baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)

    return missing_hosts

def main():
    parser = argparse.ArgumentParser(description="Service Health Regression Checks")
    parser.add_argument("--profile", choices=["lan", "tailscale"], default="lan", help="Network profile to use")
    parser.add_argument("--json", action="store_true", help="Output JSON report to stdout")
    parser.add_argument("--output-json", help="Save JSON report to file")
    parser.add_argument("--filter", help="Filter hosts by name (substring)")
    parser.add_argument("--no-notify", action="store_true", help="Disable email notifications")
    parser.add_argument("--inventory", help="Path to JSON inventory file")
    args = parser.parse_args()

    inventory = get_inventory(args.inventory)
    
    # Run coverage check
    coverage_failures = check_coverage(inventory)
    if coverage_failures:
        print(f"Coverage Gaps Found: {', '.join(coverage_failures)}", file=sys.stderr)

    hosts_to_check = []
    if "_meta" in inventory and "hostvars" in inventory["_meta"]:
        all_hosts = inventory["_meta"]["hostvars"]
        for hostname, vars in all_hosts.items():
            if "healthcheck_path" in vars:
                if args.filter and args.filter not in hostname:
                    continue
                hosts_to_check.append(hostname)
    else:
        print("Invalid inventory format: missing _meta.hostvars", file=sys.stderr)
        sys.exit(1)

    results = []
    if hosts_to_check:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_host = {
                executor.submit(perform_check, h, resolve_host_vars(inventory, h), args.profile): h 
                for h in hosts_to_check
            }
            for future in concurrent.futures.as_completed(future_to_host):
                results.append(future.result())

        results.sort(key=lambda x: x["hostname"])

    if args.output_json:
        try:
            with open(args.output_json, 'w') as f:
                json.dump(results, f, indent=2)
        except IOError as e:
            print(f"Error writing JSON output to {args.output_json}: {e}", file=sys.stderr)

    # Notifications
    if not args.no_notify:
        previous_history = load_previous_history()
        send_email_notification(results, previous_history, coverage_failures)

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'HOSTNAME':<20} {'STATUS':<10} {'IP':<15} {'DETAILS'}")
        print("-" * 80)
        for r in results:
            status_color = "\033[92m" if r["status"] == "PASS" else "\033[91m"
            reset_color = "\033[0m"
            print(f"{r['hostname']:<20} {status_color}{r['status']:<10}{reset_color} {r['target_ip'] or 'N/A':<15} {r['details']}")
        
        if coverage_failures:
            print("-" * 80)
            print(f"COVERAGE GAPS: {len(coverage_failures)}")
            for h in coverage_failures:
                print(f"{h:<20} \033[91mMISSING\033[0m   N/A             Missing healthcheck_path")

    if any(r["status"] != "PASS" for r in results) or coverage_failures:
        sys.exit(1)

if __name__ == "__main__":
    main()
