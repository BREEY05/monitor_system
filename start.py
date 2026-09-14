#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gong Ye Huan Jing Jian Kong Xi Tong - Yi Jian Qi Dong Jiao Ben
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def get_python_cmd():
    return sys.executable

def kill_port_occupiers(port):
    is_windows = platform.system() == "Windows"
    if is_windows:
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
            pids_to_kill = set()
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pids_to_kill.add(parts[-1])
            for pid in pids_to_kill:
                try:
                    pid = int(pid)
                    if pid != os.getpid() and pid != 0:
                        print(f"   [KILL] Release port {port} (PID: {pid})...")
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                except (ValueError, subprocess.TimeoutExpired):
                    pass
            return True
        except Exception:
            return False
    else:
        try:
            result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5)
            pids = result.stdout.strip().splitlines()
            for pid in pids:
                try:
                    pid = int(pid)
                    if pid != os.getpid():
                        os.kill(pid, 9)
                except (ValueError, ProcessLookupError):
                    pass
            return True
        except FileNotFoundError:
            return False

def check_dependencies():
    required = [
        "fastapi", "uvicorn", "pydantic", "Pillow", "requests",
        "python-multipart", "psycopg2-binary", "langchain",
        "langchain-community", "langchain-text-splitters",
        "duckduckgo-search", "pypdf", "python-docx", "langgraph"
    ]
    optional = ["sseclient-py"]
    print("=" * 55)
    print("   Industrial Env Monitor - Startup Check")
    print("=" * 55)
    print()
    all_packages = required + optional
    missing = []
    for lib in all_packages:
        try:
            if lib.lower() == "pillow":
                __import__("PIL")
            elif lib.lower() == "python-multipart":
                __import__("multipart")
            elif lib.lower() == "psycopg2-binary":
                __import__("psycopg2")
            elif lib.lower() == "langchain-community":
                __import__("langchain_community")
            elif lib.lower() == "langchain-text-splitters":
                __import__("langchain_text_splitters")
            elif lib.lower() == "duckduckgo-search":
                __import__("duckduckgo_search")
            elif lib.lower() == "python-docx":
                __import__("docx")
            elif lib.lower() == "sseclient-py":
                __import__("sseclient")
            else:
                __import__(lib.lower())
        except ImportError:
            missing.append(lib)
    if missing:
        print(f"   Installing {len(missing)} packages...")
        print()
        for lib in missing:
            try:
                pkg_name = lib.lower()
                if pkg_name == "pillow":
                    pkg_name = "Pillow"
                print(f"   [INSTALL] {lib}...", end=" ", flush=True)
                result = subprocess.run([get_python_cmd(), "-m", "pip", "install", pkg_name], capture_output=True, text=True)
                print("OK" if result.returncode == 0 else "FAIL")
            except Exception as e:
                print(f"FAIL: {e}")
        print()
    print("   [OK] Dependencies check passed")
    print()

def check_ollama():
    print("   Checking Ollama service...")
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("   [OK] Ollama installed")
            return True
        else:
            print("   [WARN] Ollama not available")
            return False
    except FileNotFoundError:
        print("   [WARN] Ollama not installed")
        print("      Download: https://ollama.com/download")
        return False

def start_backend(port):
    print("=" * 55)
    print("   Industrial Environment Monitor - Demo Version")
    print("=" * 55)
    print()
    print(f"   Frontend:   http://localhost:{port}")
    print(f"   API Docs:   http://localhost:{port}/docs")
    print(f"   WebSocket:  ws://localhost:{port}/ws/sensor")
    print()
    print(f"   AI Chat:    Ollama Local Model")
    print(f"   System:     {platform.system()} {platform.release()}")
    print("-" * 55)
    print()
    print("   Press Ctrl+C to stop")
    print("=" * 55)
    print()
    try:
        from api_server import app
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except ImportError as e:
        print(f"   [ERROR] Import failed: {e}")
        input("   Press Enter to exit...")
        sys.exit(1)
    except Exception as e:
        print(f"   [ERROR] Start failed: {e}")
        input("   Press Enter to exit...")
        sys.exit(1)

def main():
    os.chdir(Path(__file__).parent)
    port = 8000
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            try:
                port = int(arg.split("=")[1])
            except ValueError:
                print(f"Invalid port: {arg}")
                sys.exit(1)
    check_dependencies()
    check_ollama()
    print(f"   Checking port {port}...")
    kill_port_occupiers(port)
    print(f"   [OK] Port {port} ready")
    print()
    print("   Starting backend service...")
    print()
    start_backend(port)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("=" * 55)
        print("   Service stopped")
        print("=" * 55)
