# RSMesh BBS

Release 1.1

A Meshtastic bulletin board system with mail, channels, peer sync, and an admin tool.

Based on (and sync compatible with) [TC²-BBS-Mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh).

## Requirements

- Python 3.8+ (with `venv` support)
- A Meshtastic node connected by USB serial or TCP (ESP32 WiFi)

## Setup (virtual environment)

Use a project-local virtual environment so dependencies do not mix with system Python packages.

**Linux / macOS**

```bash
cd /path/to/rsmesh-bbs
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
cd C:\path\to\rsmesh-bbs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

After activation, `python` and `pip` refer to the venv. You can also run scripts without activating by calling the venv interpreter directly (for example `.venv/bin/python` on Linux or `.venv\Scripts\python.exe` on Windows).

## Quick start

1. Complete [Setup (virtual environment)](#setup-virtual-environment) above.
2. Copy `example_config.yml` to `config.yml` and edit for your node.
3. Start the BBS server from the project directory (with the venv activated):

```bash
python rsmesh-bbs_server.py
```

Use `-c` / `--config` to point at a different YAML file, or `-v` / `--version` to print the server version:

```bash
python rsmesh-bbs_server.py -c /path/to/config.yml
python rsmesh-bbs_server.py --version
```

4. Manage the database with the admin tool (no radio required):

```bash
python rsmesh-bbs_admin.py
```

The server creates `rsmesh-bbs.db` in the current working directory. Module data (for example Node Info) is stored under `modules/<name>/`. Run both scripts from the project directory so they use the same files.

## Mesh client (no radio)

`rsmesh-bbs_client.py` simulates a mesh handset in-process for testing without a radio. See the [Sysop Guide](docs/RSMESH-BBS-SYSOP-GUIDE.md#mesh-client-no-radio).

## Using the BBS from the mesh

See the [User Guide](docs/RSMESH-BBS-USER-GUIDE.md) for mesh menus, mail, bulletins, channels, and sysadmin capabilities.

## Admin tool

Run `rsmesh-bbs_admin.py` from the project directory with the [virtual environment](#setup-virtual-environment) activated (same as the server). It manages bulletins, mail, channels, the node catalog, sync peers, modules, and bulletin delete reconciliation.

See the [Sysop Guide](docs/RSMESH-BBS-SYSOP-GUIDE.md) for configuration, operator concepts, and a complete guide to every admin menu, input prompt, and valid choice.

## Upgrading from TC2 or RSMesh BBS 1.0

If you are migrating from TC²-BBS-Mesh or upgrading an existing RSMesh BBS 1.0 install, see [Upgrading](docs/UPGRADING.md) for migration steps and release notes.

## Cross-platform support

The Python code runs on Linux, Windows, and macOS. Use the same [virtual environment](#setup-virtual-environment) on every platform; differences are mostly about how you connect the radio and how you run the server as a background service.

### Serial (USB) examples

Set `type: serial` and the correct `port` for your OS in `config.yml`:

**Linux**

```yaml
interface:
  type: serial
  port: /dev/ttyUSB0
```

If only one serial device is connected, you can omit `port` and let Meshtastic auto-detect it. On Linux you may need membership in the `dialout` group to access USB serial devices.

**macOS**

```yaml
interface:
  type: serial
  port: /dev/cu.usbmodem101
```

List available ports after plugging in the device:

```bash
ls /dev/cu.*
```

**Windows**

```yaml
interface:
  type: serial
  port: COM3
```

Check Device Manager for the assigned COM port. Use Windows Terminal or another modern console for the admin tool bold formatting.

### TCP (WiFi) example

TCP works the same on all platforms and is useful for ESP32-based nodes:

```yaml
interface:
  type: tcp
  hostname: 192.168.1.100
```

### Running as a service

| Platform | Approach |
|----------|----------|
| **Linux** | Use `rsmesh-bbs.service` as a systemd unit (see below). |
| **macOS** | Run manually with the venv activated, or create a `launchd` plist if you need auto-start. |
| **Windows** | Run manually with the venv activated, or use Task Scheduler to start `.venv\Scripts\python.exe rsmesh-bbs_server.py` at login. |

`rsmesh-bbs_admin.py` is intended for interactive use and does not need to run as a service.

#### Linux systemd

The bundled `rsmesh-bbs.service` expects the project at `/opt/rsmesh-bbs` with dependencies installed in `/opt/rsmesh-bbs/.venv`. Pick an unprivileged Linux account to run the service — a dedicated user is ideal, but an existing login account works too. That account must own the install directory and match `User` / `Group` in the unit file.

The unit file ships with `User=bbs` and `Group=bbs` as placeholders. Either create that account or edit those lines to your chosen username before enabling the service.

```bash
# Optional: create a dedicated system user (skip if using an existing account)
sudo useradd --system --home /opt/rsmesh-bbs --create-home --shell /usr/sbin/nologin bbs

sudo mkdir -p /opt/rsmesh-bbs
sudo git clone git@github.com:UnityCore/rsmesh-bbs.git /opt/rsmesh-bbs
cd /opt/rsmesh-bbs
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp example_config.yml config.yml
# edit config.yml for your node

# Replace bbs with your service account if different
sudo chown -R bbs:bbs /opt/rsmesh-bbs

# Edit User=, Group=, WorkingDirectory=, and ExecStart= if paths or account differ
sudo cp rsmesh-bbs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rsmesh-bbs
sudo systemctl status rsmesh-bbs
```

After pulling updates, reinstall dependencies when `requirements.txt` changes and ensure the service user still owns the tree (especially if you ran `git pull` as root):

```bash
cd /opt/rsmesh-bbs
git pull
.venv/bin/python -m pip install -r requirements.txt
sudo chown -R bbs:bbs /opt/rsmesh-bbs   # use your service account
sudo systemctl restart rsmesh-bbs
```

If the service fails to start, read the journal for the startup error message:

```bash
sudo journalctl -u rsmesh-bbs -n 50 --no-pager
```

Common causes after enabling the venv-based service:

| Symptom in journal | Fix |
|--------------------|-----|
| `virtual environment not found` | Run `python3 -m venv .venv` and `pip install -r requirements.txt` in `/opt/rsmesh-bbs` |
| `configuration file not found` | Copy and edit `config.yml` in `/opt/rsmesh-bbs` |
| `missing Python package` | `.venv/bin/python -m pip install -r requirements.txt` |
| `cannot write database` / `read-only` / `readonly database` | `sudo chown -R <service-user>:<service-user> /opt/rsmesh-bbs` — the service account must own the database and WAL files |
| `PermissionError` on serial port | Add service user to `dialout` (`SupplementaryGroups=dialout` in the unit file) and verify `interface.port` in `config.yml` |
| `No serial ports detected` | Set `interface.port` explicitly, or use `interface.type: tcp` with `hostname` |

## Thanks to

- [TC²-BBS](https://github.com/TheCommsChannel/TC2-BBS-mesh)
- [Meshtastic](https://github.com/meshtastic)

## License

GPL-3.0-only. See [LICENSE](LICENSE).
