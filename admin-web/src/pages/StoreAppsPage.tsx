import { useEffect, useState, type MouseEvent } from 'react';
import {
  AdminApiError,
  loadStoreApps,
  type StoreAppItem,
  type StoreAppsState
} from '../app/apiClient';

const filters = [
  { label: '全部', value: 'all' },
  { label: 'iOS', value: 'ios' },
  { label: 'Android', value: 'android' },
  { label: '需处理', value: 'needs' },
  { label: '可同步', value: 'ok' }
];

type LoadingState = 'idle' | 'load';

export function StoreAppsPage() {
  const [state, setState] = useState<StoreAppsState | null>(null);
  const [loading, setLoading] = useState<LoadingState>('load');
  const [error, setError] = useState('');

  useEffect(() => {
    void loadFromLocation();
    const onPopState = () => void loadFromLocation();
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  async function loadFromLocation() {
    setLoading('load');
    setError('');
    try {
      setState(await loadStoreApps(location.search || ''));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading('idle');
    }
  }

  async function selectFilter(value: string) {
    const nextPath = storeAppsPath({ filter: value, appId: '' });
    history.pushState({ adminRoute: 'apps', filter: value }, '', nextPath);
    await loadFromLocation();
  }

  async function selectApp(app: StoreAppItem) {
    const nextPath = storeAppsPath({ filter: state?.filter ?? 'all', appId: app.id });
    history.pushState({ adminRoute: 'apps', appId: app.id }, '', nextPath);
    await loadFromLocation();
  }

  function openReviews(app: StoreAppItem) {
    if (!app.reviewsPath) return;
    history.pushState({ adminRoute: 'store-reviews' }, '', app.reviewsPath);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  function openInternalPath(event: MouseEvent<HTMLAnchorElement>, path: string) {
    event.preventDefault();
    event.stopPropagation();
    if (!path) return;
    history.pushState({ adminRoute: 'accounts' }, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  return (
    <div className="store-apps-page" data-store-apps-page>
      {error ? <div className="notice error">{error}</div> : null}

      <div className="store-apps-layout">
        <aside className="store-apps-side">
          <section className="panel store-account-summary">
            <div className="panel-head compact">
              <strong>筛选</strong>
              <span>{state?.stats.total ?? 0} 个应用</span>
            </div>
            <div className="filter-tabs vertical" aria-label="商店应用筛选">
              {filters.map((filter) => (
                <button
                  key={filter.value}
                  className={state?.filter === filter.value ? 'filter-tab active' : 'filter-tab'}
                  type="button"
                  onClick={() => void selectFilter(filter.value)}
                >
                  {filter.label}
                </button>
              ))}
            </div>
            <div className="store-apps-counts">
              <span>{state?.stats.ios ?? 0} 个 iOS</span>
              <span>{state?.stats.android ?? 0} 个 Android</span>
              <span>{state?.stats.ready ?? 0} 个可同步</span>
              <span>{state?.stats.needs ?? 0} 个需处理</span>
            </div>
          </section>

          <section className="panel store-account-summary">
            <div className="panel-head compact">
              <strong>账号与连接</strong>
              <a
                className="button"
                href="/admin-next/accounts"
                onClick={(event) => openInternalPath(event, '/admin-next/accounts')}
              >
                打开账号
              </a>
            </div>
            <div className="summary-list">
              <SummaryRow label="开发者账号" value={state?.accountSummary.totalAccounts ?? 0} />
              <SummaryRow label="已绑定应用" value={state?.accountSummary.boundApps ?? 0} />
              <SummaryRow label="Connector 正常" value={state?.accountSummary.connectorOk ?? 0} />
              <SummaryRow label="Connector 需处理" value={state?.accountSummary.connectorNeeds ?? 0} />
              <SummaryRow label="续费提醒" value={state?.accountSummary.renewalReminders ?? 0} />
            </div>
          </section>
        </aside>

        <section className="panel store-apps-list-panel">
          <div className="panel-head compact">
            <strong>商店应用</strong>
            <span>每个应用可以直接进入商店管理或评论分析</span>
          </div>
          <div className="store-app-table" role="table" aria-label="商店应用">
            <div className="store-app-table-row header" role="row">
              <span>应用</span>
              <span>平台</span>
              <span>开发者账号</span>
              <span>商店状态</span>
              <span>最新构建</span>
              <span>操作</span>
            </div>
            {state?.apps.map((app) => (
              <div
                key={app.id}
                className={app.selected ? 'store-app-table-row active' : 'store-app-table-row'}
                role="row"
                tabIndex={0}
                onClick={() => void selectApp(app)}
              >
                <span className="app-cell">
                  <span className="app-avatar" style={{ backgroundColor: app.iconColor }}>
                    {app.iconText}
                  </span>
                  <span>
                    <strong>{app.name}</strong>
                    <small>{app.bundleIdentifier}</small>
                  </span>
                </span>
                <span>{platformLabel(app.platform)}</span>
                <span>{app.developerAccountName || '未绑定'}</span>
                <span className={`tag ${app.status === 'ready' ? 'ok' : 'warn'}`}>
                  {app.statusLabel}
                </span>
                <span>{buildLabel(app)}</span>
                <span className="store-app-row-actions">
                  {app.storeManagementPath ? (
                    <a
                      className="button primary"
                      href={app.storeManagementPath}
                      onClick={(event) => openInternalPath(event, app.storeManagementPath)}
                    >
                      商店管理
                    </a>
                  ) : (
                    <a
                      className="button"
                      href="/admin-next/accounts"
                      onClick={(event) => openInternalPath(event, '/admin-next/accounts')}
                    >
                      绑定账号
                    </a>
                  )}
                  <a
                    className="button"
                    href={app.reviewsPath || '/admin-next/store-reviews'}
                    aria-disabled={!app.reviewsPath}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      openReviews(app);
                    }}
                  >
                    评论分析
                  </a>
                </span>
              </div>
            ))}
          </div>
          {loading === 'load' ? <div className="empty-state">正在加载商店应用...</div> : null}
          {state && state.apps.length === 0 && loading === 'idle' ? (
            <div className="empty-state">当前筛选下没有应用。</div>
          ) : null}
        </section>

      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function storeAppsPath({ filter, appId }: { filter: string; appId: string }) {
  const params = new URLSearchParams();
  if (filter && filter !== 'all') params.set('filter', filter);
  if (appId) params.set('appId', appId);
  const query = params.toString();
  return query ? `/admin-next/apps?${query}` : '/admin-next/apps';
}

function platformLabel(platform: string) {
  if (platform === 'ios') return 'iOS';
  if (platform === 'android') return 'Android';
  return platform || '未知';
}

function buildLabel(app: StoreAppItem) {
  if (!app.latestBuild) return '暂无构建';
  return `${app.latestBuild.version} (${app.latestBuild.buildNumber})`;
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
