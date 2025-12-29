#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import concurrent.futures
import urllib.request
import urllib.error
import ssl
from typing import Dict, List, Any, Optional

def get_inventory() -> Dict[str, Any]:
    """
    Execute ansible-inventory --list and return the JSON output.
    """
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

def main():
    parser = argparse.ArgumentParser(description="Service Health Regression Checks")
    parser.add_argument("--profile", choices=["lan", "tailscale"], default="lan", help="Network profile to use")
    parser.add_argument("--json", action="store_true", help="Output JSON report to stdout")
    parser.add_argument("--output-json", help="Save JSON report to file")
    parser.add_argument("--filter", help="Filter hosts by name (substring)")
    args = parser.parse_args()

    inventory = get_inventory()
    
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

    if not hosts_to_check:
        print("No hosts found with 'healthcheck_path' defined.")
        sys.exit(0)

    results = []
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

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'HOSTNAME':<20} {'STATUS':<10} {'IP':<15} {'DETAILS'}")
        print("-" * 80)
        for r in results:
            status_color = "\033[92m" if r["status"] == "PASS" else "\033[91m"
            reset_color = "\033[0m"
            print(f"{r['hostname']:<20} {status_color}{r['status']:<10}{reset_color} {r['target_ip'] or 'N/A':<15} {r['details']}")

    if any(r["status"] != "PASS" for r in results):
        sys.exit(1)

if __name__ == "__main__":
    main()
