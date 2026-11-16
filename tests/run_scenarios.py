#!/usr/bin/env python3
"""Run isolated Smart CDN scenarios against a disposable Mininet topology.

Requires root, Mininet/OVS, and a project Ryu runtime. It never runs `mn -c`;
if conflicting switch bridges already exist it stops and asks for manual review.
"""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import CONTENT_DIR, OFP_CONTROLLER_PORT, SERVERS  # noqa: E402
from scripts.content import generate_content  # noqa: E402


def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def start_controller(mode):
    manager = shutil.which("ryu-manager")
    if manager is None:
        candidate = Path(sys.executable).with_name("ryu-manager")
        if candidate.is_file():
            manager = str(candidate)
    if manager is None:
        raise RuntimeError("ryu-manager is not available in this Python environment")
    if port_open("127.0.0.1", OFP_CONTROLLER_PORT):
        raise RuntimeError("port 6653 is already occupied; refusing to attach to an unknown controller")
    env = os.environ.copy()
    env["CDN_MODE"] = mode
    python_path = env.get("PYTHONPATH", "")
    project_path = str(PROJECT_ROOT)
    if project_path not in python_path.split(os.pathsep):
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (project_path, python_path)))
    process = subprocess.Popen(
        [manager, "controller.cdn_controller"],
        cwd=str(PROJECT_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Ryu controller exited during startup")
        if port_open("127.0.0.1", OFP_CONTROLLER_PORT):
            return process
        time.sleep(0.2)
    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError("Ryu controller did not open port 6653 within 15 seconds")


def ensure_no_conflicting_bridges():
    ovs_vsctl = shutil.which("ovs-vsctl")
    if ovs_vsctl is None:
        raise RuntimeError("ovs-vsctl is not installed")
    result = subprocess.run([ovs_vsctl, "list-br"], capture_output=True, text=True, check=True)
    conflicts = {"s1", "s2", "s3", "s4", "s5"}.intersection(result.stdout.split())
    if conflicts:
        raise RuntimeError(
            "existing OVS bridges conflict with this test: {}. No cleanup was attempted.".format(
                ", ".join(sorted(conflicts))
            )
        )


def _run_client(host, filename, digest, client_id, timeout):
    client_path = str(PROJECT_ROOT / "app" / "client.py")
    process = host.popen([
        sys.executable, client_path, "--id", client_id,
        "--file", filename, "--hash", digest,
    ], cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output, _ = process.communicate(timeout=timeout)
    if process.returncode != 0:
        raise RuntimeError("client exited {}: {}".format(process.returncode, output))
    return output


def run_scenario(name, size_mb=16, seed=1, mode="dynamic", duration=15, congestion_mode="random"):
    if os.geteuid() != 0:
        raise RuntimeError("system scenarios require root; rerun with approved sudo")
    ensure_no_conflicting_bridges()
    from mininet.link import TCLink
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController
    from topology.topo import SmartCDNTopo

    run_id = uuid.uuid4().hex[:10]
    filename = "scenario_{}.bin".format(run_id)
    content_root = Path(CONTENT_DIR)
    content_root.mkdir(parents=True, exist_ok=True)
    content_file = content_root / filename
    if content_file.exists():
        raise RuntimeError("refusing to overwrite existing test content: {}".format(content_file))
    scratch = Path(tempfile.mkdtemp(prefix="smartcdn-{}-".format(run_id)))
    downloaded = Path("/tmp/client_downloads") / "c1_{}".format(filename)
    manifest = generate_content(scratch, size_mb * 1024 * 1024, seed, filename)
    shutil.copyfile(scratch / filename, content_file)

    controller = None
    net = None
    services = []
    traffic = None
    try:
        controller = start_controller(mode)
        net = Mininet(topo=SmartCDNTopo(), switch=OVSSwitch, link=TCLink, controller=None)
        net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=OFP_CONTROLLER_PORT)
        net.start()
        for server_id, info in SERVERS.items():
            process = net.get(server_id).popen([
                sys.executable, str(PROJECT_ROOT / "app" / "server.py"),
                "--id", server_id, "--ip", info["ip"],
            ], cwd=str(PROJECT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            services.append((server_id, process))
        sink = net.get("srv1").popen([
            sys.executable, str(PROJECT_ROOT / "app" / "traffic_sink.py"),
            "--bind", SERVERS["srv1"]["ip"],
        ], cwd=str(PROJECT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        services.append(("traffic-sink", sink))
        time.sleep(2)

        if name == "failover":
            if size_mb < 32:
                raise ValueError("failover test requires --size-mb 32 or larger to interrupt an active transfer")
            client = net.get("c1")
            client_proc = client.popen([
                sys.executable, str(PROJECT_ROOT / "app" / "client.py"),
                "--id", "c1", "--file", filename, "--hash", manifest["sha256"],
            ], cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            time.sleep(0.25)
            next(proc for server_id, proc in services if server_id == "srv1").terminate()
            output, _ = client_proc.communicate(timeout=max(duration, 45))
            if client_proc.returncode != 0:
                raise RuntimeError("failover client failed: {}".format(output))
        elif name == "link-failure":
            if size_mb < 16:
                raise ValueError("link-failure test requires --size-mb 16 or larger")
            client_proc = net.get("c1").popen([
                sys.executable, str(PROJECT_ROOT / "app" / "client.py"),
                "--id", "c1", "--file", filename, "--hash", manifest["sha256"],
            ], cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            time.sleep(0.2)
            net.configLinkStatus("s1", "s2", "down")
            time.sleep(1)
            net.configLinkStatus("s1", "s2", "up")
            output, _ = client_proc.communicate(timeout=duration)
            if client_proc.returncode != 0:
                raise RuntimeError("link-failure client failed: {}".format(output))
        elif name == "congestion":
            traffic = net.get("loadsrc").popen([
                sys.executable, str(PROJECT_ROOT / "scripts" / "congestion.py"),
                "--mode", congestion_mode, "--duration", str(duration), "--seed", str(seed),
                "--telemetry", str(PROJECT_ROOT / "results" / "live_routes.json"),
            ], cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            time.sleep(2)
            output = _run_client(net.get("c1"), filename, manifest["sha256"], "c1", duration + 10)
            traffic.wait(timeout=duration + 5)
        else:
            output = _run_client(net.get("c1"), filename, manifest["sha256"], "c1", duration)

        if not downloaded.exists() or hashlib.sha256(downloaded.read_bytes()).hexdigest() != manifest["sha256"]:
            raise RuntimeError("download missing or SHA-256 differs from generated source")
        return {
            "run_id": run_id,
            "mode": mode,
            "scenario": name,
            "throughput_mbps": _latest_throughput(),
            "ttfb_ms": _latest_ttfb(),
            "completed": 1,
            "total": 1,
            "sha256": manifest["sha256"],
            "client_output": output.strip().splitlines()[-1] if output.strip() else "",
        }
    finally:
        if traffic is not None and traffic.poll() is None:
            traffic.terminate()
            traffic.wait(timeout=5)
        for _service, process in services:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        if net is not None:
            net.stop()
        if controller is not None and controller.poll() is None:
            controller.terminate()
            try:
                controller.wait(timeout=5)
            except subprocess.TimeoutExpired:
                controller.kill()
                controller.wait(timeout=5)
        content_file.unlink(missing_ok=True)
        downloaded.unlink(missing_ok=True)
        shutil.rmtree(scratch, ignore_errors=True)


def _latest_metrics():
    path = PROJECT_ROOT / "results" / "data" / "client-transfers.csv"
    if not path.exists():
        return {}
    import csv
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return rows[-1] if rows else {}


def _latest_throughput():
    try:
        return float(_latest_metrics().get("throughput_mbps", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _latest_ttfb():
    try:
        return float(_latest_metrics().get("ttfb_ms", 0.0))
    except (TypeError, ValueError):
        return 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("smoke", "failover", "link-failure", "congestion"))
    parser.add_argument("--mode", choices=("dynamic", "static"), default=os.environ.get("CDN_MODE", "dynamic"))
    parser.add_argument("--size-mb", type=int, default=16)
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--congestion-mode", choices=("adaptive", "random"), default="random")
    parser.add_argument("--seed", type=int, default=int(os.environ.get("CDN_SEED", "1")))
    args = parser.parse_args()
    if args.size_mb <= 0 or args.duration <= 0:
        parser.error("--size-mb and --duration must be positive")
    result = run_scenario(
        args.scenario, args.size_mb, args.seed, args.mode, args.duration,
        args.congestion_mode,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("scenario failed: {}".format(exc), file=sys.stderr)
        raise SystemExit(1)
