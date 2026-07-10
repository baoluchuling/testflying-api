package runner

import (
	"context"
	"fmt"
	"net/http"
	"os"
)

const (
	terminalNeedsHumanArtifactUploadClassification = "artifact_upload_pending"
	terminalNeedsHumanArtifactUploadSummary        = "package-agent completed but the runner cannot upload required artifacts yet."
	terminalNeedsHumanArtifactUploadAction         = "Upload package, symbols, report, and log artifacts before marking the build succeeded."
	preAgentWorkspaceFailureClassification         = "workspace_setup_failed"
	preAgentInputFailureClassification             = "build_input_write_failed"
	preAgentStartEventFailureClassification        = "start_event_post_failed"
	postAgentFinishEventFailureClassification      = "finish_event_post_failed"
	postAgentFinishEventFailureSummary             = "package-agent completed, but the runner could not persist the finish event or verify artifacts."
	postAgentFinishEventFailureAction              = "Inspect the runner workspace output and verify required artifacts before resolving the build."
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
		return completeWithOriginalError(
			ctx,
			client,
			build.ID,
			preAgentFailureRequest(
				cfg.RunnerID,
				preAgentWorkspaceFailureClassification,
				fmt.Sprintf("failed to create build workspace %q", outputDir),
				err,
			),
			err,
		)
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
		return completeWithOriginalError(
			ctx,
			client,
			build.ID,
			preAgentFailureRequest(
				cfg.RunnerID,
				preAgentInputFailureClassification,
				fmt.Sprintf("failed to write build input for workspace %q", workspace),
				err,
			),
			err,
		)
	}

	if err := client.PostEvent(ctx, build.ID, eventRequest{
		RunnerID:        cfg.RunnerID,
		Type:            "runner.build.started",
		Message:         "Build runner started package-agent execution.",
		LifecycleStatus: "building",
		Payload: map[string]interface{}{
			"workspace": workspace,
			"gitUrl":    build.GitURL,
			"gitRef":    build.GitRef,
		},
	}); err != nil {
		return completeWithOriginalError(
			ctx,
			client,
			build.ID,
			preAgentFailureRequest(
				cfg.RunnerID,
				preAgentStartEventFailureClassification,
				"failed to post runner.build.started before package-agent execution",
				err,
			),
			err,
		)
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
		completeErr := client.Complete(ctx, build.ID, failedCompletionRequest(cfg.RunnerID, runErr, reportErr, payload["report"]))
		if postErr != nil && completeErr != nil {
			return fmt.Errorf(
				"package-agent error: %v; event post error: %v; complete error: %w",
				runErr,
				postErr,
				completeErr,
			)
		}
		if postErr != nil {
			return fmt.Errorf("package-agent error: %v; event post error: %w", runErr, postErr)
		}
		if completeErr != nil {
			return fmt.Errorf("package-agent error: %v; complete error: %w", runErr, completeErr)
		}
		return runErr
	}

	if err := client.PostEvent(ctx, build.ID, eventRequest{
		RunnerID:        cfg.RunnerID,
		Type:            "runner.build.finished",
		Message:         "package-agent finished.",
		LifecycleStatus: "building",
		Payload:         payload,
	}); err != nil {
		return completeWithOriginalError(
			ctx,
			client,
			build.ID,
			finishEventFailureCompletionRequest(cfg.RunnerID, err),
			err,
		)
	}

	return client.Complete(ctx, build.ID, needsHumanCompletionRequest(cfg.RunnerID))
}

func failedCompletionRequest(
	runnerID string,
	runErr error,
	reportErr error,
	reportValue interface{},
) completeRequest {
	request := completeRequest{
		RunnerID: runnerID,
		Status:   "failed",
	}
	if report, ok := reportValue.(AgentReport); ok {
		request.Note = report.Summary
		request.FailureClassification = report.Classification
		request.FailureSummary = report.Summary
		return request
	}

	request.Note = fmt.Sprintf("package-agent failed: %v", runErr)
	request.FailureClassification = "package_agent_failed"
	request.FailureSummary = request.Note
	if reportErr != nil {
		request.FailureSummary = fmt.Sprintf("%s; report unavailable: %v", request.FailureSummary, reportErr)
	}
	return request
}

func needsHumanCompletionRequest(runnerID string) completeRequest {
	return completeRequest{
		RunnerID:              runnerID,
		Status:                "needs_human",
		Note:                  terminalNeedsHumanArtifactUploadSummary,
		FailureClassification: terminalNeedsHumanArtifactUploadClassification,
		FailureSummary:        terminalNeedsHumanArtifactUploadSummary,
		HumanAction:           terminalNeedsHumanArtifactUploadAction,
	}
}

func preAgentFailureRequest(
	runnerID string,
	classification string,
	summary string,
	cause error,
) completeRequest {
	note := fmt.Sprintf("%s: %v", summary, cause)
	return completeRequest{
		RunnerID:              runnerID,
		Status:                "failed",
		Note:                  note,
		FailureClassification: classification,
		FailureSummary:        note,
	}
}

func finishEventFailureCompletionRequest(runnerID string, cause error) completeRequest {
	note := fmt.Sprintf("%s: %v", postAgentFinishEventFailureSummary, cause)
	return completeRequest{
		RunnerID:              runnerID,
		Status:                "needs_human",
		Note:                  note,
		FailureClassification: postAgentFinishEventFailureClassification,
		FailureSummary:        note,
		HumanAction:           postAgentFinishEventFailureAction,
	}
}

func completeWithOriginalError(
	ctx context.Context,
	client *Client,
	buildID string,
	request completeRequest,
	originalErr error,
) error {
	if completeErr := client.Complete(ctx, buildID, request); completeErr != nil {
		return fmt.Errorf("original error: %v; complete error: %w", originalErr, completeErr)
	}
	return originalErr
}
