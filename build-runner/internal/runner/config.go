package runner

import (
	"fmt"
	"strings"
)

const BuildRetryLimit = 5

type Config struct {
	RunnerID            string
	Name                string
	Token               string
	ServerURL           string
	RootDir             string
	PackageAgentBin     string
	Version             string
	PackageAgentVersion string
	Labels              []string
	Platforms           []string
	LLMAdapters         []string
	Capacity            int
}

func (c Config) Validate() error {
	required := map[string]string{
		"RunnerID":        c.RunnerID,
		"Name":            c.Name,
		"Token":           c.Token,
		"ServerURL":       c.ServerURL,
		"RootDir":         c.RootDir,
		"PackageAgentBin": c.PackageAgentBin,
	}
	for field, value := range required {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s is required", field)
		}
	}
	if c.Capacity == 0 {
		return fmt.Errorf("Capacity is required")
	}
	if c.Capacity != 1 {
		return fmt.Errorf("Capacity must be 1 in the current implementation")
	}
	return nil
}
