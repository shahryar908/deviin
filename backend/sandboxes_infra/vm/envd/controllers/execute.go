package controllers

import (
	"fmt"
	"runtime"

	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/sse"
	"github.com/shahryar908/devin/vm/envd/models"
	"github.com/shahryar908/devin/vm/envd/services"
)

func ExecuteJS(c fiber.Ctx) error {
	executeData := new(models.Execute)
	if err := c.Bind().Body(executeData); err != nil {
		return err
	}
	if err := services.WriteToFile(executeData); err != nil {
		return c.Status(500).JSON(fiber.Map{"error": err.Error()})
	}
	data := services.ExecuteJS()
	return c.Status(200).JSON(fiber.Map{
		"data":     data.Output,
		"output":   data.Output,
		"stdout":   data.Output,
		"stderr":   data.Stderr,
		"exitCode": data.ExitCode,
		"error":    data.Error,
	})
}

func ExecuteSync(c fiber.Ctx) error {
	executeCommand := models.ExecuteCommand{}
	if err := c.Bind().Body(&executeCommand); err != nil {
		return fmt.Errorf("failed to parse body: %v", err)
	}
	stdout, stderr, err := services.ExecuteCmd(executeCommand.Command)
	if err != nil {
		return err
	}
	return c.Status(fiber.StatusOK).JSON(fiber.Map{
		"stdout": stdout,
		"stderr": stderr,
	})
}

func ExecuteAsync(c fiber.Ctx, stream *sse.Stream) error {
	cmdStr := c.Query("cmd")
	if cmdStr == "" {
		return fmt.Errorf("missing 'cmd' query parameter")
	}
	var command []string
	if runtime.GOOS == "windows" {
		command = []string{"cmd", "/c", cmdStr}
	} else {
		command = []string{"sh", "-c", cmdStr}
	}
	events, err := services.ExecuteCmdBackground(command, stream.Context())
	if err != nil {
		return err
	}
	for {
		select {
		case msg, ok := <-events:
			if !ok {
				return nil
			}
			if err := stream.Event(sse.Event{Name: "message", Data: string(msg)}); err != nil {
				return err
			}
		case <-stream.Done():
			return stream.Err()
		}
	}
}
