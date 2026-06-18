package connector

type StoreApp struct {
	AppID            string `json:"appId"`
	BundleIdentifier string `json:"bundleIdentifier"`
	StoreAppID       string `json:"storeAppId,omitempty"`
	PackageName      string `json:"packageName,omitempty"`
}

type PreflightRequest struct {
	DeveloperAccountID string   `json:"developerAccountId"`
	ConnectorID        string   `json:"connectorId,omitempty"`
	Operation          string   `json:"operation"`
	Platform           string   `json:"platform"`
	Version            string   `json:"version"`
	Locale             string   `json:"locale"`
	App                StoreApp `json:"app"`
}

type PreflightResponse struct {
	CanSync    bool           `json:"canSync"`
	ReasonCode *string        `json:"reasonCode"`
	Message    string         `json:"message"`
	StoreState map[string]any `json:"storeState"`
}

type SupportedLocalesResponse struct {
	Locales []string `json:"locales"`
}

type StoreMetadata struct {
	Title            string `json:"title"`
	Subtitle         string `json:"subtitle"`
	Keywords         string `json:"keywords"`
	PromotionalText  string `json:"promotionalText"`
	Description      string `json:"description"`
	PrivacyPolicyURL string `json:"privacyPolicyUrl"`
	SupportURL       string `json:"supportUrl"`
	MarketingURL     string `json:"marketingUrl"`
}

type SyncRunRequest struct {
	PreflightRequest
	RunID        string         `json:"runId"`
	ReleaseNotes string         `json:"releaseNotes"`
	Metadata     *StoreMetadata `json:"metadata"`
}

type SyncRunResponse struct {
	Status       string  `json:"status"`
	Message      string  `json:"message"`
	ErrorCode    *string `json:"errorCode"`
	ErrorSummary *string `json:"errorSummary"`
}

type ConnectorError struct {
	Detail string `json:"detail"`
}

type HealthResponse struct {
	Status             string                      `json:"status"`
	DeveloperAccountID string                      `json:"developerAccountId"`
	Mode               string                      `json:"mode"`
	Credentials        map[string]CredentialStatus `json:"credentials"`
}

type CredentialStatus struct {
	Configured bool   `json:"configured"`
	Valid      bool   `json:"valid"`
	Message    string `json:"message"`
}

func stringPtr(value string) *string {
	return &value
}
