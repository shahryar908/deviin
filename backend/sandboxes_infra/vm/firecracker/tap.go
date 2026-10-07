package firecracker

import (
	"fmt"
	"os/exec"
)

func createTap(name, hostIP string) error {
	cmds := [][]string{
		{"ip", "tuntap", "add", "dev", name, "mode", "tap"},
		{"ip", "addr", "add", hostIP + "/24", "dev", name},
		{"ip", "link", "set", name, "up"},
	}
	for _, c := range cmds {
		if out, err := exec.Command("wsl", append([]string{"-u", "root"}, c...)...).CombinedOutput(); err != nil {
			return fmt.Errorf("%v: %v: %s", c, err, out)
		}
	}
	fmt.Println("TAP created:", name, hostIP)
	return nil
}

func deleteTap(name string) {
	exec.Command("wsl", "-u", "root", "ip", "link", "delete", name).Run()
	fmt.Println("TAP deleted:", name)
}
