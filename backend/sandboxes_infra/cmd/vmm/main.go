package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"

	"github.com/shahryar908/devin/vm/firecracker"
)

type SandboxInfo struct {
	SocketPath string `json:"socket_path"`
	TapName    string `json:"tap_name"`
	GuestIP    string `json:"guest_ip"`
	HostIP     string `json:"host_ip"`
	RootfsPath string `json:"rootfs_path"`
	KernelPath string `json:"kernel_path"`
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	cmd := os.Args[1]
	os.Args = append([]string{os.Args[0]}, os.Args[2:]...)

	switch cmd {
	case "create":
		createCmd()
	case "destroy":
		destroyCmd()
	case "status":
		statusCmd()
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: vmm <create|destroy|status> [flags]")
}

func createCmd() {
	fs := flag.NewFlagSet("create", flag.ExitOnError)
	socketPath := fs.String("socket", "/tmp/vm1.socket", "firecracker api socket")
	tapName := fs.String("tap", "tap-vm1", "host tap device")
	gip := fs.String("guest-ip", "172.16.1.2", "guest IP")
	hip := fs.String("host-ip", "172.16.1.1", "host TAP IP")
	rootfsPath := fs.String("rootfs", "/home/shahryar/firecracker-lab/rootfs/sandbox-alpine.ext4", "rootfs ext4")
	workspacePath := fs.String("workspace", "/home/shahryar/firecracker-lab/rootfs/workspace.ext4", "per-session workspace ext4")
	kernelPath := fs.String("kernel", "/home/shahryar/firecracker-lab/kernel/vmlinux.bin", "kernel")
	jsonOut := fs.Bool("json", false, "print sandbox info as JSON")
	fs.Parse(os.Args[1:])

	v := &firecracker.VM{
		SocketPath: *socketPath,
		TapName:    *tapName,
		GuestIP:    *gip,
		HostIP:     *hip,
		RootfsPath: *rootfsPath,
		KernelPath: *kernelPath,
		WorkspacePath: *workspacePath,
	}
	if err := firecracker.StartVM(v); err != nil {
		fmt.Fprintln(os.Stderr, "create:", err)
		os.Exit(1)
	}
	info := SandboxInfo{
		SocketPath: *socketPath,
		TapName:    *tapName,
		GuestIP:    *gip,
		HostIP:     *hip,
		RootfsPath: *rootfsPath,
		KernelPath: *kernelPath,
	}
	if *jsonOut {
		b, _ := json.Marshal(info)
		fmt.Println(string(b))
	} else {
		fmt.Printf("sandbox up: %+v\n", info)
	}
}

func destroyCmd() {
	fs := flag.NewFlagSet("destroy", flag.ExitOnError)
	socketPath := fs.String("socket", "/tmp/vm1.socket", "firecracker api socket")
	tapName := fs.String("tap", "tap-vm1", "host tap device")
	fs.Parse(os.Args[1:])

	exec.Command("wsl", "-u", "root", "pkill", "-f", "firecracker --api-sock").Run()
	exec.Command("wsl", "-u", "root", "rm", "-f", *socketPath).Run()
	exec.Command("wsl", "-u", "root", "ip", "link", "delete", *tapName).Run()
	fmt.Println("sandbox destroyed")
}

func statusCmd() {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	socketPath := fs.String("socket", "/tmp/vm1.socket", "firecracker api socket")
	guestIP := fs.String("guest-ip", "172.16.1.2", "guest IP")
	fs.Parse(os.Args[1:])

	socketOK := exec.Command("wsl", "-u", "root", "test", "-S", *socketPath).Run() == nil
	healthOK := exec.Command("wsl", "curl", "-s", "--max-time", "2", fmt.Sprintf("http://%s:8080/health", *guestIP)).Run() == nil
	fmt.Printf("socket: %v, envd: %v\n", socketOK, healthOK)
}
