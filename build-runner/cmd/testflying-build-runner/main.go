package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"strings"

	"testflying-build-runner/internal/runner"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	cfg := runner.Config{
		RunnerID:            os.Getenv("TESTFLYING_BUILD_RUNNER_ID"),
		Name:                os.Getenv("TESTFLYING_BUILD_RUNNER_NAME"),
		Token:               os.Getenv("TESTFLYING_BUILD_RUNNER_TOKEN"),
		ServerURL:           os.Getenv("TESTFLYING_BUILD_RUNNER_SERVER_URL"),
		RootDir:             os.Getenv("TESTFLYING_BUILD_RUNNER_ROOT"),
		PackageAgentBin:     os.Getenv("TESTFLYING_PACKAGE_AGENT_BIN"),
		Version:             envOrDefault("TESTFLYING_BUILD_RUNNER_VERSION", "dev"),
		PackageAgentVersion: envOrDefault("TESTFLYING_PACKAGE_AGENT_VERSION", "dev"),
		Labels:              splitCSV(os.Getenv("TESTFLYING_BUILD_RUNNER_LABELS")),
		Platforms:           splitCSV(os.Getenv("TESTFLYING_BUILD_RUNNER_PLATFORMS")),
		LLMAdapters:         splitCSV(os.Getenv("TESTFLYING_BUILD_RUNNER_LLM_ADAPTERS")),
		Capacity:            1,
	}
	if len(cfg.Platforms) == 0 {
		cfg.Platforms = []string{"ios"}
	}
	if len(cfg.LLMAdapters) == 0 {
		cfg.LLMAdapters = []string{"codex"}
	}

	if err := runner.Run(ctx, cfg); err != nil {
		log.Fatal(err)
	}
}

func envOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func splitCSV(raw string) []string {
	if strings.TrimSpace(raw) == "" {
		return nil
	}

	parts := strings.Split(raw, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		value := strings.TrimSpace(part)
		if value != "" {
			values = append(values, value)
		}
	}
	return values
}
