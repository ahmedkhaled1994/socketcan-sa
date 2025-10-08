# Testing Setup

## Running Integration Tests

The integration tests require virtual CAN interfaces to be set up. You have two options:

### Option 1: One-time setup (Recommended)

Run the setup script once:
```bash
# In WSL/Linux
sudo ./tools/setup_vcan.sh
```

This creates persistent `vcan0` and `vcan1` interfaces that will remain available until you reboot or explicitly delete them.

### Option 2: Manual setup

```bash
# Create interfaces manually
sudo ip link add dev vcan0 type vcan
sudo ip link add dev vcan1 type vcan
sudo ip link set up vcan0
sudo ip link set up vcan1
```

### Running the tests

Once interfaces are set up:
```bash
# Windows (using WSL)
wsl bash -c "cd /mnt/d/workspace/GitHub/socketcan-sa && .venv-wsl/bin/python -m pytest tests/test_shaper_integration.py -v"

# Or directly in WSL
cd /mnt/d/workspace/GitHub/socketcan-sa
source .venv-wsl/bin/activate
pytest tests/test_shaper_integration.py -v
```

### Cleanup

To remove the interfaces:
```bash
sudo ./tools/shutdown_vcan.sh
```

## Troubleshooting

If tests are skipped with messages like "Virtual CAN interface vcan0 not found":
1. Make sure you're running in WSL/Linux (not Windows)
2. Run the setup script: `sudo ./tools/setup_vcan.sh`
3. Verify interfaces exist: `ip link show vcan0`