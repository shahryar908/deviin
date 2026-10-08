# `vm/firecracker` — implementation reference

This document describes the **actual code in this folder** as it exists
today. Everything below is what the Go files really do — paths, constants,
commands, and JSON payloads are the real values used.

---

## 1. What this package does

`package firecracker` manages the full life of one Firecracker microVM:

```
create TAP → start firecracker → wait for API socket → configure →
InstanceStart → wait for envd → (Ctrl+C) cleanup
```

Where things run:

| Component        | Where it runs                    |
|------------------|----------------------------------|
| This Go package  | Windows (`C:\projects\devin`)    |
| Firecracker bin  | WSL2 (`~/firecracker-lab/bin`)   |
| Kernel `vmlinux.bin` | WSL2 filesystem              |
| rootfs `*.ext4`  | WSL2 filesystem                  |
| TAP `tap-vm1`    | WSL2 network stack               |
| `envd` agent     | inside the microVM guest         |

Windows cannot talk to WSL's unix sockets or net devices directly, so the
Go code never touches Firecracker itself — it shells out to WSL for every
low-level operation (`wsl`, `wsl -u root`).

---

## 2. Files in this folder

| File       | Contents                                                   |
|------------|------------------------------------------------------------|
| `main.go`  | Demo entry: `CreateAndStartVM()` + Ctrl+C handler. **Inert** because the folder is `package firecracker`, not `package main` — see §6. |
| `vm.go`    | `VM` struct + all lifecycle methods + `CreateAndStartVM()` |
| `api.go`   | `put`/`get` — Firecracker REST calls via `wsl curl`        |
| `tap.go`   | `createTap`/`deleteTap` — host networking via `wsl -u root ip` |
| `README.md`| This document                                              |

---

## 3. `vm.go`

### 3.1 The `VM` struct

```go
type VM struct {
    SocketPath string         // "/tmp/vm1.socket"
    TapName    string         // "tap-vm1"
    GuestIP    string         // "172.16.1.2"
    HostIP     string         // "172.16.1.1"
    RootfsPath string         // "/home/shahryar/firecracker-lab/rootfs/sandbox-alpine.ext4"
    Cmd        *exec.Cmd      // the running firecracker process
}
```

### 3.2 `Start() error`

1. `createTap(v.TapName, v.HostIP)` — the TAP must exist **before**
   Firecracker starts config, because `PUT /network-interfaces/eth0`
   references it by name.
2. `wsl -u root rm -f <SocketPath>` — delete stale socket so the
   readiness poll can't match a leftover.
3. Launches Firecracker:
   ```go
   exec.Command("wsl", "-u", "root",
       "/home/shahryar/firecracker-lab/bin/firecracker",
       "--api-sock", v.SocketPath)
   ```
   - Full path because non-interactive `wsl` doesn't read `.bashrc`,
     where your PATH entry lives.
   - `-u root` because Firecracker must open the root-owned TAP, and the
     socket it creates will be root-owned too.
   - Stdout/stderr are wired to the Go process so kernel boot logs
     (`console=ttyS0`) appear in your terminal.
4. Readiness loop — up to 20 × 250 ms, checks:
   ```
   wsl -u root test -S /tmp/vm1.socket
   ```
   `test -S` is true only for a unix socket. On timeout → error.

### 3.3 `Configure() error`

Sends four PUTs **in order**, all `204` on success:

1. `PUT /machine-config`
   ```json
   {"vcpu_count": 1, "mem_size_mib": 256, "smt": false}
   ```
2. `PUT /boot-source`
   ```json
   {
     "kernel_image_path": "/home/shahryar/firecracker-lab/kernel/vmlinux.bin",
     "boot_args": "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init ip=172.16.1.2::172.16.1.1:255.255.255.0::eth0:off"
   }
   ```
   Boot args decoded:

   | Arg | Meaning |
   |---|---|
   | `console=ttyS0` | kernel logs → serial → firecracker stdout |
   | `reboot=k panic=1` | reboot on exit, panic immediately on kernel panic |
   | `pci=off` | no PCI (faster boot, fewer devices) |
   | `root=/dev/vda rw` | rootfs = first virtio block device, read-write |
   | `init=/init` | **required** — the image's `/init` shell script mounts /proc,/sys,/dev then `exec /usr/local/bin/envd -addr :8080`. Without it the kernel falls back to busybox init which fails on missing `/sbin/openrc` |
   | `ip=...` | static guest config: IP `.2`, gateway `.1`, /24, interface `eth0` |

3. `PUT /drives/rootfs`
   ```json
   {"drive_id": "rootfs",
    "path_on_host": "/home/shahryar/firecracker-lab/rootfs/sandbox-alpine.ext4",
    "is_root_device": true, "is_read_only": false}
   ```
   This is the image that contains `envd` (verified by a strings scan of
   the ext4).
4. `PUT /network-interfaces/eth0`
   ```json
   {"iface_id": "eth0",
    "host_dev_name": "tap-vm1",
    "guest_mac": "AA:FC:00:00:00:01"}
   ```

Config must all be sent **before** `InstanceStart`; Firecracker rejects
most of it afterwards.

### 3.4 `Boot() error`

```go
v.put("/actions", `{"action_type": "InstanceStart"}`)
```
Point of no return — kernel boots.

### 3.5 `WaitForAgent(timeout) error`

```go
url := "http://172.16.1.2:8080/health"
exec.Command("wsl", "curl", "-s", "--max-time", "2", url).Output()
```

Polls `envd`'s `/health` once per second until it returns a non-empty body
(`{"status":"ok"}`) or `timeout` (75 s) elapses. This is the only proof
the guest actually reached userspace.

### 3.6 `Cleanup()`

In order:

1. `v.Cmd.Process.Kill()` + `v.Cmd.Wait()` — stop the `wsl` wrapper.
2. `wsl -u root pkill -f "firecracker --api-sock"` — **required**: killing
   the `wsl` wrapper does not reap the Linux firecracker child.
3. `wsl -u root rm -f /tmp/vm1.socket` — remove the API socket.
4. `deleteTap(v.TapName)` — remove the network device.

### 3.7 `CreateAndStartVM()`

```go
Start() → Configure() → Boot() → WaitForAgent(75 * time.Second)
```
On any error: `Cleanup()` then return the error (no leaked TAP/socket/
process). On success the caller owns a running VM and must eventually
call `Cleanup()`.

---

## 4. `api.go` — Firecracker REST from Windows

Windows Go **cannot** open a unix socket that lives inside WSL2, so a
native unix-socket HTTP client does not work here. Both helpers instead
run curl *inside WSL*:

```go
// put
exec.Command("wsl", "-u", "root", "curl", "--silent", "--show-error",
    "--unix-socket", v.SocketPath,
    "-X", "PUT", "-H", "Content-Type: application/json",
    "-d", body, "http://localhost" + path)

// get — same but no -X PUT, no -d
```

- `--unix-socket` ignores the URL's host for connection purposes;
  `http://localhost` is a placeholder Firecracker accepts.
- `-u root` because the socket is root-owned.
- Each call prints its response (`PUT /actions -> 204 No Content` etc.)
  for debugging and returns a non-nil error if curl failed.
- Cost: one `wsl.exe` interop process per call (~100 ms). Fine at setup
  time; a hot control path should live in Linux Go instead.

---

## 5. `tap.go` — host networking

```go
wsl -u root ip tuntap add dev tap-vm1 mode tap
wsl -u root ip addr add 172.16.1.1/24 dev tap-vm1
wsl -u root ip link set tap-vm1 up
```

A TAP is a virtual Ethernet pair: WSL side = `tap-vm1` (`172.16.1.1/24`),
peer side = guest `eth0` (`172.16.1.2`). `deleteTap` runs
`ip link delete tap-vm1` and ignores errors (idempotent cleanup).

Why `wsl -u root` and not `sudo`: your WSL sudo requires a password, which
would hang the Go program. `wsl -u root` enters the interop session as
root with no prompt.

---

## 6. `main.go` — why it's inert, and how to run for real

The folder is `package firecracker`. Go only honors `func main` as a
program entry in `package main`. So `main.go` here compiles (a function
named `main` is legal in any package) but starting a VM via
`go run ./vm/firecracker` does nothing — the package builds, no program
runs.

To run a VM from the command line, add (not yet present):

```
cmd/vmm/main.go
```

```go
package main

import (
    "fmt"
    "os"
    "os/signal"
    "syscall"

    fc "github.com/shahryar908/devin/vm/firecracker"
)

func main() {
    vm, err := fc.CreateAndStartVM()
    if err != nil { fmt.Println(err); os.Exit(1) }
    sig := make(chan os.Signal, 1)
    signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
    <-sig
    vm.Cleanup()
}
```

Then: `go run ./cmd/vmm`.

Note the module is `github.com/shahryar908/devin` (see
`backend/sandboxes_infra/go.mod`), so the import path is
`github.com/shahryar908/devin/vm/firecracker`.

---

## 7. Verified working behavior

Observed in the last live run:

```
2026/10/07 20:03:49 envd listening on :8080        ← guest /init
envd is up: {"status":"ok"}                        ← WaitForAgent
VM running. Press Ctrl+C to stop.
```

All four configure PUTs returned `204`.
