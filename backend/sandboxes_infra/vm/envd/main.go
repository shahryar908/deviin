package main

import (
	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/cors"
	"github.com/shahryar908/devin/vm/envd/router"
)

func main() {
	app := fiber.New()
	app.Use(cors.New())
	router.ExecuteRoute(app)
	if err := app.Listen(":3000"); err != nil {
		panic(err)
	}
}
