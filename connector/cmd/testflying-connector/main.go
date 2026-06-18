package main

import (
	"log"
	"net/http"

	"github.com/baoluchuling/testflying-server/connector/internal/connector"
)

func main() {
	settings := connector.LoadSettingsFromEnv()
	server, err := connector.NewServer(settings)
	if err != nil {
		log.Fatalf("configure connector: %v", err)
	}

	log.Printf(
		"testflying-connector listening on %s account=%s mode=%s",
		settings.ListenAddr,
		settings.DeveloperAccountID,
		settings.StoreMode,
	)
	if err := http.ListenAndServe(settings.ListenAddr, server); err != nil {
		log.Fatal(err)
	}
}
