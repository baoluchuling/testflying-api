package runner

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
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

func TestRunOnceAssignedBuildRunsPackageAgentAndPostsBuildingEvents(t *testing.T) {
	root := t.TempDir()
	packageAgentBin := filepath.Join(root, "fake-package-agent.sh")
	if err := os.WriteFile(packageAgentBin, []byte(`#!/bin/sh
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
printf 'input=%s\noutput=%s\n' "$INPUT" "$OUTPUT" > "$OUTPUT/invocation.txt"
cat > "$OUTPUT/report.json" <<'EOF'
{
  "status": "ok",
  "classification": "success",
  "summary": "fake package-agent completed",
  "packagePaths": ["app.ipa"],
  "symbolsPaths": ["app.dSYM.zip"],
  "logPaths": ["runner.log"],
  "maxAttempts": 5
}
EOF
`), 0o755); err != nil {
		t.Fatal(err)
	}

	type capturedEvent struct {
		Type            string                 `json:"type"`
		LifecycleStatus string                 `json:"lifecycleStatus"`
		Payload         map[string]interface{} `json:"payload"`
	}

	var heartbeatBody heartbeatRequest
	var pollBody pollRequest
	events := make([]capturedEvent, 0, 2)

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
}
