package firecracker

import (
	"fmt"
	"os/exec"
	"time"
)

type VM struct {
	SocketPath string
	TapName    string
	GuestIP    string
	HostIP     string
	RootfsPath string
	KernelPath string
	WorkspacePath string
	Cmd        *exec.Cmd
}

func (v *VM) Start() error {
	if err := createTap(v.TapName, v.HostIP); err != nil {
		return err
	}
	exec.Command("wsl", "-u", "root", "rm", "-f", v.SocketPath).Run()

	// Redirect kernel logs to a file instead of the vmm process's stdout —
	// piping them to the short-lived vmm process would kill Firecracker when
	// vmm exits (broken pipe).
	sc := v.SocketPath
	cmdStr := "/home/shahryar/firecracker-lab/bin/firecracker --api-sock " + sc + " >/tmp/firecracker.log 2>&1"
	v.Cmd = exec.Command("wsl", "-u", "root", "bash", "-c", cmdStr)
	if err := v.Cmd.Start(); err != nil {
		return fmt.Errorf("start firecracker: %w", err)
	}
	fmt.Println("Firecracker started, Windows PID:", v.Cmd.Process.Pid)

	for i := 0; i < 20; i++ {
		time.Sleep(250 * time.Millisecond)
		if err := exec.Command("wsl", "-u", "root", "test", "-S", v.SocketPath).Run(); err == nil {
			fmt.Println("Socket created:", v.SocketPath)
			return nil
		}
	}
	return fmt.Errorf("socket %s not created", v.SocketPath)
}

func (v *VM) Configure() error {
	steps := []struct{ path, body string }{
		{"/machine-config", `{"vcpu_count": 1, "mem_size_mib": 256, "smt": false}`},
		{"/boot-source", fmt.Sprintf(`{
			"kernel_image_path": "%s",
			"boot_args": "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init ip=%s::%s:255.255.255.0::eth0:off"
		}`, v.KernelPath, v.GuestIP, v.HostIP)},
		{"/drives/rootfs", fmt.Sprintf(`{
			"drive_id": "rootfs",
			"path_on_host": "%s",
			"is_root_device": true,
			"is_read_only": true
		}`, v.RootfsPath)},
		{"/drives/workspace", fmt.Sprintf(`{
			"drive_id": "workspace",
			"path_on_host": "%s",
			"is_root_device": false,
			"is_read_only": false
		}`, v.WorkspacePath)},
		{"/network-interfaces/eth0", fmt.Sprintf(`{
			"iface_id": "eth0",
			"host_dev_name": "%s",
			"guest_mac": "AA:FC:00:00:00:01"
		}`, v.TapName)},
	}
	for _, s := range steps {
		if err := v.put(s.path, s.body); err != nil {
			return fmt.Errorf("PUT %s: %w", s.path, err)
		}
	}
	return nil
}

func (v *VM) Boot() error {
	return v.put("/actions", `{"action_type": "InstanceStart"}`)
}

func (v *VM) WaitForAgent(timeout time.Duration) error {
	url := fmt.Sprintf("http://%s:8080/health", v.GuestIP)
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		out, err := exec.Command("wsl", "curl", "-s", "--max-time", "2", url).Output()
		if err == nil && len(out) > 0 {
			fmt.Printf("envd is up: %s\n", string(out))
			return nil
		}
		time.Sleep(1 * time.Second)
	}
	return fmt.Errorf("agent not reachable at %s within %v", url, timeout)
}

func (v *VM) Cleanup() {
	fmt.Println("\nStopping Firecracker...")
	if v.Cmd != nil && v.Cmd.Process != nil {
		v.Cmd.Process.Kill()
		v.Cmd.Wait()
	}
	exec.Command("wsl", "-u", "root", "pkill", "-f", "firecracker --api-sock").Run()
	exec.Command("wsl", "-u", "root", "rm", "-f", v.SocketPath).Run()
	deleteTap(v.TapName)
	fmt.Println("Cleaned up successfully")
}

func StartVM(v *VM) error {
	if v.KernelPath == "" {
		v.KernelPath = "/home/shahryar/firecracker-lab/kernel/vmlinux.bin"
	}
	if v.WorkspacePath == "" {
		v.WorkspacePath = "/home/shahryar/firecracker-lab/rootfs/workspace.ext4"
	}
	if err := v.Start(); err != nil {
		v.Cleanup()
		return err
	}
	if err := v.Configure(); err != nil {
		v.Cleanup()
		return err
	}
	if err := v.Boot(); err != nil {
		v.Cleanup()
		return err
	}
	if err := v.WaitForAgent(75 * time.Second); err != nil {
		v.Cleanup()
		return err
	}
	return nil
}

func CreateAndStartVM() (*VM, error) {
	v := &VM{
		SocketPath: "/tmp/vm1.socket",
		TapName:    "tap-vm1",
		GuestIP:    "172.16.1.2",
		HostIP:     "172.16.1.1",
		RootfsPath: "/home/shahryar/firecracker-lab/rootfs/sandbox-alpine.ext4",
		KernelPath: "/home/shahryar/firecracker-lab/kernel/vmlinux.bin",
		WorkspacePath: "/home/shahryar/firecracker-lab/rootfs/workspace.ext4",
	}
	if err := StartVM(v); err != nil {
		return nil, err
	}
	return v, nil
}
