package runner

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

type AgentReport struct {
	Status         string   `json:"status"`
	Classification string   `json:"classification"`
	Summary        string   `json:"summary"`
	HumanAction    string   `json:"humanAction"`
	PackagePaths   []string `json:"packagePaths"`
	SymbolsPaths   []string `json:"symbolsPaths"`
	LogPaths       []string `json:"logPaths"`
	Adapter        *string  `json:"adapter"`
	MaxAttempts    int      `json:"maxAttempts"`
}

type ArtifactUpload struct {
	ArtifactType string
	Path         string
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

func ArtifactUploadsFromReport(outputDir string, report AgentReport) ([]ArtifactUpload, error) {
	uploads := []ArtifactUpload{
		{
			ArtifactType: "report",
			Path:         filepath.Join(outputDir, "report.json"),
		},
	}

	required := []struct {
		artifactType string
		paths        []string
	}{
		{artifactType: "package", paths: report.PackagePaths},
		{artifactType: "symbols", paths: report.SymbolsPaths},
		{artifactType: "log", paths: report.LogPaths},
	}

	for _, item := range required {
		if len(item.paths) == 0 {
			return nil, fmt.Errorf("report is missing %s paths", item.artifactType)
		}
		if len(item.paths) > 1 {
			return nil, fmt.Errorf("report lists multiple %s paths", item.artifactType)
		}
		resolved, err := resolveArtifactPath(outputDir, item.paths[0])
		if err != nil {
			return nil, fmt.Errorf("%s artifact path is invalid: %w", item.artifactType, err)
		}
		uploads = append(uploads, ArtifactUpload{
			ArtifactType: item.artifactType,
			Path:         resolved,
		})
	}

	for _, upload := range uploads {
		info, err := os.Stat(upload.Path)
		if err != nil {
			return nil, fmt.Errorf("%s artifact %q is unreadable: %w", upload.ArtifactType, upload.Path, err)
		}
		if info.IsDir() {
			return nil, fmt.Errorf("%s artifact %q is a directory", upload.ArtifactType, upload.Path)
		}
	}

	return uploads, nil
}

func CompleteStatusFromReport(status string) string {
	switch status {
	case "success":
		return "succeeded"
	default:
		return status
	}
}

func resolveArtifactPath(outputDir string, pathValue string) (string, error) {
	if pathValue == "" {
		return "", fmt.Errorf("path is blank")
	}
	if filepath.IsAbs(pathValue) {
		return pathValue, nil
	}
	return filepath.Join(outputDir, pathValue), nil
}
