package services

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"time"
)

type std struct {
	Kind string
	Data []byte
}

func ExecuteCmd(command []string) (string, string, error) {
	cmd := exec.Command(command[0], command[1:]...)
	var stdOut bytes.Buffer
	var errOut bytes.Buffer
	cmd.Stdout = &stdOut
	cmd.Stderr = &errOut
	if err := cmd.Run(); err != nil {
		return "", "", fmt.Errorf("failed to run the command: %w", err)
	}
	return stdOut.String(), errOut.String(), nil
}

func ExecuteCmdBackground(command []string, c context.Context) (chan []byte, error) {
	cmd := exec.Command(command[0], command[1:]...)
	stdOut, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	stdErr, err := cmd.StderrPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start cmd: %w", err)
	}

	event := make(chan []byte)
	go func() {
		defer close(event)
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				buf := make([]byte, 2024)
				n, err := stdOut.Read(buf)
				if err == nil && n > 0 {
					data := std{Data: buf[:n], Kind: "STDOUT"}
					if byt, err := json.Marshal(data); err == nil {
						event <- byt
					}
				}
				bufe := make([]byte, 2024)
				n, err = stdErr.Read(bufe)
				if err == nil && n > 0 {
					data := std{Data: bufe[:n], Kind: "STDERR"}
					if byt, err := json.Marshal(data); err == nil {
						event <- byt
					}
				}
			case <-c.Done():
				return
			}
		}
	}()
	return event, nil
}
