package connector

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type StoreGateway interface {
	Preflight(ctx context.Context, payload PreflightRequest) (PreflightResponse, error)
	SupportedLocales(ctx context.Context, appID string, accountID string, platform string, version string, storeAppID string, packageName string) (SupportedLocalesResponse, error)
	ListProductPageOptimizations(ctx context.Context, appID string, accountID string, platform string, storeAppID string) (ProductPageOptimizationsResponse, error)
	CreateProductPageOptimization(ctx context.Context, appID string, payload ProductPageOptimizationCreateRequest) (ProductPageOptimizationCreateResponse, error)
	SyncRun(ctx context.Context, payload SyncRunRequest) (SyncRunResponse, error)
}

type MockStoreGateway struct{}

func (g MockStoreGateway) Preflight(_ context.Context, payload PreflightRequest) (PreflightResponse, error) {
	operationLabel := operationLabel(payload.Operation)
	if payload.Operation == "update_marketing_page" {
		return PreflightResponse{
			CanSync:    true,
			ReasonCode: nil,
			Message:    "营销页面可同步；同步前会按勾选项提交文案或商店图。",
			StoreState: map[string]any{
				"versionExists": true,
				"editable":      true,
				"currentStatus": "marketing_page_editable",
			},
		}, nil
	}
	if strings.TrimSpace(payload.Version) == "" || strings.Contains(strings.ToLower(payload.Version), "missing") {
		return PreflightResponse{
			CanSync:    false,
			ReasonCode: stringPtr("store_version_missing"),
			Message:    fmt.Sprintf("商店中还没有创建 %s 版本，暂不能同步%s。", defaultString(payload.Version, "目标"), operationLabel),
			StoreState: map[string]any{
				"versionExists": false,
				"editable":      false,
				"currentStatus": "missing",
			},
		}, nil
	}
	return PreflightResponse{
		CanSync:    true,
		ReasonCode: nil,
		Message:    fmt.Sprintf("商店中已存在 %s 版本，当前状态允许修改%s。", payload.Version, operationLabel),
		StoreState: map[string]any{
			"versionExists": true,
			"editable":      true,
			"currentStatus": "prepare_for_submission",
		},
	}, nil
}

func (g MockStoreGateway) SupportedLocales(_ context.Context, _ string, _ string, platform string, _ string, _ string, _ string) (SupportedLocalesResponse, error) {
	if normalizePlatform(platform) == "ios" {
		return SupportedLocalesResponse{Locales: []string{"zh-Hans", "en-US", "ja", "ko"}}, nil
	}
	return SupportedLocalesResponse{Locales: []string{"zh-Hans", "en-US"}}, nil
}

func (g MockStoreGateway) ListProductPageOptimizations(_ context.Context, appID string, _ string, platform string, _ string) (ProductPageOptimizationsResponse, error) {
	if normalizePlatform(platform) != "ios" {
		return ProductPageOptimizationsResponse{Experiments: []ProductPageOptimization{}}, nil
	}
	return ProductPageOptimizationsResponse{
		Experiments: []ProductPageOptimization{
			{
				ID:                "ppo-" + defaultString(appID, "mock"),
				Name:              "Mock Product Page Optimization",
				Platform:          "IOS",
				State:             "PREPARE_FOR_SUBMISSION",
				TrafficProportion: 50,
				ReviewRequired:    false,
				Treatments: []ProductPageOptimizationTreatment{
					{
						ID:      "treatment-mock-a",
						Name:    "Variant A",
						Locales: []string{"en-US", "zh-Hant"},
					},
				},
			},
		},
	}, nil
}

func (g MockStoreGateway) CreateProductPageOptimization(_ context.Context, appID string, payload ProductPageOptimizationCreateRequest) (ProductPageOptimizationCreateResponse, error) {
	if normalizePlatform(payload.Platform) != "ios" {
		return ProductPageOptimizationCreateResponse{}, errors.New("产品页面优化当前仅支持 App Store Connect")
	}
	if strings.TrimSpace(payload.Name) == "" {
		return ProductPageOptimizationCreateResponse{}, errors.New("产品页面优化名称不能为空")
	}
	treatments := payload.Treatments
	if len(treatments) == 0 {
		treatments = []ProductPageOptimizationTreatment{{Name: "Variant A"}}
	}
	resultTreatments := make([]ProductPageOptimizationTreatment, 0, len(treatments))
	for index, treatment := range treatments {
		locales := treatment.Locales
		if len(locales) == 0 {
			locales = payload.Locales
		}
		resultTreatments = append(resultTreatments, ProductPageOptimizationTreatment{
			ID:          fmt.Sprintf("treatment-%s-%d", defaultString(appID, "mock"), index+1),
			Name:        defaultString(treatment.Name, fmt.Sprintf("Variant %d", index+1)),
			AppIconName: treatment.AppIconName,
			Locales:     locales,
		})
	}
	return ProductPageOptimizationCreateResponse{
		Experiment: ProductPageOptimization{
			ID:                "ppo-created-" + defaultString(appID, "mock"),
			Name:              payload.Name,
			Platform:          "IOS",
			State:             "PREPARE_FOR_SUBMISSION",
			TrafficProportion: payload.TrafficProportion,
			ReviewRequired:    true,
			Treatments:        resultTreatments,
		},
	}, nil
}

func (g MockStoreGateway) SyncRun(_ context.Context, payload SyncRunRequest) (SyncRunResponse, error) {
	if payload.Operation == "update_marketing_page" {
		if payload.MarketingPage == nil {
			return failedSync("empty_marketing_page", "营销页面内容不能为空。"), nil
		}
		if strings.TrimSpace(payload.MarketingPage.PageName) == "" {
			return failedSync("empty_marketing_page_name", "营销页面名称不能为空。"), nil
		}
		return SyncRunResponse{Status: "succeeded", Message: "营销页面已同步。"}, nil
	}
	if payload.Operation == "update_app_metadata" {
		if payload.Metadata == nil {
			return failedSync("empty_metadata", "商店元数据不能为空。"), nil
		}
		if strings.TrimSpace(payload.Metadata.Description) == "" {
			return failedSync("empty_metadata_description", "商店元数据描述不能为空。"), nil
		}
		return SyncRunResponse{Status: "succeeded", Message: "商店元数据已同步。"}, nil
	}
	if strings.TrimSpace(payload.ReleaseNotes) == "" {
		return failedSync("empty_release_notes", "版本说明不能为空。"), nil
	}
	return SyncRunResponse{Status: "succeeded", Message: "版本说明已同步。"}, nil
}

type LiveStoreGateway struct {
	settings   Settings
	credential *CredentialManager
	httpClient *http.Client
	ratePolicy *StoreRateLimitPolicy
}

func NewLiveStoreGateway(settings Settings, credential *CredentialManager, ratePolicy *StoreRateLimitPolicy) *LiveStoreGateway {
	return &LiveStoreGateway{
		settings:   settings,
		credential: credential,
		httpClient: &http.Client{Timeout: 20 * time.Second},
		ratePolicy: ratePolicy,
	}
}

func (g *LiveStoreGateway) Preflight(ctx context.Context, payload PreflightRequest) (PreflightResponse, error) {
	switch normalizePlatform(payload.Platform) {
	case "ios":
		return g.applePreflight(ctx, payload)
	case "android":
		return g.googlePreflight(ctx, payload)
	default:
		return PreflightResponse{
			CanSync:    false,
			ReasonCode: stringPtr("unsupported_platform"),
			Message:    "当前平台暂不支持商店同步。",
			StoreState: map[string]any{"platform": payload.Platform},
		}, nil
	}
}

func (g *LiveStoreGateway) SupportedLocales(ctx context.Context, appID string, accountID string, platform string, version string, storeAppID string, packageName string) (SupportedLocalesResponse, error) {
	switch normalizePlatform(platform) {
	case "ios":
		return g.appleSupportedLocales(ctx, storeAppID, version)
	case "android":
		return g.googleSupportedLocales(ctx, packageName)
	default:
		return SupportedLocalesResponse{Locales: []string{}}, nil
	}
}

func (g *LiveStoreGateway) ListProductPageOptimizations(ctx context.Context, appID string, accountID string, platform string, storeAppID string) (ProductPageOptimizationsResponse, error) {
	switch normalizePlatform(platform) {
	case "ios":
		return g.appleProductPageOptimizations(ctx, storeAppID)
	default:
		return ProductPageOptimizationsResponse{}, errors.New("产品页面优化当前仅支持 App Store Connect")
	}
}

func (g *LiveStoreGateway) CreateProductPageOptimization(ctx context.Context, appID string, payload ProductPageOptimizationCreateRequest) (ProductPageOptimizationCreateResponse, error) {
	switch normalizePlatform(payload.Platform) {
	case "ios":
		return g.appleCreateProductPageOptimization(ctx, payload)
	default:
		return ProductPageOptimizationCreateResponse{}, errors.New("产品页面优化当前仅支持 App Store Connect")
	}
}

func (g *LiveStoreGateway) SyncRun(ctx context.Context, payload SyncRunRequest) (SyncRunResponse, error) {
	switch normalizePlatform(payload.Platform) {
	case "ios":
		return g.appleSyncRun(ctx, payload)
	case "android":
		return g.googleSyncRun(ctx, payload)
	default:
		return failedSync("unsupported_platform", "当前平台暂不支持商店同步。"), nil
	}
}

type appleVersion struct {
	ID         string
	State      string
	Attributes map[string]any
}

type appleLocalization struct {
	ID         string
	Locale     string
	Attributes map[string]any
}

type appleResource struct {
	ID         string `json:"id"`
	Type       string `json:"type"`
	Attributes struct {
		Name              string `json:"name"`
		Platform          string `json:"platform"`
		State             string `json:"state"`
		TrafficProportion int    `json:"trafficProportion"`
		ReviewRequired    bool   `json:"reviewRequired"`
		StartDate         string `json:"startDate"`
		EndDate           string `json:"endDate"`
		AppIconName       string `json:"appIconName"`
		Locale            string `json:"locale"`
	} `json:"attributes"`
	Relationships map[string]struct {
		Data []struct {
			ID   string `json:"id"`
			Type string `json:"type"`
		} `json:"data"`
	} `json:"relationships"`
}

func (g *LiveStoreGateway) applePreflight(ctx context.Context, payload PreflightRequest) (PreflightResponse, error) {
	if strings.TrimSpace(payload.App.StoreAppID) == "" {
		return PreflightResponse{
			CanSync:    false,
			ReasonCode: stringPtr("store_app_id_missing"),
			Message:    "iOS App 缺少 Apple App ID，暂不能同步。",
			StoreState: map[string]any{"versionExists": false, "editable": false},
		}, nil
	}
	if payload.Operation == "update_marketing_page" {
		return PreflightResponse{
			CanSync:    true,
			ReasonCode: nil,
			Message:    "App Store Connect App 已配置，营销页面可提交。",
			StoreState: map[string]any{
				"versionExists": true,
				"editable":      true,
				"currentStatus": "marketing_page_editable",
			},
		}, nil
	}
	version, err := g.appleFindVersion(ctx, payload.App.StoreAppID, payload.Version)
	if err != nil {
		return PreflightResponse{}, err
	}
	if version == nil {
		return PreflightResponse{
			CanSync:    false,
			ReasonCode: stringPtr("store_version_missing"),
			Message:    fmt.Sprintf("商店中还没有创建 %s 版本，暂不能同步%s。", defaultString(payload.Version, "目标"), operationLabel(payload.Operation)),
			StoreState: map[string]any{
				"versionExists": false,
				"editable":      false,
				"currentStatus": "missing",
			},
		}, nil
	}
	return PreflightResponse{
		CanSync:    true,
		ReasonCode: nil,
		Message:    fmt.Sprintf("商店中已存在 %s 版本，当前状态允许修改%s。", payload.Version, operationLabel(payload.Operation)),
		StoreState: map[string]any{
			"versionExists": true,
			"editable":      true,
			"currentStatus": strings.ToLower(version.State),
		},
	}, nil
}

func (g *LiveStoreGateway) appleSupportedLocales(ctx context.Context, storeAppID string, version string) (SupportedLocalesResponse, error) {
	if strings.TrimSpace(storeAppID) == "" {
		return SupportedLocalesResponse{Locales: []string{}}, nil
	}
	versionInfo, err := g.appleFindVersion(ctx, storeAppID, version)
	if err != nil {
		return SupportedLocalesResponse{}, err
	}
	if versionInfo != nil {
		locales, err := g.appleVersionLocalizations(ctx, versionInfo.ID)
		if err != nil {
			return SupportedLocalesResponse{}, err
		}
		return SupportedLocalesResponse{Locales: localizationLocales(locales)}, nil
	}
	locales, err := g.appleInfoLocalizations(ctx, storeAppID)
	if err != nil {
		return SupportedLocalesResponse{}, err
	}
	return SupportedLocalesResponse{Locales: localizationLocales(locales)}, nil
}

func (g *LiveStoreGateway) appleProductPageOptimizations(ctx context.Context, storeAppID string) (ProductPageOptimizationsResponse, error) {
	if strings.TrimSpace(storeAppID) == "" {
		return ProductPageOptimizationsResponse{}, errors.New("iOS App 缺少 Apple App ID")
	}
	query := url.Values{}
	query.Set("include", "appStoreVersionExperimentTreatments")
	query.Set("limit", "200")
	query.Set("limit[appStoreVersionExperimentTreatments]", "50")
	var response struct {
		Data     []appleResource `json:"data"`
		Included []appleResource `json:"included"`
	}
	if _, err := g.appleRequest(ctx, http.MethodGet, "/v1/apps/"+url.PathEscape(storeAppID)+"/appStoreVersionExperimentsV2?"+query.Encode(), nil, &response); err != nil {
		return ProductPageOptimizationsResponse{}, err
	}
	treatmentsByID := map[string]ProductPageOptimizationTreatment{}
	for _, included := range response.Included {
		if included.Type != "appStoreVersionExperimentTreatments" {
			continue
		}
		treatmentsByID[included.ID] = ProductPageOptimizationTreatment{
			ID:          included.ID,
			Name:        included.Attributes.Name,
			AppIconName: included.Attributes.AppIconName,
		}
	}
	experiments := make([]ProductPageOptimization, 0, len(response.Data))
	for _, item := range response.Data {
		experiment := appleProductPageOptimizationFromResource(item)
		if relationship, ok := item.Relationships["appStoreVersionExperimentTreatments"]; ok {
			for _, linkage := range relationship.Data {
				if treatment, exists := treatmentsByID[linkage.ID]; exists {
					experiment.Treatments = append(experiment.Treatments, treatment)
				}
			}
		}
		experiments = append(experiments, experiment)
	}
	return ProductPageOptimizationsResponse{Experiments: experiments}, nil
}

func (g *LiveStoreGateway) appleCreateProductPageOptimization(ctx context.Context, payload ProductPageOptimizationCreateRequest) (ProductPageOptimizationCreateResponse, error) {
	storeAppID := strings.TrimSpace(payload.App.StoreAppID)
	if storeAppID == "" {
		return ProductPageOptimizationCreateResponse{}, errors.New("iOS App 缺少 Apple App ID")
	}
	name := strings.TrimSpace(payload.Name)
	if name == "" {
		return ProductPageOptimizationCreateResponse{}, errors.New("产品页面优化名称不能为空")
	}
	trafficProportion := payload.TrafficProportion
	if trafficProportion <= 0 || trafficProportion > 100 {
		return ProductPageOptimizationCreateResponse{}, errors.New("trafficProportion 必须在 1 到 100 之间")
	}
	createBody := map[string]any{
		"data": map[string]any{
			"type": "appStoreVersionExperiments",
			"attributes": map[string]any{
				"name":              name,
				"platform":          "IOS",
				"trafficProportion": trafficProportion,
			},
			"relationships": map[string]any{
				"app": map[string]any{
					"data": map[string]string{
						"type": "apps",
						"id":   storeAppID,
					},
				},
			},
		},
	}
	var createResponse struct {
		Data appleResource `json:"data"`
	}
	if _, err := g.appleRequest(ctx, http.MethodPost, "/v2/appStoreVersionExperiments", createBody, &createResponse); err != nil {
		return ProductPageOptimizationCreateResponse{}, err
	}
	experiment := appleProductPageOptimizationFromResource(createResponse.Data)
	if experiment.ID == "" {
		return ProductPageOptimizationCreateResponse{}, errors.New("App Store Connect 没有返回产品页面优化 ID")
	}
	treatments, err := g.appleCreateExperimentTreatments(ctx, experiment.ID, payload)
	if err != nil {
		return ProductPageOptimizationCreateResponse{}, err
	}
	experiment.Treatments = treatments
	return ProductPageOptimizationCreateResponse{Experiment: experiment}, nil
}

func (g *LiveStoreGateway) appleCreateExperimentTreatments(ctx context.Context, experimentID string, payload ProductPageOptimizationCreateRequest) ([]ProductPageOptimizationTreatment, error) {
	if len(payload.Treatments) == 0 {
		return []ProductPageOptimizationTreatment{}, nil
	}
	created := make([]ProductPageOptimizationTreatment, 0, len(payload.Treatments))
	for _, treatment := range payload.Treatments {
		name := strings.TrimSpace(treatment.Name)
		if name == "" {
			return nil, errors.New("treatment 名称不能为空")
		}
		attributes := map[string]any{"name": name}
		if strings.TrimSpace(treatment.AppIconName) != "" {
			attributes["appIconName"] = strings.TrimSpace(treatment.AppIconName)
		}
		body := map[string]any{
			"data": map[string]any{
				"type":       "appStoreVersionExperimentTreatments",
				"attributes": attributes,
				"relationships": map[string]any{
					"appStoreVersionExperimentV2": map[string]any{
						"data": map[string]string{
							"type": "appStoreVersionExperiments",
							"id":   experimentID,
						},
					},
				},
			},
		}
		var response struct {
			Data appleResource `json:"data"`
		}
		if _, err := g.appleRequest(ctx, http.MethodPost, "/v1/appStoreVersionExperimentTreatments", body, &response); err != nil {
			return nil, err
		}
		createdTreatment := ProductPageOptimizationTreatment{
			ID:          response.Data.ID,
			Name:        response.Data.Attributes.Name,
			AppIconName: response.Data.Attributes.AppIconName,
		}
		locales := treatment.Locales
		if len(locales) == 0 {
			locales = payload.Locales
		}
		for _, locale := range locales {
			normalizedLocale := strings.TrimSpace(locale)
			if normalizedLocale == "" {
				continue
			}
			if err := g.appleCreateExperimentTreatmentLocalization(ctx, createdTreatment.ID, normalizedLocale); err != nil {
				return nil, err
			}
			createdTreatment.Locales = append(createdTreatment.Locales, normalizedLocale)
		}
		created = append(created, createdTreatment)
	}
	return created, nil
}

func (g *LiveStoreGateway) appleCreateExperimentTreatmentLocalization(ctx context.Context, treatmentID string, locale string) error {
	body := map[string]any{
		"data": map[string]any{
			"type": "appStoreVersionExperimentTreatmentLocalizations",
			"attributes": map[string]any{
				"locale": locale,
			},
			"relationships": map[string]any{
				"appStoreVersionExperimentTreatment": map[string]any{
					"data": map[string]string{
						"type": "appStoreVersionExperimentTreatments",
						"id":   treatmentID,
					},
				},
			},
		},
	}
	_, err := g.appleRequest(ctx, http.MethodPost, "/v1/appStoreVersionExperimentTreatmentLocalizations", body, nil)
	return err
}

func (g *LiveStoreGateway) appleSyncRun(ctx context.Context, payload SyncRunRequest) (SyncRunResponse, error) {
	if payload.Operation == "update_marketing_page" {
		if payload.MarketingPage == nil {
			return failedSync("empty_marketing_page", "营销页面内容不能为空。"), nil
		}
		if strings.TrimSpace(payload.MarketingPage.PageName) == "" {
			return failedSync("empty_marketing_page_name", "营销页面名称不能为空。"), nil
		}
		return SyncRunResponse{Status: "succeeded", Message: "营销页面已同步。"}, nil
	}
	version, err := g.appleFindVersion(ctx, payload.App.StoreAppID, payload.Version)
	if err != nil {
		return SyncRunResponse{}, err
	}
	if version == nil {
		return failedSync("store_version_missing", "商店中还没有创建目标版本。"), nil
	}
	versionLocalizations, err := g.appleVersionLocalizations(ctx, version.ID)
	if err != nil {
		return SyncRunResponse{}, err
	}
	versionLocalization := findLocalization(versionLocalizations, payload.Locale)
	if versionLocalization == nil {
		return failedSync("store_locale_missing", "商店中还没有创建目标语言。"), nil
	}
	if payload.Operation == "update_app_metadata" {
		if payload.Metadata == nil {
			return failedSync("empty_metadata", "商店元数据不能为空。"), nil
		}
		if err := g.applePatchVersionLocalization(ctx, versionLocalization.ID, map[string]string{
			"description":     payload.Metadata.Description,
			"keywords":        payload.Metadata.Keywords,
			"promotionalText": payload.Metadata.PromotionalText,
		}); err != nil {
			return SyncRunResponse{}, err
		}
		return SyncRunResponse{Status: "succeeded", Message: "商店元数据已同步。"}, nil
	}
	if strings.TrimSpace(payload.ReleaseNotes) == "" {
		return failedSync("empty_release_notes", "版本说明不能为空。"), nil
	}
	if err := g.applePatchVersionLocalization(ctx, versionLocalization.ID, map[string]string{
		"whatsNew": payload.ReleaseNotes,
	}); err != nil {
		return SyncRunResponse{}, err
	}
	return SyncRunResponse{Status: "succeeded", Message: "版本说明已同步。"}, nil
}

func (g *LiveStoreGateway) appleFindVersion(ctx context.Context, storeAppID string, version string) (*appleVersion, error) {
	if strings.TrimSpace(version) == "" {
		return nil, nil
	}
	query := url.Values{}
	query.Set("filter[versionString]", version)
	query.Set("limit", "10")
	var response struct {
		Data []struct {
			ID         string         `json:"id"`
			Attributes map[string]any `json:"attributes"`
		} `json:"data"`
	}
	if _, err := g.appleRequest(ctx, http.MethodGet, "/v1/apps/"+url.PathEscape(storeAppID)+"/appStoreVersions?"+query.Encode(), nil, &response); err != nil {
		return nil, err
	}
	for _, item := range response.Data {
		state, _ := item.Attributes["appStoreState"].(string)
		return &appleVersion{ID: item.ID, State: state, Attributes: item.Attributes}, nil
	}
	return nil, nil
}

func (g *LiveStoreGateway) appleVersionLocalizations(ctx context.Context, versionID string) ([]appleLocalization, error) {
	var response struct {
		Data []struct {
			ID         string         `json:"id"`
			Attributes map[string]any `json:"attributes"`
		} `json:"data"`
	}
	if _, err := g.appleRequest(ctx, http.MethodGet, "/v1/appStoreVersions/"+url.PathEscape(versionID)+"/appStoreVersionLocalizations?limit=200", nil, &response); err != nil {
		return nil, err
	}
	return appleLocalizationsFromResponse(response.Data), nil
}

func (g *LiveStoreGateway) appleInfoLocalizations(ctx context.Context, storeAppID string) ([]appleLocalization, error) {
	var infos struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if _, err := g.appleRequest(ctx, http.MethodGet, "/v1/apps/"+url.PathEscape(storeAppID)+"/appInfos?limit=1", nil, &infos); err != nil {
		return nil, err
	}
	if len(infos.Data) == 0 {
		return nil, nil
	}
	var response struct {
		Data []struct {
			ID         string         `json:"id"`
			Attributes map[string]any `json:"attributes"`
		} `json:"data"`
	}
	if _, err := g.appleRequest(ctx, http.MethodGet, "/v1/appInfos/"+url.PathEscape(infos.Data[0].ID)+"/appInfoLocalizations?limit=200", nil, &response); err != nil {
		return nil, err
	}
	return appleLocalizationsFromResponse(response.Data), nil
}

func (g *LiveStoreGateway) appleFindInfoLocalization(ctx context.Context, storeAppID string, locale string) (*appleLocalization, error) {
	localizations, err := g.appleInfoLocalizations(ctx, storeAppID)
	if err != nil {
		return nil, err
	}
	return findLocalization(localizations, locale), nil
}

func (g *LiveStoreGateway) applePatchVersionLocalization(ctx context.Context, localizationID string, attributes map[string]string) error {
	return g.applePatchLocalization(ctx, "appStoreVersionLocalizations", localizationID, attributes)
}

func (g *LiveStoreGateway) applePatchInfoLocalization(ctx context.Context, localizationID string, attributes map[string]string) error {
	return g.applePatchLocalization(ctx, "appInfoLocalizations", localizationID, attributes)
}

func (g *LiveStoreGateway) applePatchLocalization(ctx context.Context, resourceType string, localizationID string, attributes map[string]string) error {
	cleaned := map[string]string{}
	for key, value := range attributes {
		if strings.TrimSpace(value) != "" {
			cleaned[key] = value
		}
	}
	body := map[string]any{
		"data": map[string]any{
			"type":       resourceType,
			"id":         localizationID,
			"attributes": cleaned,
		},
	}
	_, err := g.appleRequest(ctx, http.MethodPatch, "/v1/"+resourceType+"/"+url.PathEscape(localizationID), body, nil)
	return err
}

func (g *LiveStoreGateway) appleRequest(ctx context.Context, method string, path string, body any, out any) (http.Header, error) {
	token, err := g.credential.AppleJWT(time.Now())
	if err != nil {
		return nil, err
	}
	return doJSON(ctx, g.httpClient, method, g.settings.AppleAPIBaseURL+path, "Bearer "+token, body, out, func(headers http.Header) {
		g.ratePolicy.RecordAppleRateLimitHeader(headers.Get("X-Rate-Limit"))
	})
}

func (g *LiveStoreGateway) googlePreflight(ctx context.Context, payload PreflightRequest) (PreflightResponse, error) {
	packageName := defaultString(payload.App.PackageName, payload.App.BundleIdentifier)
	if strings.TrimSpace(packageName) == "" {
		return PreflightResponse{
			CanSync:    false,
			ReasonCode: stringPtr("package_name_missing"),
			Message:    "Android App 缺少 package，暂不能同步。",
			StoreState: map[string]any{"editable": false},
		}, nil
	}
	editID, err := g.googleInsertEdit(ctx, packageName)
	if err != nil {
		return PreflightResponse{}, err
	}
	return PreflightResponse{
		CanSync:    true,
		ReasonCode: nil,
		Message:    fmt.Sprintf("Google Play 已允许创建编辑会话 %s，当前状态允许修改%s。", editID, operationLabel(payload.Operation)),
		StoreState: map[string]any{
			"versionExists": true,
			"editable":      true,
			"currentStatus": "editable",
			"editId":        editID,
		},
	}, nil
}

func (g *LiveStoreGateway) googleSupportedLocales(ctx context.Context, packageName string) (SupportedLocalesResponse, error) {
	if strings.TrimSpace(packageName) == "" {
		return SupportedLocalesResponse{Locales: []string{}}, nil
	}
	editID, err := g.googleInsertEdit(ctx, packageName)
	if err != nil {
		return SupportedLocalesResponse{}, err
	}
	var response struct {
		Listings []struct {
			Language string `json:"language"`
		} `json:"listings"`
	}
	if err := g.googleRequest(ctx, http.MethodGet, "/androidpublisher/v3/applications/"+url.PathEscape(packageName)+"/edits/"+url.PathEscape(editID)+"/listings", nil, &response); err != nil {
		return SupportedLocalesResponse{}, err
	}
	locales := make([]string, 0, len(response.Listings))
	for _, listing := range response.Listings {
		if strings.TrimSpace(listing.Language) != "" {
			locales = append(locales, listing.Language)
		}
	}
	return SupportedLocalesResponse{Locales: locales}, nil
}

func (g *LiveStoreGateway) googleSyncRun(ctx context.Context, payload SyncRunRequest) (SyncRunResponse, error) {
	if payload.Operation == "update_marketing_page" {
		return failedSync("google_marketing_page_unsupported", "营销页面控制台当前仅支持 App Store Connect。"), nil
	}
	if payload.Operation != "update_app_metadata" {
		return failedSync("google_release_notes_unsupported", "Google Play 版本说明同步需要 track 和 versionCode，当前后台还没有提供这些参数。"), nil
	}
	if payload.Metadata == nil {
		return failedSync("empty_metadata", "商店元数据不能为空。"), nil
	}
	packageName := defaultString(payload.App.PackageName, payload.App.BundleIdentifier)
	editID, err := g.googleInsertEdit(ctx, packageName)
	if err != nil {
		return SyncRunResponse{}, err
	}
	body := map[string]string{"fullDescription": payload.Metadata.Description}
	path := "/androidpublisher/v3/applications/" + url.PathEscape(packageName) +
		"/edits/" + url.PathEscape(editID) + "/listings/" + url.PathEscape(payload.Locale)
	if err := g.googleRequest(ctx, http.MethodPatch, path, body, nil); err != nil {
		return SyncRunResponse{}, err
	}
	if err := g.googleRequest(ctx, http.MethodPost, "/androidpublisher/v3/applications/"+url.PathEscape(packageName)+"/edits/"+url.PathEscape(editID)+":commit", nil, nil); err != nil {
		return SyncRunResponse{}, err
	}
	return SyncRunResponse{Status: "succeeded", Message: "商店元数据已同步。"}, nil
}

func (g *LiveStoreGateway) googleInsertEdit(ctx context.Context, packageName string) (string, error) {
	if strings.TrimSpace(packageName) == "" {
		return "", errors.New("Android package 不能为空")
	}
	var response struct {
		ID string `json:"id"`
	}
	if err := g.googleRequest(ctx, http.MethodPost, "/androidpublisher/v3/applications/"+url.PathEscape(packageName)+"/edits", map[string]any{}, &response); err != nil {
		return "", err
	}
	if response.ID == "" {
		return "", errors.New("Google Play 没有返回 edit id")
	}
	return response.ID, nil
}

func (g *LiveStoreGateway) googleRequest(ctx context.Context, method string, path string, body any, out any) error {
	token, err := g.credential.GoogleAccessToken(ctx, g.httpClient, time.Now())
	if err != nil {
		return err
	}
	_, err = doJSON(ctx, g.httpClient, method, g.settings.GoogleAPIBaseURL+path, "Bearer "+token, body, out, nil)
	return err
}

func doJSON(ctx context.Context, client *http.Client, method string, url string, authorization string, body any, out any, after func(http.Header)) (http.Header, error) {
	var requestBody io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		requestBody = bytes.NewReader(raw)
	}
	request, err := http.NewRequestWithContext(ctx, method, url, requestBody)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if authorization != "" {
		request.Header.Set("Authorization", authorization)
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if after != nil {
		after(response.Header)
	}
	responseBody, _ := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return response.Header, fmt.Errorf("商店接口返回 HTTP %d: %s", response.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	if out != nil && len(responseBody) > 0 {
		if err := json.Unmarshal(responseBody, out); err != nil {
			return response.Header, fmt.Errorf("商店接口响应解析失败: %w", err)
		}
	}
	return response.Header, nil
}

func appleLocalizationsFromResponse(data []struct {
	ID         string         `json:"id"`
	Attributes map[string]any `json:"attributes"`
}) []appleLocalization {
	localizations := make([]appleLocalization, 0, len(data))
	for _, item := range data {
		locale, _ := item.Attributes["locale"].(string)
		localizations = append(localizations, appleLocalization{
			ID:         item.ID,
			Locale:     locale,
			Attributes: item.Attributes,
		})
	}
	return localizations
}

func localizationLocales(localizations []appleLocalization) []string {
	locales := make([]string, 0, len(localizations))
	for _, localization := range localizations {
		if strings.TrimSpace(localization.Locale) != "" {
			locales = append(locales, localization.Locale)
		}
	}
	return locales
}

func findLocalization(localizations []appleLocalization, locale string) *appleLocalization {
	for i := range localizations {
		if strings.EqualFold(localizations[i].Locale, locale) {
			return &localizations[i]
		}
	}
	return nil
}

func appleProductPageOptimizationFromResource(item appleResource) ProductPageOptimization {
	return ProductPageOptimization{
		ID:                item.ID,
		Name:              item.Attributes.Name,
		Platform:          item.Attributes.Platform,
		State:             item.Attributes.State,
		TrafficProportion: item.Attributes.TrafficProportion,
		ReviewRequired:    item.Attributes.ReviewRequired,
		StartDate:         item.Attributes.StartDate,
		EndDate:           item.Attributes.EndDate,
		Treatments:        []ProductPageOptimizationTreatment{},
	}
}

func failedSync(code string, summary string) SyncRunResponse {
	return SyncRunResponse{
		Status:       "failed",
		Message:      summary,
		ErrorCode:    stringPtr(code),
		ErrorSummary: stringPtr(summary),
	}
}

func operationLabel(operation string) string {
	if operation == "update_app_metadata" {
		return "商店元数据"
	}
	if operation == "update_marketing_page" {
		return "营销页面"
	}
	return "版本说明"
}

func defaultString(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
