package firecracker

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	vm, err := CreateAndStartVM()
	if err != nil {
		fmt.Println("VM failed:", err)
		os.Exit(1)
	}

	fmt.Println("VM running. Press Ctrl+C to stop.")
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	vm.Cleanup()
}
