package runner

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
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
	}

	path, err := WriteBuildInput(root, input)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatal(err)
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
