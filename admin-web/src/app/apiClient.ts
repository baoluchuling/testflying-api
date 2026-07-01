export type NavItem = {
  key: string;
  label: string;
  path: string;
};

export type BootstrapResponse = {
  appName: string;
  navItems: NavItem[];
  health: {
    state: 'idle' | 'ok' | 'error';
    label: string;
  };
};

export type ReviewAppItem = {
  accountId: string;
  appId: string;
  appName: string;
  bundleIdentifier: string;
  platform: string;
  accountName: string;
  iconColor: string;
  reviewCount: number;
  selected: boolean;
};

export type ReviewStats = {
  total: number;
  low: number;
  ios: number;
  android: number;
};

export type ReviewItem = {
  id: string;
  storeReviewId: string;
  rating: number | null;
  title: string;
  body: string;
  authorName: string;
  locale: string;
  territory: string;
  appVersion: string;
  createdAt: string;
};

export type ReviewFetchRun = {
  id: string;
  status: string;
  pageCount: number;
  fetchedCount: number;
  insertedCount: number;
  duplicateCount: number;
  stoppedReason: string;
  finishedAt: string | null;
  errorSummary: string;
};

export type ReviewAnalysisRun = {
  id: string;
  status: string;
  reviewCount: number;
  lowRatingCount: number;
  issueCount: number;
  summary: string;
  finishedAt: string | null;
  errorSummary: string;
};

export type ReviewAnalysisIssue = {
  title: string;
  severity: string;
  count: number | null;
  focus: string;
  representativeReviewIds: string[];
};

export type StoreReviewsState = {
  apps: ReviewAppItem[];
  selectedAccountId: string | null;
  selectedAppId: string | null;
  rating: number | null;
  stats: ReviewStats;
  reviews: ReviewItem[];
  latestFetch: ReviewFetchRun | null;
  latestAnalysis: ReviewAnalysisRun | null;
  analysisIssues: ReviewAnalysisIssue[];
  analysisBoundaries: string[];
};

export type StoreReviewActionResponse = {
  message: string;
  result: ReviewFetchRun | ReviewAnalysisRun | null;
  state: StoreReviewsState;
  error?: {
    code: string;
    message: string;
  } | null;
};

export type StoreAppBuild = {
  version: string;
  buildNumber: string;
  environment: string;
  uploadedAt: string;
};

export type StoreAppItem = {
  id: string;
  name: string;
  bundleIdentifier: string;
  platform: string;
  developerAccountId: string | null;
  developerAccountName: string;
  iconColor: string;
  iconText: string;
  storeIdentifier: string;
  status: string;
  statusLabel: string;
  latestBuild: StoreAppBuild | null;
  selected: boolean;
  storeManagementPath: string;
  reviewsPath: string;
};

export type StoreAppsStats = {
  total: number;
  ios: number;
  android: number;
  ready: number;
  needs: number;
};

export type StoreAppsAccountSummary = {
  totalAccounts: number;
  boundApps: number;
  connectorOk: number;
  connectorNeeds: number;
  renewalReminders: number;
};

export type StoreAppsState = {
  apps: StoreAppItem[];
  selectedApp: StoreAppItem | null;
  filter: string;
  stats: StoreAppsStats;
  accountSummary: StoreAppsAccountSummary;
};

export class AdminApiError extends Error {
  code: string;
  detail: unknown;

  constructor(message: string, code = 'admin_api_error', detail: unknown = null) {
    super(message);
    this.name = 'AdminApiError';
    this.code = code;
    this.detail = detail;
  }
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    cache: 'no-store'
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    throw new AdminApiError(
      error?.message || `请求失败：HTTP ${response.status}`,
      error?.code || 'http_error',
      error?.detail || null
    );
  }
  return payload as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    throw new AdminApiError(
      error?.message || `请求失败：HTTP ${response.status}`,
      error?.code || 'http_error',
      error?.detail || null
    );
  }
  return payload as T;
}

export function bootstrapAdmin(): Promise<BootstrapResponse> {
  return getJson<BootstrapResponse>('/admin/api/bootstrap');
}

export function loadStoreApps(pathAndQuery: string): Promise<StoreAppsState> {
  return getJson<StoreAppsState>(`/admin/api/store-apps${pathAndQuery}`);
}

export function loadStoreReviews(pathAndQuery: string): Promise<StoreReviewsState> {
  return getJson<StoreReviewsState>(`/admin/api/store-reviews${pathAndQuery}`);
}

export function fetchStoreReviews(accountId: string, appId: string) {
  return postJson<StoreReviewActionResponse>('/admin/api/store-reviews/fetch', {
    accountId,
    appId
  });
}

export function analyzeStoreReviews(accountId: string, appId: string) {
  return postJson<StoreReviewActionResponse>('/admin/api/store-reviews/analyze', {
    accountId,
    appId
  });
}
