#!/usr/bin/env python3
"""
Quant AI Agent Gateway & PWA Post-Deployment Smoke Test Suite
Probes all critical operational and Model Context Protocol (MCP) endpoints.
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error
import http.client


def probe_endpoint(base_url: str, method: str, path: str, payload: dict = None, timeout: float = 5.0) -> bool:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"User-Agent": "Quant-Smoke-Test-Runner/1.0"}
    data = None
    
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # Read first chunk if streaming / SSE
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                _ = response.readline()
            else:
                _ = response.read(1024)
            
            if status_code == 200:
                print(f"  ? PASS: [{method}] {path:<28} -> HTTP {status_code} ({elapsed_ms:.1f}ms)")
                return True
            else:
                print(f"  ? FAIL: [{method}] {path:<28} -> HTTP {status_code} ({elapsed_ms:.1f}ms) [Expected 200]")
                return False
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"  ? FAIL: [{method}] {path:<28} -> HTTP {e.code} ({elapsed_ms:.1f}ms) [Expected 200]")
        return False
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"  ? ERROR: [{method}] {path:<28} -> Exception: {e} ({elapsed_ms:.1f}ms)")
        return False


def main():
    parser = argparse.ArgumentParser(description="Probe Quant PWA / Gateway HTTP Endpoints for Smoke Verification")
    parser.add_argument("--host", default="127.0.0.1", help="Target server host IP or hostname (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Target server HTTP port (default: 8000)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout in seconds per probe (default: 5.0)")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    print("=" * 70)
    print(f"  QUANT AI GATEWAY SMOKE TEST RUNNER")
    print(f"  Target: {base_url}")
    print("=" * 70)

    endpoints = [
        ("GET", "/health", None),
        ("GET", "/api/health", None),
        ("GET", "/api/flow/status", None),
        ("GET", "/api/quant-levels/status", None),
        ("GET", "/mcp/sse", None),
        ("POST", "/mcp/sse", {"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        ("GET", "/mcp/messages", None),
        ("POST", "/mcp/messages", {"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        ("GET", "/mcp", None),
        ("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        ("GET", "/sse", None),
        ("POST", "/sse", {"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        ("GET", "/messages", None),
        ("POST", "/messages", {"jsonrpc": "2.0", "id": 1, "method": "ping"}),
    ]

    all_passed = True
    passed_count = 0
    total_count = len(endpoints)

    for method, path, payload in endpoints:
        ok = probe_endpoint(base_url, method, path, payload, timeout=args.timeout)
        if ok:
            passed_count += 1
        else:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print(f"  SMOKE TEST RESULTS: ALL {passed_count}/{total_count} ENDPOINTS RETURNED 200 OK")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"  SMOKE TEST RESULTS: {total_count - passed_count}/{total_count} PROBES FAILED")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
