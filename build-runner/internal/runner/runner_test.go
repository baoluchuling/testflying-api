package runner

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestWorkspacePathUsesBuildID(t *testing.T) {
	root := t.TempDir()
	path := WorkspacePath(root, "build-123")

	want := filepath.Join(root, "workspaces", "build-123")
	if path != want {
		t.Fatalf("WorkspacePath() = %q, want %q", path, want)
	}
}

func TestWriteBuildInputCreatesJSON(t *testing.T) {
	root := t.TempDir()
	input := BuildInput{
		BuildID:        "build-1",
		ProjectDir:     root,
		Platform:       "ios",
		Environment:    "development",
		ArtifactType:   "ipa",
		CredentialRefs: map[string]string{"git": "git-main"},
		MaxAttempts:    BuildRetryLimit,
	}

	path, err := WriteBuildInput(root, input)
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}

	var got BuildInput
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}

	if got.BuildID != input.BuildID {
		t.Fatalf("buildId = %q, want %q", got.BuildID, input.BuildID)
	}
	if got.ProjectDir != input.ProjectDir {
		t.Fatalf("projectDir = %q, want %q", got.ProjectDir, input.ProjectDir)
	}
	if got.Platform != input.Platform {
		t.Fatalf("platform = %q, want %q", got.Platform, input.Platform)
	}
	if got.Environment != input.Environment {
		t.Fatalf("environment = %q, want %q", got.Environment, input.Environment)
	}
	if got.ArtifactType != input.ArtifactType {
		t.Fatalf("artifactType = %q, want %q", got.ArtifactType, input.ArtifactType)
	}
	if got.CredentialRefs["git"] != input.CredentialRefs["git"] {
		t.Fatalf("credentialRefs[git] = %q, want %q", got.CredentialRefs["git"], input.CredentialRefs["git"])
	}
	if got.MaxAttempts != BuildRetryLimit {
		t.Fatalf("maxAttempts = %d, want %d", got.MaxAttempts, BuildRetryLimit)
	}
}

func TestRunOnceNoBuildOnlyHeartbeatsAndPolls(t *testing.T) {
	var heartbeatCalls int
	var pollCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			heartbeatCalls++
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			pollCalls++
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":null}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             t.TempDir(),
		PackageAgentBin:     "package-agent",
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	if err := RunOnce(context.Background(), cfg, server.Client()); err != nil {
		t.Fatal(err)
	}

	if heartbeatCalls != 1 {
		t.Fatalf("heartbeat calls = %d, want 1", heartbeatCalls)
	}
	if pollCalls != 1 {
		t.Fatalf("poll calls = %d, want 1", pollCalls)
	}
}

func TestConfigValidateRequiresFieldsAndCapacityOne(t *testing.T) {
	valid := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           "https://example.test",
		RootDir:             t.TempDir(),
		PackageAgentBin:     "/tmp/package-agent",
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Capacity:            1,
	}
	if err := valid.Validate(); err != nil {
		t.Fatalf("Validate() unexpected error: %v", err)
	}

	cases := []struct {
		name string
		cfg  Config
		want string
	}{
		{
			name: "missing runner id",
			cfg: func() Config {
				cfg := valid
				cfg.RunnerID = ""
				return cfg
			}(),
			want: "RunnerID is required",
		},
		{
			name: "missing name",
			cfg: func() Config {
				cfg := valid
				cfg.Name = " "
				return cfg
			}(),
			want: "Name is required",
		},
		{
			name: "missing token",
			cfg: func() Config {
				cfg := valid
				cfg.Token = ""
				return cfg
			}(),
			want: "Token is required",
		},
		{
			name: "missing server url",
			cfg: func() Config {
				cfg := valid
				cfg.ServerURL = ""
				return cfg
			}(),
			want: "ServerURL is required",
		},
		{
			name: "missing root dir",
			cfg: func() Config {
				cfg := valid
				cfg.RootDir = ""
				return cfg
			}(),
			want: "RootDir is required",
		},
		{
			name: "missing package agent bin",
			cfg: func() Config {
				cfg := valid
				cfg.PackageAgentBin = ""
				return cfg
			}(),
			want: "PackageAgentBin is required",
		},
		{
			name: "missing capacity",
			cfg: func() Config {
				cfg := valid
				cfg.Capacity = 0
				return cfg
			}(),
			want: "Capacity is required",
		},
		{
			name: "capacity must stay one",
			cfg: func() Config {
				cfg := valid
				cfg.Capacity = 2
				return cfg
			}(),
			want: "Capacity must be 1 in the current implementation",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := tc.cfg.Validate()
			if err == nil {
				t.Fatal("Validate() error = nil, want error")
			}
			if err.Error() != tc.want {
				t.Fatalf("Validate() error = %q, want %q", err.Error(), tc.want)
			}
		})
	}
}

func TestRunOnceAssignedBuildRunsPackageAgentPostsEventsAndCompletesNeedsHuman(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := writeFakePackageAgentWithFiles(t, root, 0, `{
  "status": "success",
  "classification": "build_succeeded",
  "summary": "fake package-agent completed",
  "version": "1.2.3",
  "buildNumber": "42",
  "commitSha": "abc123def456",
  "packagePaths": ["app.ipa"],
  "symbolsPaths": ["app.dSYM.zip", "symbols/additional.dSYM.zip"],
  "logPaths": ["runner.log", "logs/xcode.log"],
  "maxAttempts": 5
}`, map[string]string{
		"app.ipa":                     "ipa-bytes",
		"app.dSYM.zip":                "symbols-bytes",
		"symbols/additional.dSYM.zip": "additional-symbols",
		"runner.log":                  "runner-log",
		"logs/xcode.log":              "xcode-log",
	})

	type capturedEvent struct {
		Type            string                 `json:"type"`
		LifecycleStatus string                 `json:"lifecycleStatus"`
		Payload         map[string]interface{} `json:"payload"`
	}
	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Version               string `json:"version"`
		BuildNumber           string `json:"buildNumber"`
		CommitSHA             string `json:"commitSha"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
		HumanAction           string `json:"humanAction"`
	}
	type uploadedArtifact struct {
		ArtifactType string
		FileName     string
		Body         string
	}

	var heartbeatBody heartbeatRequest
	var pollBody pollRequest
	events := make([]capturedEvent, 0, 2)
	completes := make([]capturedComplete, 0, 1)
	uploads := make([]uploadedArtifact, 0, 4)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			if err := json.NewDecoder(r.Body).Decode(&heartbeatBody); err != nil {
				t.Fatalf("decode heartbeat: %v", err)
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			if err := json.NewDecoder(r.Body).Decode(&pollBody); err != nil {
				t.Fatalf("decode poll: %v", err)
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			var event capturedEvent
			if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
				t.Fatalf("decode event: %v", err)
			}
			events = append(events, event)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/artifacts":
			if err := r.ParseMultipartForm(1 << 20); err != nil {
				t.Fatalf("parse multipart form: %v", err)
			}
			file, header, err := r.FormFile("file")
			if err != nil {
				t.Fatalf("read artifact file: %v", err)
			}
			defer file.Close()
			data, err := io.ReadAll(file)
			if err != nil {
				t.Fatalf("read artifact body: %v", err)
			}
			uploads = append(uploads, uploadedArtifact{
				ArtifactType: r.FormValue("artifactType"),
				FileName:     header.Filename,
				Body:         string(data),
			})
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     packageAgentBin,
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	if err := RunOnce(context.Background(), cfg, server.Client()); err != nil {
		t.Fatal(err)
	}

	if heartbeatBody.RunnerID != cfg.RunnerID {
		t.Fatalf("heartbeat runnerId = %q, want %q", heartbeatBody.RunnerID, cfg.RunnerID)
	}
	if pollBody.RunnerID != cfg.RunnerID {
		t.Fatalf("poll runnerId = %q, want %q", pollBody.RunnerID, cfg.RunnerID)
	}

	workspace := WorkspacePath(root, "build-123")
	inputPath := filepath.Join(workspace, "build-input.json")
	outputDir := OutputPath(workspace)

	if _, err := os.Stat(workspace); err != nil {
		t.Fatalf("workspace stat: %v", err)
	}
	if _, err := os.Stat(inputPath); err != nil {
		t.Fatalf("build-input stat: %v", err)
	}

	inputData, err := os.ReadFile(inputPath)
	if err != nil {
		t.Fatal(err)
	}
	var gotInput BuildInput
	if err := json.Unmarshal(inputData, &gotInput); err != nil {
		t.Fatal(err)
	}
	if gotInput.ProjectDir != filepath.Join(workspace, "project", "ios", "app") {
		t.Fatalf("projectDir = %q", gotInput.ProjectDir)
	}
	if gotInput.MaxAttempts != BuildRetryLimit {
		t.Fatalf("maxAttempts = %d, want %d", gotInput.MaxAttempts, BuildRetryLimit)
	}

	invocationData, err := os.ReadFile(filepath.Join(outputDir, "invocation.txt"))
	if err != nil {
		t.Fatal(err)
	}
	invocation := string(invocationData)
	if !strings.Contains(invocation, "input="+inputPath) {
		t.Fatalf("invocation missing input path: %q", invocation)
	}
	if !strings.Contains(invocation, "output="+outputDir) {
		t.Fatalf("invocation missing output path: %q", invocation)
	}

	if len(events) != 2 {
		t.Fatalf("event count = %d, want 2", len(events))
	}
	if events[0].Type != "runner.build.started" {
		t.Fatalf("first event type = %q", events[0].Type)
	}
	if events[0].LifecycleStatus != "building" {
		t.Fatalf("first event lifecycleStatus = %q", events[0].LifecycleStatus)
	}
	if events[0].Payload["workspace"] != workspace {
		t.Fatalf("first event workspace = %#v, want %q", events[0].Payload["workspace"], workspace)
	}
	if events[1].Type != "runner.build.finished" {
		t.Fatalf("second event type = %q", events[1].Type)
	}
	if events[1].LifecycleStatus != "building" {
		t.Fatalf("second event lifecycleStatus = %q", events[1].LifecycleStatus)
	}
	if events[1].Payload["workspace"] != workspace {
		t.Fatalf("second event workspace = %#v, want %q", events[1].Payload["workspace"], workspace)
	}
	if events[1].Payload["outputDir"] != outputDir {
		t.Fatalf("second event outputDir = %#v, want %q", events[1].Payload["outputDir"], outputDir)
	}

	reportPayload, ok := events[1].Payload["report"].(map[string]interface{})
	if !ok {
		t.Fatalf("second event report payload type = %T", events[1].Payload["report"])
	}
	if reportPayload["summary"] != "fake package-agent completed" {
		t.Fatalf("report summary = %#v", reportPayload["summary"])
	}
	if reportPayload["maxAttempts"] != float64(BuildRetryLimit) {
		t.Fatalf("report maxAttempts = %#v", reportPayload["maxAttempts"])
	}

	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].RunnerID != cfg.RunnerID {
		t.Fatalf("complete runnerId = %q, want %q", completes[0].RunnerID, cfg.RunnerID)
	}
	if completes[0].Status != "succeeded" {
		t.Fatalf("complete status = %q, want %q", completes[0].Status, "succeeded")
	}
	if completes[0].Version != "1.2.3" {
		t.Fatalf("complete version = %q", completes[0].Version)
	}
	if completes[0].BuildNumber != "42" {
		t.Fatalf("complete buildNumber = %q", completes[0].BuildNumber)
	}
	if completes[0].CommitSHA != "abc123def456" {
		t.Fatalf("complete commitSha = %q", completes[0].CommitSHA)
	}
	if completes[0].FailureClassification != "" {
		t.Fatalf("complete failureClassification = %q, want empty", completes[0].FailureClassification)
	}
	if completes[0].FailureSummary != "" {
		t.Fatalf("complete failureSummary = %q, want empty", completes[0].FailureSummary)
	}
	if completes[0].Note != "fake package-agent completed" {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if completes[0].HumanAction != "" {
		t.Fatalf("complete humanAction = %q, want empty", completes[0].HumanAction)
	}

	if len(uploads) != 6 {
		t.Fatalf("upload count = %d, want 6", len(uploads))
	}
	wantUploads := []uploadedArtifact{
		{ArtifactType: "report", FileName: "report.json", Body: "{\n  \"status\": \"success\",\n  \"classification\": \"build_succeeded\",\n  \"summary\": \"fake package-agent completed\",\n  \"version\": \"1.2.3\",\n  \"buildNumber\": \"42\",\n  \"commitSha\": \"abc123def456\",\n  \"packagePaths\": [\"app.ipa\"],\n  \"symbolsPaths\": [\"app.dSYM.zip\", \"symbols/additional.dSYM.zip\"],\n  \"logPaths\": [\"runner.log\", \"logs/xcode.log\"],\n  \"maxAttempts\": 5\n}\n"},
		{ArtifactType: "package", FileName: "app.ipa", Body: "ipa-bytes\n"},
		{ArtifactType: "symbols", FileName: "app.dSYM.zip", Body: "symbols-bytes\n"},
		{ArtifactType: "symbols", FileName: "additional.dSYM.zip", Body: "additional-symbols\n"},
		{ArtifactType: "log", FileName: "runner.log", Body: "runner-log\n"},
		{ArtifactType: "log", FileName: "xcode.log", Body: "xcode-log\n"},
	}
	for index, want := range wantUploads {
		if uploads[index] != want {
			t.Fatalf("upload[%d] = %#v, want %#v", index, uploads[index], want)
		}
	}
}

func TestRunOnceAssignedBuildCompletesFailedWhenPackageAgentExitsNonZero(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := writeFakePackageAgent(t, root, 7, `{
  "status": "failed",
  "classification": "codesign_failed",
  "summary": "codesign step failed",
  "packagePaths": [],
  "symbolsPaths": [],
  "logPaths": ["runner.log"],
  "maxAttempts": 5
}`)

	type capturedEvent struct {
		Type            string                 `json:"type"`
		LifecycleStatus string                 `json:"lifecycleStatus"`
		Message         string                 `json:"message"`
		Payload         map[string]interface{} `json:"payload"`
	}
	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
	}

	events := make([]capturedEvent, 0, 2)
	completes := make([]capturedComplete, 0, 1)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			var event capturedEvent
			if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
				t.Fatalf("decode event: %v", err)
			}
			events = append(events, event)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     packageAgentBin,
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	err := RunOnce(context.Background(), cfg, server.Client())
	if err == nil {
		t.Fatal("RunOnce() error = nil, want error")
	}
	var exitErr *exec.ExitError
	if !errors.As(err, &exitErr) {
		t.Fatalf("RunOnce() error type = %T, want *os.ExitError", err)
	}
	if exitErr.ExitCode() != 7 {
		t.Fatalf("RunOnce() exit code = %d, want 7", exitErr.ExitCode())
	}

	if len(events) != 2 {
		t.Fatalf("event count = %d, want 2", len(events))
	}
	if events[0].Type != "runner.build.started" {
		t.Fatalf("first event type = %q", events[0].Type)
	}
	if events[1].Type != "runner.build.failed" {
		t.Fatalf("second event type = %q, want %q", events[1].Type, "runner.build.failed")
	}
	if events[1].Message != "package-agent failed: exit status 7" {
		t.Fatalf("second event message = %q", events[1].Message)
	}
	if events[1].Payload["error"] != "exit status 7" {
		t.Fatalf("second event error payload = %#v", events[1].Payload["error"])
	}
	reportPayload, ok := events[1].Payload["report"].(map[string]interface{})
	if !ok {
		t.Fatalf("second event report payload type = %T", events[1].Payload["report"])
	}
	if reportPayload["classification"] != "codesign_failed" {
		t.Fatalf("report classification = %#v", reportPayload["classification"])
	}
	if reportPayload["summary"] != "codesign step failed" {
		t.Fatalf("report summary = %#v", reportPayload["summary"])
	}

	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "failed" {
		t.Fatalf("complete status = %q, want %q", completes[0].Status, "failed")
	}
	if completes[0].FailureClassification != "codesign_failed" {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if completes[0].FailureSummary != "codesign step failed" {
		t.Fatalf("complete failureSummary = %q", completes[0].FailureSummary)
	}
	if completes[0].Note != "codesign step failed" {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
}

func TestRunOnceAssignedBuildCompletesNeedsHumanWhenPackageAgentExitsTwo(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := writeFakePackageAgent(t, root, 2, `{
  "status": "needs_human",
  "classification": "missing_artifacts",
  "summary": "Automatic success requires package, symbols, and logs.",
  "humanAction": "Upload the missing package, symbols, and logs, then resolve the build.",
  "packagePaths": [],
  "symbolsPaths": [],
  "logPaths": ["runner.log"],
  "maxAttempts": 5
}`)

	type capturedEvent struct {
		Type            string                 `json:"type"`
		LifecycleStatus string                 `json:"lifecycleStatus"`
		Message         string                 `json:"message"`
		Payload         map[string]interface{} `json:"payload"`
	}
	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
		HumanAction           string `json:"humanAction"`
	}

	events := make([]capturedEvent, 0, 2)
	completes := make([]capturedComplete, 0, 1)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			var event capturedEvent
			if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
				t.Fatalf("decode event: %v", err)
			}
			events = append(events, event)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     packageAgentBin,
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	if err := RunOnce(context.Background(), cfg, server.Client()); err != nil {
		t.Fatalf("RunOnce() error = %v, want nil", err)
	}

	if len(events) != 2 {
		t.Fatalf("event count = %d, want 2", len(events))
	}
	if events[0].Type != "runner.build.started" {
		t.Fatalf("first event type = %q", events[0].Type)
	}
	if events[1].Type != "runner.build.needs_human" {
		t.Fatalf("second event type = %q, want %q", events[1].Type, "runner.build.needs_human")
	}
	if events[1].Message != "Upload the missing package, symbols, and logs, then resolve the build." {
		t.Fatalf("second event message = %q", events[1].Message)
	}
	reportPayload, ok := events[1].Payload["report"].(map[string]interface{})
	if !ok {
		t.Fatalf("second event report payload type = %T", events[1].Payload["report"])
	}
	if reportPayload["classification"] != "missing_artifacts" {
		t.Fatalf("report classification = %#v", reportPayload["classification"])
	}
	if reportPayload["summary"] != "Automatic success requires package, symbols, and logs." {
		t.Fatalf("report summary = %#v", reportPayload["summary"])
	}
	if reportPayload["humanAction"] != "Upload the missing package, symbols, and logs, then resolve the build." {
		t.Fatalf("report humanAction = %#v", reportPayload["humanAction"])
	}

	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "needs_human" {
		t.Fatalf("complete status = %q, want needs_human", completes[0].Status)
	}
	if completes[0].FailureClassification != "missing_artifacts" {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if completes[0].FailureSummary != "Automatic success requires package, symbols, and logs." {
		t.Fatalf("complete failureSummary = %q", completes[0].FailureSummary)
	}
	if completes[0].Note != "Automatic success requires package, symbols, and logs." {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if completes[0].HumanAction != "Upload the missing package, symbols, and logs, then resolve the build." {
		t.Fatalf("complete humanAction = %q", completes[0].HumanAction)
	}
}

func TestRunOnceAssignedBuildCompletesFailedWhenWorkspaceSetupFails(t *testing.T) {
	root := filepath.Join(t.TempDir(), "root-file")
	if err := os.WriteFile(root, []byte("not a directory"), 0o600); err != nil {
		t.Fatal(err)
	}

	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
	}

	completes := make([]capturedComplete, 0, 1)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/events":
			t.Fatal("events should not be posted when workspace setup fails")
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     "/path/to/package-agent",
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	err := RunOnce(context.Background(), cfg, server.Client())
	if err == nil {
		t.Fatal("RunOnce() error = nil, want error")
	}
	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "failed" {
		t.Fatalf("complete status = %q, want failed", completes[0].Status)
	}
	if completes[0].FailureClassification != preAgentWorkspaceFailureClassification {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if !strings.Contains(completes[0].Note, "failed to create build workspace") {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if completes[0].FailureSummary != completes[0].Note {
		t.Fatalf("complete failureSummary = %q, want note match", completes[0].FailureSummary)
	}
}

func TestRunOnceAssignedBuildCompletesFailedWhenStartEventPostFails(t *testing.T) {
	root := t.TempDir()

	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
	}

	var eventCalls int
	completes := make([]capturedComplete, 0, 1)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			eventCalls++
			http.Error(w, "start event rejected", http.StatusBadGateway)
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     "/path/to/package-agent",
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	err := RunOnce(context.Background(), cfg, server.Client())
	if err == nil {
		t.Fatal("RunOnce() error = nil, want error")
	}
	if eventCalls != 1 {
		t.Fatalf("event calls = %d, want 1", eventCalls)
	}
	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "failed" {
		t.Fatalf("complete status = %q, want failed", completes[0].Status)
	}
	if completes[0].FailureClassification != preAgentStartEventFailureClassification {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if !strings.Contains(completes[0].Note, "failed to post runner.build.started") {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
}

func TestRunOnceAssignedBuildCompletesNeedsHumanWhenFinishEventPostFails(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := writeFakePackageAgentWithFiles(t, root, 0, `{
  "status": "success",
  "classification": "build_succeeded",
  "summary": "fake package-agent completed",
  "packagePaths": ["app.ipa"],
  "symbolsPaths": ["app.dSYM.zip"],
  "logPaths": ["runner.log"],
  "maxAttempts": 5
}`, map[string]string{
		"app.ipa":      "ipa-bytes",
		"app.dSYM.zip": "symbols-bytes",
		"runner.log":   "runner-log",
	})

	type capturedEvent struct {
		Type string `json:"type"`
	}
	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
		HumanAction           string `json:"humanAction"`
	}

	events := make([]capturedEvent, 0, 2)
	completes := make([]capturedComplete, 0, 1)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			var event capturedEvent
			if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
				t.Fatalf("decode event: %v", err)
			}
			events = append(events, event)
			if event.Type == "runner.build.finished" {
				http.Error(w, "finish event rejected", http.StatusBadGateway)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/artifacts":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     packageAgentBin,
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	err := RunOnce(context.Background(), cfg, server.Client())
	if err == nil {
		t.Fatal("RunOnce() error = nil, want error")
	}
	if len(events) != 2 {
		t.Fatalf("event count = %d, want 2", len(events))
	}
	if events[0].Type != "runner.build.started" || events[1].Type != "runner.build.finished" {
		t.Fatalf("event types = %#v", events)
	}
	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "needs_human" {
		t.Fatalf("complete status = %q, want needs_human", completes[0].Status)
	}
	if completes[0].FailureClassification != postAgentFinishEventFailureClassification {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if !strings.Contains(completes[0].Note, postAgentFinishEventFailureSummary) {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if completes[0].FailureSummary != completes[0].Note {
		t.Fatalf("complete failureSummary = %q, want note match", completes[0].FailureSummary)
	}
	if completes[0].HumanAction != postAgentFinishEventFailureAction {
		t.Fatalf("complete humanAction = %q", completes[0].HumanAction)
	}
}

func TestRunOnceAssignedBuildCompletesNeedsHumanWhenArtifactUploadFails(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := writeFakePackageAgent(t, root, 0, `{
  "status": "success",
  "classification": "build_succeeded",
  "summary": "fake package-agent completed",
  "packagePaths": ["missing.ipa"],
  "symbolsPaths": ["app.dSYM.zip"],
  "logPaths": ["runner.log"],
  "maxAttempts": 5
}`)

	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
		HumanAction           string `json:"humanAction"`
	}

	completes := make([]capturedComplete, 0, 1)
	var eventCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			eventCalls++
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/artifacts":
			t.Fatal("artifact upload should not be attempted when the first required file is missing")
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     packageAgentBin,
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	err := RunOnce(context.Background(), cfg, server.Client())
	if err == nil {
		t.Fatal("RunOnce() error = nil, want error")
	}
	if eventCalls != 1 {
		t.Fatalf("event calls = %d, want 1", eventCalls)
	}
	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "needs_human" {
		t.Fatalf("complete status = %q, want needs_human", completes[0].Status)
	}
	if completes[0].FailureClassification != postAgentArtifactUploadFailureClassification {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if !strings.Contains(completes[0].Note, "required artifact upload failed") {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if !strings.Contains(completes[0].Note, "missing.ipa") {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if completes[0].FailureSummary != completes[0].Note {
		t.Fatalf("complete failureSummary = %q, want note match", completes[0].FailureSummary)
	}
	if completes[0].HumanAction != postAgentArtifactUploadAction {
		t.Fatalf("complete humanAction = %q", completes[0].HumanAction)
	}
}

func TestArtifactUploadsFromReportRejectsPathsOutsideOutputDir(t *testing.T) {
	outputDir := t.TempDir()
	insidePackage := filepath.Join(outputDir, "app.ipa")
	insideSymbols := filepath.Join(outputDir, "app.dSYM.zip")
	insideLog := filepath.Join(outputDir, "runner.log")
	for _, path := range []string{insidePackage, insideSymbols, insideLog} {
		if err := os.WriteFile(path, []byte("artifact"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	outsideDir := t.TempDir()
	outsideFile := filepath.Join(outsideDir, "secret.log")
	if err := os.WriteFile(outsideFile, []byte("secret"), 0o600); err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		name        string
		packagePath string
	}{
		{name: "parent traversal", packagePath: "../secret.ipa"},
		{name: "outside absolute path", packagePath: outsideFile},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ArtifactUploadsFromReport(outputDir, AgentReport{
				PackagePaths: []string{tc.packagePath},
				SymbolsPaths: []string{"app.dSYM.zip"},
				LogPaths:     []string{"runner.log"},
			})
			if err == nil {
				t.Fatal("ArtifactUploadsFromReport() error = nil, want error")
			}
			if !strings.Contains(err.Error(), "invalid") {
				t.Fatalf("ArtifactUploadsFromReport() error = %q", err)
			}
		})
	}
}

func TestRunOnceAssignedBuildCompletesNeedsHumanWhenSuccessReportEscapesOutputDir(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := writeFakePackageAgentWithFiles(t, root, 0, `{
  "status": "success",
  "classification": "build_succeeded",
  "summary": "fake package-agent completed",
  "packagePaths": ["../secret.ipa"],
  "symbolsPaths": ["app.dSYM.zip"],
  "logPaths": ["runner.log"],
  "maxAttempts": 5
}`, map[string]string{
		"app.dSYM.zip": "symbols-bytes",
		"runner.log":   "runner-log",
	})

	type capturedComplete struct {
		RunnerID              string `json:"runnerId"`
		Status                string `json:"status"`
		Note                  string `json:"note"`
		FailureClassification string `json:"failureClassification"`
		FailureSummary        string `json:"failureSummary"`
		HumanAction           string `json:"humanAction"`
	}

	completes := make([]capturedComplete, 0, 1)
	var eventCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/admin/api/build-runners/heartbeat":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/poll":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"build":{
				"id":"build-123",
				"appId":"app-1",
				"platform":"ios",
				"environment":"development",
				"gitUrl":"https://example.com/repo.git",
				"gitRef":"main",
				"repoSubpath":"ios/app",
				"artifactType":"ipa",
				"credentialRefs":{"git":"git-main"}
			}}`))
		case "/admin/api/build-runners/builds/build-123/events":
			eventCalls++
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/complete":
			var complete capturedComplete
			if err := json.NewDecoder(r.Body).Decode(&complete); err != nil {
				t.Fatalf("decode complete: %v", err)
			}
			completes = append(completes, complete)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"ok":true}`))
		case "/admin/api/build-runners/builds/build-123/artifacts":
			t.Fatal("artifact upload should not be attempted when report escapes output directory")
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	cfg := Config{
		RunnerID:            "runner-1",
		Name:                "Runner 1",
		Token:               "token",
		ServerURL:           server.URL,
		RootDir:             root,
		PackageAgentBin:     packageAgentBin,
		Version:             "0.1.0",
		PackageAgentVersion: "0.1.0",
		Labels:              []string{"ios-release"},
		Platforms:           []string{"ios"},
		LLMAdapters:         []string{"codex"},
		Capacity:            1,
	}

	err := RunOnce(context.Background(), cfg, server.Client())
	if err == nil {
		t.Fatal("RunOnce() error = nil, want error")
	}
	if eventCalls != 1 {
		t.Fatalf("event calls = %d, want 1", eventCalls)
	}
	if len(completes) != 1 {
		t.Fatalf("complete count = %d, want 1", len(completes))
	}
	if completes[0].Status != "needs_human" {
		t.Fatalf("complete status = %q, want needs_human", completes[0].Status)
	}
	if completes[0].FailureClassification != postAgentArtifactUploadFailureClassification {
		t.Fatalf("complete failureClassification = %q", completes[0].FailureClassification)
	}
	if !strings.Contains(completes[0].Note, "escapes output directory") {
		t.Fatalf("complete note = %q", completes[0].Note)
	}
	if completes[0].HumanAction != postAgentArtifactUploadAction {
		t.Fatalf("complete humanAction = %q", completes[0].HumanAction)
	}
}

func TestCompleteStatusFromReport(t *testing.T) {
	if got := CompleteStatusFromReport("success"); got != "succeeded" {
		t.Fatalf("CompleteStatusFromReport(success) = %q, want succeeded", got)
	}
	if got := CompleteStatusFromReport("needs_human"); got != "needs_human" {
		t.Fatalf("CompleteStatusFromReport(needs_human) = %q, want needs_human", got)
	}
	if got := CompleteStatusFromReport("failed"); got != "failed" {
		t.Fatalf("CompleteStatusFromReport(failed) = %q, want failed", got)
	}
}

func writeFakePackageAgent(t *testing.T, root string, exitCode int, reportJSON string) string {
	return writeFakePackageAgentWithFiles(t, root, exitCode, reportJSON, nil)
}

func writeFakePackageAgentWithFiles(
	t *testing.T,
	root string,
	exitCode int,
	reportJSON string,
	outputFiles map[string]string,
) string {
	t.Helper()

	packageAgentBin := filepath.Join(root, "fake-package-agent.sh")
	fileWriters := ""
	for relativePath, body := range outputFiles {
		fileWriters += fmt.Sprintf(`
mkdir -p "$(dirname "$OUTPUT/%s")"
cat > "$OUTPUT/%s" <<'EOF'
%s
EOF
`, relativePath, relativePath, body)
	}
	script := fmt.Sprintf(`#!/bin/sh
set -eu

INPUT=""
OUTPUT=""

while [ "$#" -gt 0 ]; do
	case "$1" in
		build)
			shift
			;;
		--input)
			INPUT="$2"
			shift 2
			;;
		--output)
			OUTPUT="$2"
			shift 2
			;;
		*)
			echo "unexpected arg: $1" >&2
			exit 1
			;;
	esac
done

mkdir -p "$OUTPUT"
printf 'input=%%s\noutput=%%s\n' "$INPUT" "$OUTPUT" > "$OUTPUT/invocation.txt"
cat > "$OUTPUT/report.json" <<'EOF'
%s
EOF
%s
exit %d
`, reportJSON, fileWriters, exitCode)
	if err := os.WriteFile(packageAgentBin, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	return packageAgentBin
}
