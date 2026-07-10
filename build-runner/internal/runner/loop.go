package runner

import (
	"context"
	"fmt"
	"net/http"
	"os"
)

type BuildAssignment struct {
	ID             string            `json:"id"`
	AppID          string            `json:"appId"`
	Platform       string            `json:"platform"`
	Environment    string            `json:"environment"`
	GitURL         string            `json:"gitUrl"`
	GitRef         string            `json:"gitRef"`
	RepoSubpath    string            `json:"repoSubpath"`
	ArtifactType   string            `json:"artifactType"`
	CredentialRefs map[string]string `json:"credentialRefs"`
}

func Run(ctx context.Context, cfg Config) error {
	if err := cfg.Validate(); err != nil {
		return err
	}
	return RunOnce(ctx, cfg, http.DefaultClient)
}

func RunOnce(ctx context.Context, cfg Config, httpClient *http.Client) error {
	if err := cfg.Validate(); err != nil {
		return err
	}

	client := NewClient(cfg.ServerURL, cfg.Token, httpClient)
	if err := client.Heartbeat(ctx, cfg); err != nil {
		return err
	}

	build, err := client.Poll(ctx, cfg.RunnerID)
	if err != nil {
		return err
	}
	if build == nil {
		return nil
	}

	return handleBuild(ctx, client, cfg, *build)
}

func handleBuild(ctx context.Context, client *Client, cfg Config, build BuildAssignment) error {
	workspace := WorkspacePath(cfg.RootDir, build.ID)
	outputDir := OutputPath(workspace)
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return err
	}

	inputPath, err := WriteBuildInput(workspace, BuildInput{
		BuildID:        build.ID,
		ProjectDir:     ProjectDirPath(workspace, build.RepoSubpath),
		Platform:       build.Platform,
		Environment:    build.Environment,
		ArtifactType:   build.ArtifactType,
		CredentialRefs: build.CredentialRefs,
		MaxAttempts:    BuildRetryLimit,
	})
	if err != nil {
		return err
	}

	if err := client.PostEvent(ctx, build.ID, eventRequest{
		RunnerID:        cfg.RunnerID,
		Type:            "runner.build.started",
		Message:         "Build runner started package-agent execution.",
		LifecycleStatus: "running",
		Payload: map[string]interface{}{
			"workspace": workspace,
			"gitUrl":    build.GitURL,
			"gitRef":    build.GitRef,
		},
	}); err != nil {
		return err
	}

	runErr := RunPackageAgent(ctx, cfg.PackageAgentBin, inputPath, outputDir)
	report, reportErr := ReadAgentReport(outputDir)
	payload := map[string]interface{}{
		"workspace": workspace,
		"outputDir": outputDir,
	}
	if reportErr == nil {
		payload["report"] = report
	} else {
		payload["reportReadError"] = reportErr.Error()
	}

	if runErr != nil {
		payload["error"] = runErr.Error()
		postErr := client.PostEvent(ctx, build.ID, eventRequest{
			RunnerID: cfg.RunnerID,
			Type:     "runner.build.failed",
			Message:  fmt.Sprintf("package-agent failed: %v", runErr),
			Payload:  payload,
		})
		if postErr != nil {
			return fmt.Errorf("package-agent error: %v; event post error: %w", runErr, postErr)
		}
		return runErr
	}

	return client.PostEvent(ctx, build.ID, eventRequest{
		RunnerID:        cfg.RunnerID,
		Type:            "runner.build.finished",
		Message:         "package-agent finished.",
		LifecycleStatus: "running",
		Payload:         payload,
	})
}
