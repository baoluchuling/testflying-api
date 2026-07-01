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

export type UploadAccountOption = {
  id: string;
  teamName: string;
  status: string;
  platform: string | null;
};

export type UploadState = {
  accounts: UploadAccountOption[];
};

export type UploadResult = {
  appId: string;
  appName: string;
  bundleIdentifier: string;
  platform: string;
  environment: string;
  version: string;
  buildNumber: string;
  developerAccount: string;
  storeIdentifier: string;
  installUrl: string;
  manifestUrl: string | null;
  downloadUrl: string | null;
};

export type AdminUploadResponse = {
  message: string;
  result: UploadResult;
  state: UploadState;
};

export type AppLogConnectInfo = {
  host: string;
  port: string;
  name: string;
  appScheme: string;
  appName: string;
  connectUrl: string;
  connectPageUrl: string;
  schemeUrl: string;
  websocketUrl: string;
};

export type AppLogDevice = {
  token: string;
  deviceId: string;
  device: string;
  platform: string;
  connected: boolean;
  knownToken: boolean;
  connectedAt: string;
  lastSeenAt: string;
  connectionCount: number;
  errorCount: number;
  logCount: number;
};

export type AppLogField = {
  key: string;
  value: string;
};

export type AppLogEntry = {
  sequence: number;
  token: string;
  deviceId: string;
  device: string;
  platform: string;
  receivedAt: string;
  sentAt: string;
  history: boolean;
  raw: string;
  timestamp: string;
  level: string;
  tag: string;
  event: string;
  message: string;
  fields: AppLogField[];
};

export type AppLogClientError = {
  sequence: number;
  token: string;
  deviceId: string;
  device: string;
  receivedAt: string;
  sentAt: string;
  message: string;
};

export type AppLogsState = {
  connect: AppLogConnectInfo;
  cursor: number;
  devices: AppLogDevice[];
  logs: AppLogEntry[];
  errors: AppLogClientError[];
  levels: string[];
};

export type DashboardStat = {
  label: string;
  value: string;
  tone: string;
};

export type BuildAppSummary = {
  id: string;
  name: string;
  bundleIdentifier: string;
  platform: string;
  iconColor: string;
  iconText: string;
};

export type BuildArtifact = {
  fileName: string;
  sizeLabel: string;
  installUrl: string;
  downloadUrl: string;
  manifestUrl: string | null;
};

export type BuildItem = {
  id: string;
  app: BuildAppSummary;
  version: string;
  buildNumber: string;
  platform: string;
  platformLabel: string;
  environment: string;
  environmentLabel: string;
  status: string;
  note: string;
  minOsVersion: string;
  uploadedAt: string;
  uploadedAtLabel: string;
  expiresAt: string | null;
  expiresAtLabel: string;
  artifact: BuildArtifact | null;
};

export type NotificationItem = {
  id: string;
  type: string;
  section: string;
  iconKey: string;
  title: string;
  subtitle: string;
  tag: string;
  tagColor: string;
  createdAt: string;
  createdAtLabel: string;
};

export type DashboardState = {
  stats: DashboardStat[];
  recentBuilds: BuildItem[];
  recentNotifications: NotificationItem[];
};

export type BuildsState = {
  builds: BuildItem[];
  total: number;
};

export type DeviceItem = {
  id: string;
  name: string;
  owner: string;
  platform: string;
  platformLabel: string;
  status: string;
  statusColor: string;
  detail: string;
  udid: string;
  osVersion: string;
  certificateStatus: string;
  registeredAt: string;
  registeredAtLabel: string;
};

export type DevicesState = {
  devices: DeviceItem[];
  total: number;
};

export type NotificationTypeCount = {
  type: string;
  label: string;
  count: number;
};

export type NotificationsState = {
  notifications: NotificationItem[];
  typeCounts: NotificationTypeCount[];
  activeType: string;
  total: number;
};

export type ApiDocParam = {
  name: string;
  location: string;
  required: string;
  description: string;
};

export type ApiDocEndpoint = {
  anchor: string;
  title: string;
  method: string;
  path: string;
  summary: string;
  params: ApiDocParam[];
  curl: string;
  response: string;
};

export type ApiDocsState = {
  endpoints: ApiDocEndpoint[];
  downloadUrl: string;
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

export function loadDashboardState(): Promise<DashboardState> {
  return getJson<DashboardState>('/admin/api/dashboard');
}

export function loadStoreApps(pathAndQuery: string): Promise<StoreAppsState> {
  return getJson<StoreAppsState>(`/admin/api/store-apps${pathAndQuery}`);
}

export function loadStoreReviews(pathAndQuery: string): Promise<StoreReviewsState> {
  return getJson<StoreReviewsState>(`/admin/api/store-reviews${pathAndQuery}`);
}

export function loadUploadState(): Promise<UploadState> {
  return getJson<UploadState>('/admin/api/uploads');
}

export function loadBuildsState(): Promise<BuildsState> {
  return getJson<BuildsState>('/admin/api/builds');
}

export function loadDevicesState(): Promise<DevicesState> {
  return getJson<DevicesState>('/admin/api/devices');
}

export function loadNotificationsState(pathAndQuery: string): Promise<NotificationsState> {
  return getJson<NotificationsState>(`/admin/api/notifications${pathAndQuery}`);
}

export function loadApiDocsState(): Promise<ApiDocsState> {
  return getJson<ApiDocsState>('/admin/api/api-docs');
}

export function loadAppLogs(): Promise<AppLogsState> {
  return getJson<AppLogsState>('/admin/api/app-logs');
}

export function loadAppLogEvents(cursor: number): Promise<AppLogsState> {
  return getJson<AppLogsState>(`/admin/api/app-logs/events?cursor=${cursor}`);
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

export function uploadPackage(
  formData: FormData,
  onProgress: (percent: number) => void
): Promise<AdminUploadResponse> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', '/admin/api/uploads');
    request.setRequestHeader('Accept', 'application/json');
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)));
      }
    });
    request.addEventListener('load', () => {
      const payload = parseJson(request.responseText);
      if (request.status < 200 || request.status >= 300) {
        const error = payload?.error;
        reject(
          new AdminApiError(
            error?.message || `请求失败：HTTP ${request.status}`,
            error?.code || 'http_error',
            error?.detail || null
          )
        );
        return;
      }
      onProgress(100);
      resolve(payload as AdminUploadResponse);
    });
    request.addEventListener('error', () => {
      reject(new AdminApiError('上传失败，请检查网络后重试', 'upload_network_error'));
    });
    request.send(formData);
  });
}

function parseJson(value: string): any {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
