import { useEffect, useMemo, useState, type MouseEvent } from 'react';
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

  const selectedApp = useMemo(() => state?.selectedApp ?? null, [state]);

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
    if (!path) return;
    history.pushState({ adminRoute: 'accounts' }, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  return (
    <div className="store-apps-page" data-store-apps-page>
      <section className="store-apps-filterbar">
        <div className="filter-tabs" aria-label="商店应用筛选">
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
          <span>{state?.stats.total ?? 0} 个应用</span>
          <span>{state?.stats.ready ?? 0} 个可同步</span>
          <span>{state?.stats.needs ?? 0} 个需处理</span>
        </div>
      </section>

      {error ? <div className="notice error">{error}</div> : null}

      <div className="store-apps-layout">
        <section className="panel store-apps-list-panel">
          <div className="panel-head compact">
            <strong>商店应用</strong>
            <span>点击应用查看操作</span>
          </div>
          <div className="store-app-table" role="table" aria-label="商店应用">
            <div className="store-app-table-row header" role="row">
              <span>应用</span>
              <span>平台</span>
              <span>开发者账号</span>
              <span>商店状态</span>
              <span>最新构建</span>
            </div>
            {state?.apps.map((app) => (
              <button
                key={app.id}
                className={app.selected ? 'store-app-table-row active' : 'store-app-table-row'}
                type="button"
                role="row"
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
              </button>
            ))}
          </div>
          {loading === 'load' ? <div className="empty-state">正在加载商店应用...</div> : null}
          {state && state.apps.length === 0 && loading === 'idle' ? (
            <div className="empty-state">当前筛选下没有应用。</div>
          ) : null}
        </section>

        <aside className="store-apps-side">
          <section className="panel selected-store-app-panel">
            <div className="panel-head compact">
              <strong>当前应用</strong>
              <span>{selectedApp?.statusLabel ?? '未选择'}</span>
            </div>
            {selectedApp ? (
              <div className="selected-store-app">
                <div className="selected-store-app-title">
                  <span className="app-avatar" style={{ backgroundColor: selectedApp.iconColor }}>
                    {selectedApp.iconText}
                  </span>
                  <div>
                    <strong>{selectedApp.name}</strong>
                    <span>{selectedApp.bundleIdentifier}</span>
                  </div>
                </div>
                <dl>
                  <div>
                    <dt>平台</dt>
                    <dd>{platformLabel(selectedApp.platform)}</dd>
                  </div>
                  <div>
                    <dt>开发者账号</dt>
                    <dd>{selectedApp.developerAccountName || '未绑定'}</dd>
                  </div>
                  <div>
                    <dt>商店标识</dt>
                    <dd>{selectedApp.storeIdentifier || '未填写'}</dd>
                  </div>
                  <div>
                    <dt>最新构建</dt>
                    <dd>{buildLabel(selectedApp)}</dd>
                  </div>
                </dl>
                <div className="selected-store-actions">
                  {selectedApp.storeManagementPath ? (
                    <a
                      className="button primary"
                      href={selectedApp.storeManagementPath}
                      onClick={(event) => openInternalPath(event, selectedApp.storeManagementPath)}
                    >
                      打开商店编辑
                    </a>
                  ) : (
                    <a
                      className="button"
                      href="/admin-next/accounts"
                      onClick={(event) => openInternalPath(event, '/admin-next/accounts')}
                    >
                      先绑定账号
                    </a>
                  )}
                  <button
                    className="button"
                    type="button"
                    onClick={() => openReviews(selectedApp)}
                    disabled={!selectedApp.reviewsPath}
                  >
                    评论分析
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-state">从左侧选择一个应用。</div>
            )}
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
