package runner

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type BuildInput struct {
	BuildID        string            `json:"buildId"`
	ProjectDir     string            `json:"projectDir"`
	Platform       string            `json:"platform"`
	Environment    string            `json:"environment"`
	ArtifactType   string            `json:"artifactType"`
	CredentialRefs map[string]string `json:"credentialRefs"`
	MaxAttempts    int               `json:"maxAttempts"`
}

func WorkspacePath(root string, buildID string) string {
	return filepath.Join(root, "workspaces", buildID)
}

func OutputPath(workspace string) string {
	return filepath.Join(workspace, "output")
}

func ProjectDirPath(workspace string, repoSubpath string) string {
	projectRoot := filepath.Join(workspace, "project")
	if repoSubpath == "" {
		return projectRoot
	}
	return filepath.Join(projectRoot, repoSubpath)
}

func WriteBuildInput(workspace string, input BuildInput) (string, error) {
	path := filepath.Join(workspace, "build-input.json")
	if err := os.MkdirAll(workspace, 0o755); err != nil {
		return "", err
	}
	data, err := json.MarshalIndent(input, "", "  ")
	if err != nil {
		return "", err
	}
	return path, os.WriteFile(path, data, 0o600)
}
