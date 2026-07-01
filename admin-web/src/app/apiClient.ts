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

export function bootstrapAdmin(): Promise<BootstrapResponse> {
  return getJson<BootstrapResponse>('/admin/api/bootstrap');
}
