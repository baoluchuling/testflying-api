package runner

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
)

type AgentReport struct {
	Status         string   `json:"status"`
	Classification string   `json:"classification"`
	Summary        string   `json:"summary"`
	PackagePaths   []string `json:"packagePaths"`
	SymbolsPaths   []string `json:"symbolsPaths"`
	LogPaths       []string `json:"logPaths"`
	Adapter        *string  `json:"adapter"`
	MaxAttempts    int      `json:"maxAttempts"`
}

func RunPackageAgent(ctx context.Context, binary string, inputPath string, outputDir string) error {
	cmd := exec.CommandContext(ctx, binary, "build", "--input", inputPath, "--output", outputDir)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func ReadAgentReport(outputDir string) (AgentReport, error) {
	var report AgentReport
	data, err := os.ReadFile(filepath.Join(outputDir, "report.json"))
	if err != nil {
		return report, err
	}
	if err := json.Unmarshal(data, &report); err != nil {
		return report, err
	}
	return report, nil
}
