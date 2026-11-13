#!/usr/bin/env bash
echo "=== Smart CDN Environment Checker ==="

# Check Python
if command -v python3 &>/dev/null; then
    py_ver=$(python3 --version)
    echo "[OK] Python: $py_ver"
else
    echo "[FAIL] Python3 not found!"
fi

# Check Ryu
if python3 -c "import ryu" &>/dev/null; then
    echo "[OK] Ryu framework installed."
else
    echo "[FAIL] Ryu not found in active python environment!"
fi

# Check Mininet
if command -v mn &>/dev/null; then
    mn_ver=$(mn --version 2>/dev/null || echo "installed")
    echo "[OK] Mininet: $mn_ver"
else
    echo "[FAIL] Mininet not found!"
fi

# Check Open vSwitch
if command -v ovs-vsctl &>/dev/null; then
    echo "[OK] Open vSwitch installed."
else
    echo "[FAIL] Open vSwitch not found!"
fi

echo "=== Environment Check Complete ==="
