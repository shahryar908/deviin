package firecracker

import (
	"fmt"
	"os/exec"
)

func (v *VM) put(path, body string) error {
	out, err := exec.Command("wsl", "-u", "root", "curl", "--silent", "--show-error",
		"--unix-socket", v.SocketPath,
		"-X", "PUT",
		"-H", "Content-Type: application/json",
		"-d", body,
		"http://localhost"+path,
	).CombinedOutput()
	fmt.Printf("PUT %s -> %s\n", path, string(out))
	return err
}

func (v *VM) get(path string) error {
	out, err := exec.Command("wsl", "-u", "root", "curl", "--silent", "--show-error",
		"--unix-socket", v.SocketPath,
		"http://localhost"+path,
	).CombinedOutput()
	fmt.Printf("GET %s -> %s\n", path, string(out))
	return err
}
