package services

import (
	"bytes"
	"os"
	"os/exec"

	"github.com/shahryar908/devin/vm/envd/models"
)

var filePath = "./code.js"

type ExecuteResult struct {
	Output   string `json:"output"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exitCode"`
	Error    string `json:"error,omitempty"`
}

func WriteToFile(code *models.Execute) error {
	return os.WriteFile(filePath, []byte(code.Code), 0644)
}

func ExecuteJS() ExecuteResult {
	result := ExecuteResult{}
	bunCommand := exec.Command("bun", "run", filePath)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	bunCommand.Stdout = &stdout
	bunCommand.Stderr = &stderr

	err := bunCommand.Run()
	result.Output = stdout.String()
	result.Stderr = stderr.String()

	if err == nil {
		return result
	}
	result.Error = err.Error()
	if exitError, ok := err.(*exec.ExitError); ok {
		result.ExitCode = exitError.ExitCode()
		return result
	}
	result.ExitCode = -1
	return result
}
