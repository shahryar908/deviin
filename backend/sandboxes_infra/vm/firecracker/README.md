# vm/firecracker — detailed code walkthrough

Package `firecracker` (files in this folder) manages one Firecracker
microVM: it creates the host network, starts the Firecracker process inside
WSL2, configures the VM through Firecracker's HTTP API, boots it, waits for
the in-guest `envd` agent to become reachable, and tears everything down.

All code runs on **Windows**, but Firecracker, the kernel, the rootfs, and
the TAP device all live **inside WSL2**. Every WSL-side action is therefore
a `exec.Command("wsl", ...)` call.

---

## 1. `main.go` — entry point

```go
func main() {
    vm, err := CreateAndStartVM()
    ...
    sig := make(chan os.Signal, 1)
    signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
    <-sig
    vm.Cleanup()
}
```

- `CreateAndStartVM()` does the full startup pipeline (Start → Configure →
  Boot → WaitForAgent) and returns a ready `*VM`.
- The program then blocks on `os.Signal` so Ctrl+C (SIGINT) or SIGTERM
  triggers a graceful `vm.Cleanup()` instead of leaving a running
  Firecracker and a leaked TAP behind.

> After renaming the package to `firecracker`, this file no longer compiles
> as a program (`go run` needs `package main`). Treat it as the reference
> entry point; a thin `main` package elsewhere should import and call
> `CreateAndStartVM()`.

---

## 2. `vm.go` — the VM type and its lifecycle

### 2.1 The struct

```go
type VM struct {
    SocketPath string        // Firecracker API socket, e.g. /tmp/vm1.socket
    TapName    string        // host TAP device, e.g. tap-vm1
    GuestIP    string        // guest static IP, e.g. 172.16.1.2
    HostIP     string        // this side of the TAP, e.g. 172.16.1.1
    RootfsPath string        // path inside WSL to the ext4 image
    Cmd        *exec.Cmd     // the running Firecracker process
}
```

Everything a VM needs to describe itself lives here; all methods hang off
`*VM` so two VMs with different fields could run side by side.

### 2.2 `Start()` — TAP + Firecracker process + API socket

```go
if err := createTap(v.TapName, v.HostIP); err != nil { return err }
exec.Command("wsl", "-u", "root", "rm", "-f", v.SocketPath).Run()

v.Cmd = exec.Command("wsl", "-u", "root",
    "/home/shahryar/firecracker-lab/bin/firecracker",
    "--api-sock", v.SocketPath)
```

- `createTap` must run **before** Firecracker, because the later
  `PUT /network-interfaces/eth0` references `tap-vm1` by name and
  Firecracker opens it immediately; it fails if the device is missing.
- The stale socket is removed so the "socket exists" poll below can never
  match a leftover file from a previous run.
- Firecracker is launched as `wsl -u root`. Two reasons:
  1. It must open `/dev/net/tun` via the TAP we created — the TAP is
     root-owned.
  2. The API socket it creates will be root-owned, so all API calls must
     also run as root.
- `--api-sock` tells Firecracker where to expose its REST API over a unix
  domain socket. That socket *is* the control channel for everything in
  `Configure()`.
- Absolute path to the binary because non-interactive `wsl` invocations do
  **not** read your `.bashrc`, so `$HOME/firecracker-lab/bin` is not on
  PATH there.

Then the readiness loop:

```go
for i := 0; i < 20; i++ {
    time.Sleep(250 * time.Millisecond)
    exec.Command("wsl", "-u", "root", "test", "-S", v.SocketPath).Run()
}
```

Polls `test -S` (true only if the path is a *socket*) every 250 ms, up to
~5 s. Firecracker usually creates the socket in well under a second; the
loop just avoids a fixed sleep that's either too short (race) or too long
(slow startup).

### 2.3 `Configure()` — the four mandatory PUTs

Runs **before** boot. Firecracker freezes most configuration once the
instance starts, so this must all be sent while the VM is still in
`Not started` state.

**1. `PUT /machine-config`**
```json
{"vcpu_count": 1, "mem_size_mib": 256, "smt": false}
```
1 virtual CPU, 256 MiB RAM, SMT off. These are the resource limits for
the microVM.

**2. `PUT /boot-source`**
```json
{
  "kernel_image_path": "/home/shahryar/firecracker-lab/kernel/vmlinux.bin",
  "boot_args": "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init ip=172.16.1.2::172.16.1.1:255.255.255.0::eth0:off"
}
```
- `console=ttyS0` routes kernel logs to the serial console, which
  Firecracker wires to the process's stdout — that's why you see boot logs
  in the terminal.
- `root=/dev/vda rw` mounts the rootfs drive read-write.
- `init=/init` is essential for this image: `/init` is a small shell
  script that mounts `/proc`, `/sys`, `/dev` and then
  `exec /usr/local/bin/envd -addr :8080`. Without it the kernel tries
  busybox init, which fails on the missing `/sbin/openrc`.
- `ip=...::eth0:off` gives the guest a **static** address (`.2`) with this
  host as gateway (`.1`), no DHCP needed.

**3. `PUT /drives/rootfs`**
```json
{"drive_id": "rootfs",
 "path_on_host": "/home/shahryar/firecracker-lab/rootfs/sandbox-alpine.ext4",
 "is_root_device": true, "is_read_only": false}
```
The ext4 image becomes `/dev/vda` inside the guest. We verified with a
strings scan that this image actually contains the `envd` binary.

**4. `PUT /network-interfaces/eth0`**
```json
{"iface_id": "eth0", "host_dev_name": "tap-vm1", "guest_mac": "AA:FC:00:00:00:01"}
```
Binds guest eth0 to the host-side TAP created in `Start()`, with a fixed
MAC address so the guest sees a stable device.

Each PUT goes through `v.put` (api.go); any error aborts the loop with
`PUT <path>: <err>`.

### 2.4 `Boot()` — actually start the VM

```go
v.put("/actions", `{"action_type": "InstanceStart"}`)
```
This is the point of no return: Firecracker loads the kernel, mounts the
rootfs, and runs `/init`. After this returns 204, the guest is booting.

### 2.5 `WaitForAgent(timeout)` — prove the guest works

```go
url := fmt.Sprintf("http://%s:8080/health", v.GuestIP)
exec.Command("wsl", "curl", "-s", "--max-time", "2", url).Output()
```

Kernel boot alone doesn't tell you the agent is alive. This polls
`GET http://172.16.1.2:8080/health` every second (2 s per-request cap)
until it returns the body `envd` produces (`{"status":"ok"}`), or fails
after the timeout (75 s by default). Note curl runs as the normal WSL user
here — the guest IP is reachable without root because it's just routed
traffic over the TAP.

### 2.6 `Cleanup()` — leave nothing behind

1. `v.Cmd.Process.Kill()` + `Wait()` — stop the direct child (the `wsl`
   wrapper).
2. `pkill -f "firecracker --api-sock"` — kill Firecracker itself inside
   WSL. Killing the `wsl.exe` wrapper does **not** reliably reap the
   grandchild Linux process, so this belt-and-suspenders step matters.
3. `rm -f /tmp/vm1.socket` — remove the API socket.
4. `deleteTap("tap-vm1")` — remove the host network device.

### 2.7 `CreateAndStartVM()` — the pipeline

```go
Start() → Configure() → Boot() → WaitForAgent(75s)
```
On **any** error it calls `Cleanup()` before returning, so a failed boot
never leaks a TAP, socket, or Firecracker process. A caller only needs:

```go
vm, err := CreateAndStartVM()
```

---

## 3. `api.go` — talking to Firecracker's API from Windows

Windows cannot open a unix socket that lives inside WSL2, so the naive
Go approach (`http.Client` with a `net.Dial("unix", ...)` transport) does
not work. The workaround: delegate each HTTP call to curl **inside WSL**.

```go
exec.Command("wsl", "-u", "root", "curl", "--silent", "--show-error",
    "--unix-socket", v.SocketPath,
    "-X", "PUT",
    "-H", "Content-Type: application/json",
    "-d", body,
    "http://localhost"+path,
)
```

- `--unix-socket /tmp/vm1.socket` — curl connects to the unix socket
  instead of TCP. The URL host is irrelevant then; `http://localhost` is a
  placeholder Firecracker ignores.
- `-u root` — the socket is root-owned (Firecracker ran as root).
- `--silent --show-error` — no progress meter, but errors still surface.
- `CombinedOutput()` captures the response body (Firecracker returns JSON
  errors or `{}`) and it's printed for debugging.

`get(path)` is the same minus `-X PUT` / `-d`. To add more endpoints
(e.g. `GET /metrics`, `PUT /vm` for pause/resume), follow the same shape.
Each call costs one `wsl.exe` interop process (~100 ms) — fine for
setup-time configuration, too slow for a hot path. If you ever move the
control plane into WSL (a Linux Go binary), replace these with a real
unix-socket HTTP client.

---

## 4. `tap.go` — host-side networking

```go
exec.Command("wsl", "-u", "root", "ip", "tuntap", "add", "dev", name, "mode", "tap")
exec.Command("wsl", "-u", "root", "ip", "addr", "add", hostIP+"/24", "dev", name)
exec.Command("wsl", "-u", "root", "ip", "link", "set", name, "up")
```

A TAP device is a virtual Ethernet cable: one end is `tap-vm1` in WSL,
the other end is `eth0` inside the microVM.

- `ip tuntap add ... mode tap` creates the device.
- `ip addr add 172.16.1.1/24` gives the WSL side an address on the same
  subnet the guest will use (`172.16.1.0/24`).
- `ip link set ... up` activates it. Until this, the device shows
  `NO-CARRIER`.

We use `wsl -u root` rather than `sudo` because your WSL sudo requires a
password, which would hang the Go program; `wsl -u root` starts the
interop session directly as root.

`deleteTap` removes the device in `Cleanup()`. It's safe to call even if
the TAP never got created (the `ip` error is ignored on purpose).

---

## 5. End-to-end timeline

```
Windows Go program
│
├─ createTap("tap-vm1", "172.16.1.1")          wsl -u root ip ...
├─ rm -f /tmp/vm1.socket                        (stale cleanup)
├─ exec wsl -u root firecracker --api-sock ...   (process starts)
├─ poll test -S /tmp/vm1.socket                  (~0.3 s)
├─ PUT /machine-config        → 204
├─ PUT /boot-source           → 204
├─ PUT /drives/rootfs         → 204
├─ PUT /network-interfaces/eth0 → 204
├─ PUT /actions InstanceStart → 204
│        │
│        └─ inside WSL: kernel boots, mounts ext4, runs /init,
│           /init execs envd -addr :8080
│
├─ poll GET http://172.16.1.2:8080/health        (~2–5 s)
│        → {"status":"ok"}
│
└─ (Ctrl+C) kill, pkill, rm socket, deleteTap
```

## 6. Gotchas collected during development

- **Two `func main` files in one folder don't compile** — an earlier
  `client.go`/`talk.go` duplicate was removed for this reason.
- **Busybox init fails** with `can't run '/sbin/openrc'` unless you pass
  `init=/init` — the rootfs only ships the `/init` script.
- **`wsl sudo` hangs** on a password prompt; use `wsl -u root`.
- **Killing the `wsl` wrapper doesn't kill Firecracker**; always `pkill`
  inside WSL too.
- **ext4 journal**: abrupt kills leave the image needing journal recovery;
  the kernel replays it on next boot, but worst case run `e2fsck` on a copy.
- **Running several VMs**: make `SocketPath`, `TapName`, and the
  `GuestIP`/`HostIP` subnet unique per VM (e.g. `vm2`, `172.16.2.x`).
