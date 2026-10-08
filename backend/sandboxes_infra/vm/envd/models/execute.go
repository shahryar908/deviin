package models

type Execute struct {
	Code string `json:"code"`
}

type ExecuteCommand struct {
	Command []string `json:"command"`
}
