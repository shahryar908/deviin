package router

import (
	"github.com/gofiber/fiber/v3"
	"github.com/gofiber/fiber/v3/middleware/sse"
	"github.com/shahryar908/devin/vm/envd/controllers"
)

func ExecuteRoute(app *fiber.App) {
	api := app.Group("/api")
	execute := api.Group("/execute")
	execute.Post("/js", controllers.ExecuteJS)
	execute.Post("/sync", controllers.ExecuteSync)
	execute.Get("/async", sse.New(sse.Config{
		Handler: controllers.ExecuteAsync,
	}))
}
