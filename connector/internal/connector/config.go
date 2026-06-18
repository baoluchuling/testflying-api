package connector

import (
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	StoreModeMock = "mock"
	StoreModeLive = "live"
)

type Settings struct {
	DeveloperAccountID string
	ConnectorToken     string
	StoreMode          string
	ListenAddr         string

	AppleIssuerID       string
	AppleKeyID          string
	ApplePrivateKeyPath string
	ApplePrivateKeyPEM  string
	AppleAPIBaseURL     string

	GoogleServiceAccountJSONPath string
	GoogleServiceAccountJSON     string
	GoogleDeveloperID            string
	GoogleTokenURL               string
	GoogleAPIBaseURL             string

	GoogleRateLimitMaxRequests int
	GoogleRateLimitWindow      time.Duration
	AppleRateLimitFallbackMax  int
	AppleRateLimitWindow       time.Duration
	AppleRateLimitSafetyRatio  float64
}

func LoadSettingsFromEnv() Settings {
	return Settings{
		DeveloperAccountID: strings.TrimSpace(env("TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID", "account-apple-enterprise")),
		ConnectorToken:     env("TESTFLYING_CONNECTOR_TOKEN", "dev-connector-token"),
		StoreMode:          normalizeStoreMode(env("TESTFLYING_CONNECTOR_STORE_MODE", StoreModeMock)),
		ListenAddr:         env("TESTFLYING_CONNECTOR_LISTEN_ADDR", ":8100"),

		AppleIssuerID:       strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_APPLE_ISSUER_ID")),
		AppleKeyID:          strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_APPLE_KEY_ID")),
		ApplePrivateKeyPath: strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_APPLE_PRIVATE_KEY_PATH")),
		ApplePrivateKeyPEM:  strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_APPLE_PRIVATE_KEY")),
		AppleAPIBaseURL:     strings.TrimRight(env("TESTFLYING_CONNECTOR_APPLE_API_BASE_URL", "https://api.appstoreconnect.apple.com"), "/"),

		GoogleServiceAccountJSONPath: strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_GOOGLE_SERVICE_ACCOUNT_JSON_PATH")),
		GoogleServiceAccountJSON:     strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_GOOGLE_SERVICE_ACCOUNT_JSON")),
		GoogleDeveloperID:            strings.TrimSpace(os.Getenv("TESTFLYING_CONNECTOR_GOOGLE_DEVELOPER_ID")),
		GoogleTokenURL:               env("TESTFLYING_CONNECTOR_GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token"),
		GoogleAPIBaseURL:             strings.TrimRight(env("TESTFLYING_CONNECTOR_GOOGLE_API_BASE_URL", "https://androidpublisher.googleapis.com"), "/"),

		GoogleRateLimitMaxRequests: intFromEnv("TESTFLYING_CONNECTOR_GOOGLE_RATE_LIMIT_MAX_REQUESTS", 200),
		GoogleRateLimitWindow:      secondsFromEnv("TESTFLYING_CONNECTOR_GOOGLE_RATE_LIMIT_WINDOW_SECONDS", 60),
		AppleRateLimitFallbackMax:  intFromEnv("TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_FALLBACK_MAX_REQUESTS", 2880),
		AppleRateLimitWindow:       secondsFromEnv("TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_WINDOW_SECONDS", 3600),
		AppleRateLimitSafetyRatio:  floatFromEnv("TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_SAFETY_RATIO", 0.8),
	}
}

func (s Settings) Validate() error {
	if strings.TrimSpace(s.DeveloperAccountID) == "" {
		return configError("TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID 不能为空")
	}
	if strings.TrimSpace(s.ConnectorToken) == "" {
		return configError("TESTFLYING_CONNECTOR_TOKEN 不能为空")
	}
	return nil
}

func env(name string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	return value
}

func normalizeStoreMode(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case StoreModeLive:
		return StoreModeLive
	default:
		return StoreModeMock
	}
}

func intFromEnv(name string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 1 {
		return fallback
	}
	return value
}

func secondsFromEnv(name string, fallback int) time.Duration {
	return time.Duration(intFromEnv(name, fallback)) * time.Second
}

func floatFromEnv(name string, fallback float64) float64 {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return fallback
	}
	if value < 0.1 {
		return 0.1
	}
	if value > 1 {
		return 1
	}
	return value
}

type configError string

func (e configError) Error() string {
	return string(e)
}
