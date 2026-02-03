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

def get_inventory(inventory_path: Optional[str] = None, host: Optional[str] = None) -> Dict[str, Any]:
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
        # Run ansible-inventory from the ansible directory to ensure host_vars are picked up correctly.
        # NOTE: `--list` loads the entire inventory (and therefore all group_vars/host_vars),
        # which can fail if unrelated hosts reference vault files not present in CI.
        if host:
            cmd = ["ansible-inventory", "-i", "inventories/generated/hosts.yml", "--host", host]
            result = subprocess.run(cmd, cwd="ansible", capture_output=True, text=True, check=True)
            hostvars = json.loads(result.stdout)
            return {
                "all": {"vars": {}},
                "services": {"hosts": [host]},
                "_meta": {"hostvars": {host: hostvars}},
            }

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

def get_service_config(host_vars: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize healthcheck configuration from either object or flat keys.
    Returns dict with keys: scheme, port, path, profile, verify_ssl, expect_status, expect_json, verification_command
    Returns None if no valid configuration found.
    """
    # New Object Structure
    url_obj = host_vars.get("healthcheck_url")
    if url_obj and isinstance(url_obj, dict):
        return {
            "scheme": url_obj.get("scheme", "http"),
            "port": url_obj.get("port", 80),
            "path": url_obj.get("path", "/"),
            "profile": host_vars.get("healthcheck_profile", "both"),
            "verify_ssl": host_vars.get("healthcheck_verify_ssl", True),
            "expect_status": host_vars.get("healthcheck_expect_status", 200),
            "expect_json": host_vars.get("healthcheck_expect_json"),
            "verification_command": host_vars.get("healthcheck_verification_command")
        }

    # Old Flat Structure (Fallback)
    if "healthcheck_path" in host_vars:
        return {
            "scheme": host_vars.get("healthcheck_scheme", "http"),
            "port": host_vars.get("healthcheck_port", 80),
            "path": host_vars.get("healthcheck_path"),
            "profile": host_vars.get("healthcheck_profile", "both"),
            "verify_ssl": host_vars.get("healthcheck_verify_ssl", True),
            "expect_status": host_vars.get("healthcheck_expect_status", 200),
            "expect_json": host_vars.get("healthcheck_expect_json"),
            "verification_command": host_vars.get("healthcheck_verification_command")
        }

    return None

def get_target_ip(host_vars: Dict[str, Any], profile: str) -> Optional[str]:
    if profile == "tailscale":
        return host_vars.get("tailscale_ip")
    else:
        return host_vars.get("ansible_host")

def perform_check(hostname: str, host_vars: Dict[str, Any], profile: str) -> Dict[str, Any]:
    # Check if healthcheck is enabled
    if not host_vars.get("healthcheck_enabled", True):
        return {
            "hostname": hostname,
            "target_ip": get_target_ip(host_vars, profile),
            "status": "SKIP",
            "details": f"Disabled: {host_vars.get('healthcheck_reason', 'No reason provided')}",
            "url": "N/A"
        }

    config = get_service_config(host_vars)

    # If no config found, this should have been caught as GAP in main loop if enforced,
    # or we shouldn't be here. But if we are here and no config:
    if not config:
        return {
            "hostname": hostname,
            "target_ip": "N/A",
            "status": "GAP",
            "details": "Missing healthcheck configuration",
            "url": "N/A"
        }

    svc_profile = config["profile"]

    # Profile Compatibility Check
    # If service is 'none', it's a special case (no HTTP check)
    if svc_profile == "none":
        cmd = config["verification_command"]
        if not cmd:
            return {
                "hostname": hostname,
                "target_ip": "N/A",
                "status": "SKIP",
                "details": "Profile 'none' but no verification command",
                "url": "N/A"
            }

        # Execute verification command
        try:
            # We run the command locally.
            # Note: host_vars are already substituted by ansible-inventory if they used Jinja2
            subprocess.run(cmd, shell=True, check=True, timeout=10, capture_output=True)
            return {
                "hostname": hostname,
                "target_ip": "N/A",
                "status": "PASS",
                "details": f"Command verified: {cmd}",
                "url": f"cmd://{cmd}"
            }
        except subprocess.CalledProcessError as e:
            return {
                "hostname": hostname,
                "target_ip": "N/A",
                "status": "FAIL",
                "details": f"Verification command failed: {e.stderr.decode('utf-8').strip() if e.stderr else 'Unknown error'}",
                "url": f"cmd://{cmd}"
            }
        except subprocess.TimeoutExpired:
             return {
                "hostname": hostname,
                "target_ip": "N/A",
                "status": "FAIL",
                "details": "Verification command timed out",
                "url": f"cmd://{cmd}"
            }

    # Profile Mismatch Check
    # lan service -> only checkable if profile=lan
    # tailscale service -> only checkable if profile=tailscale
    # both -> checkable by either
    if svc_profile != "both" and svc_profile != profile:
        return {
            "hostname": hostname,
            "target_ip": "N/A",
            "status": "SKIP",
            "details": f"Profile mismatch: Service={svc_profile}, Runner={profile}",
            "url": "N/A"
        }

    # Standard HTTP Check
    path = config["path"]
    port = config["port"]
    scheme = config["scheme"]
    verify_ssl = config["verify_ssl"]
    expect_status = config["expect_status"]
    expect_json_str = config["expect_json"]

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

def send_email_notification(current_results: List[Dict[str, Any]], previous_states: Dict[str, str], coverage_failures: List[str], alert_on_gap: bool = False):
    """
    Send email notification if state changed from Success -> Failure or if coverage gaps exist (and alerting enabled).
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

        if status == "SKIP":
            continue

        prev_status = previous_states.get(hostname, "PASS") # Default to PASS so we don't alert on first run unless it fails?

        if status != "PASS" and prev_status == "PASS":
            failures.append(f"Service Regression: {hostname} ({r['details']})")

    # Check for coverage gaps (Alert only if configured)
    if alert_on_gap:
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
    Check if hosts in enforced groups have healthcheck configuration defined.
    Returns list of missing hosts.
    """
    missing_hosts = []

    enforced_groups = ["services"] # Default
    if "all" in inventory and "vars" in inventory["all"]:
        enforced_groups = inventory["all"]["vars"].get("healthcheck_enforced_groups", enforced_groups)

    hostvars = inventory.get("_meta", {}).get("hostvars", {})

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
            config = get_service_config(hv)

            if not config:
                missing_hosts.append(hostname)
            else:
                # Construct URL for baseline
                if config["profile"] == "none":
                    url = f"cmd://{config.get('verification_command', 'unknown')}"
                else:
                    url = f"{config['scheme']}://{hv.get('ansible_host')}:{config['port']}{config['path']}"

                baseline["targets"].append({
                    "hostname": hostname,
                    "url": url
                })

    # Save baseline artifact
    os.makedirs("artifacts/healthcheck", exist_ok=True)
    with open("artifacts/healthcheck/baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)

    return missing_hosts

def validate_schema(hostname: str, host_vars: Dict[str, Any]) -> List[str]:
    errors = []

    # Check for deprecated keys
    deprecated_keys = ["healthcheck_path", "healthcheck_port", "healthcheck_scheme"]
    found_deprecated = [k for k in deprecated_keys if k in host_vars]
    if found_deprecated:
        errors.append(f"Deprecated keys found: {', '.join(found_deprecated)}. Use 'healthcheck_url' object.")

    # Check for new schema
    url_obj = host_vars.get("healthcheck_url")
    if url_obj:
        if not isinstance(url_obj, dict):
            errors.append("healthcheck_url must be a dictionary")
        else:
            required = ["scheme", "port", "path"]
            missing = [k for k in required if k not in url_obj]
            if missing:
                errors.append(f"healthcheck_url missing required keys: {', '.join(missing)}")

    # Check profile
    profile = host_vars.get("healthcheck_profile")
    if profile:
        if profile not in ["lan", "tailscale", "both", "none"]:
            errors.append(f"Invalid healthcheck_profile: {profile}")

        if profile == "none":
            if not host_vars.get("healthcheck_verification_command"):
                errors.append("healthcheck_profile is 'none' but 'healthcheck_verification_command' is missing")

    return errors

def main():
    parser = argparse.ArgumentParser(description="Service Health Regression Checks")
    parser.add_argument("--profile", choices=["lan", "tailscale"], default="lan", help="Network profile to use")
    parser.add_argument("--json", action="store_true", help="Output JSON report to stdout")
    parser.add_argument("--output-json", help="Save JSON report to file")
    parser.add_argument("--filter", help="Filter hosts by name (substring)")
    parser.add_argument("--host", action="append", help="Check an explicit host (repeatable); avoids loading full inventory")
    parser.add_argument("--no-notify", action="store_true", help="Disable email notifications")
    parser.add_argument("--alert-on-gap", action="store_true", help="Enable email alerts for coverage gaps")
    parser.add_argument("--inventory", help="Path to JSON inventory file")
    parser.add_argument("--check-drift", action="store_true", help="Check for configuration drift/schema violations")
    args = parser.parse_args()

    inventory = get_inventory(args.inventory, host=args.host[0] if args.host else None)

    if args.check_drift:
        drift_errors = {}
        if "_meta" in inventory and "hostvars" in inventory["_meta"]:
            all_hosts = inventory["_meta"]["hostvars"]
            for hostname, vars in all_hosts.items():
                # Only check if any healthcheck config exists (new or old)
                if "healthcheck_url" in vars or "healthcheck_path" in vars:
                    errs = validate_schema(hostname, vars)
                    if errs:
                        drift_errors[hostname] = errs
        else:
            print("Invalid inventory format: missing _meta.hostvars", file=sys.stderr)
            sys.exit(1)

        if drift_errors:
            print("Configuration Drift Detected:")
            for host, errs in drift_errors.items():
                print(f"{host}:")
                for e in errs:
                    print(f"  - {e}")
            sys.exit(1)
        else:
            print("No drift detected.")
            sys.exit(0)

    # Run coverage check
    coverage_failures = check_coverage(inventory)
    # We will add these as GAP results later

    hosts_to_check = []
    if "_meta" in inventory and "hostvars" in inventory["_meta"]:
        all_hosts = inventory["_meta"]["hostvars"]
        for hostname, vars in all_hosts.items():
            # Check if host has valid config using our helper
            if get_service_config(vars):
                if args.filter and args.filter not in hostname:
                    continue
                if args.host and hostname not in args.host:
                    continue
                hosts_to_check.append(hostname)
    else:
        print("Invalid inventory format: missing _meta.hostvars", file=sys.stderr)
        sys.exit(1)

    results = []

    # Add GAP results for coverage failures
    for h in coverage_failures:
        if args.filter and args.filter not in h:
            continue
        if args.host and h not in args.host:
            continue
        results.append({
            "hostname": h,
            "target_ip": "N/A",
            "status": "GAP",
            "details": "Missing healthcheck configuration",
            "url": "N/A"
        })

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
        send_email_notification(results, previous_history, coverage_failures, args.alert_on_gap)

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'HOSTNAME':<20} {'STATUS':<10} {'IP':<15} {'DETAILS'}")
        print("-" * 80)
        for r in results:
            status_color = "\033[92m" if r["status"] == "PASS" else ("\033[93m" if r["status"] == "SKIP" else ("\033[96m" if r["status"] == "GAP" else "\033[91m"))
            reset_color = "\033[0m"
            print(f"{r['hostname']:<20} {status_color}{r['status']:<10}{reset_color} {r['target_ip'] or 'N/A':<15} {r['details']}")

    # Exit 1 only if there are actual failures (not SKIPs).
    if any(r["status"] == "FAIL" for r in results):
        sys.exit(1)
    # Optional: Exit 1 on GAP if strict? For now, let's keep it as warning unless alert_on_gap is set?
    # But the previous code exited 1 if coverage_failures existed.
    if coverage_failures and args.alert_on_gap:
         sys.exit(1)

if __name__ == "__main__":
    main()
