import { useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  AdminApiError,
  bindAccountApp,
  checkAccountConnector,
  checkMarketingPagePreflight,
  checkStoreWorkspacePreflight,
  copyMarketingPage,
  createMarketingPage,
  createDeveloperAccount,
  deleteMarketingPage,
  deleteMarketingPageImage,
  deleteStoreWorkspaceImage,
  loadDeveloperAccount,
  loadDeveloperAccounts,
  loadMarketingPage,
  loadStoreWorkspace,
  saveAccountConnector,
  saveMarketingPage,
  saveStoreWorkspaceMetadata,
  saveStoreWorkspaceReleaseNotes,
  syncMarketingPage,
  syncStoreWorkspaceMetadata,
  unbindAccountApp,
  updateAccountAppSettings,
  updateDeveloperAccount,
  uploadMarketingPageImages,
  uploadStoreWorkspaceImages,
  type AccountAppItem,
  type DeveloperAccountDetailState,
  type DeveloperAccountForm,
  type DeveloperAccountSummary,
  type DeveloperAccountsState,
  type MarketingPageDetailState,
  type MarketingPageLocaleContent,
  type MarketingPageLocaleInput,
  type MarketingPagePayload,
  type StoreLocaleContent,
  type StoreLocaleContentInput,
  type StoreMarketingPageSummary,
  type StoreWorkspaceState
} from '../app/apiClient';

type StoreImageUploadRequest = { locale: string; slotKey: string; files: File[] };

type AccountRoute =
  | { kind: 'list' }
  | { kind: 'new' }
  | { kind: 'detail'; accountId: string }
  | { kind: 'edit'; accountId: string }
  | { kind: 'app'; accountId: string; appId: string; section: StoreSection; pageId?: string };

type StoreSection = 'store' | 'marketing' | 'release-notes' | 'connection';

const accountStatuses = [
  { value: 'ok', label: '正常' },
  { value: 'renewal_due', label: '需要续费' },
  { value: 'expired', label: '已过期' },
  { value: 'disabled', label: '已停用' }
];

const storeSections: Array<{ key: StoreSection; label: string; description: string }> = [
  { key: 'store', label: '默认商店页', description: '宣传文本、描述、商店图和版本说明' },
  { key: 'marketing', label: '营销页面', description: '自定义产品页面和产品页面优化' },
  { key: 'release-notes', label: '版本说明', description: '最新商店版本的 Release Notes' },
  { key: 'connection', label: '商店连接', description: 'Connector、商店标识和连接检查' }
];

export function DeveloperAccountsPage() {
  const [route, setRoute] = useState<AccountRoute>(() => parseAccountRoute(location.pathname));
  const [accountsState, setAccountsState] = useState<DeveloperAccountsState | null>(null);
  const [detailState, setDetailState] = useState<DeveloperAccountDetailState | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    void loadFromLocation();
    const onPopState = () => void loadFromLocation();
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  async function loadFromLocation() {
    const nextRoute = parseAccountRoute(location.pathname);
    setRoute(nextRoute);
    setLoading(true);
    setError('');
    try {
      if (nextRoute.kind === 'list' || nextRoute.kind === 'new') {
        setDetailState(null);
        setAccountsState(await loadDeveloperAccounts());
      } else {
        setDetailState(await loadDeveloperAccount(nextRoute.accountId));
      }
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  function navigate(path: string) {
    history.pushState({ adminRoute: 'accounts' }, '', path);
    void loadFromLocation();
  }

  function showMessage(value: string) {
    setMessage(value);
    window.setTimeout(() => setMessage(''), 2400);
  }

  async function submitAccount(payload: DeveloperAccountForm, accountId?: string) {
    setError('');
    try {
      const response = accountId
        ? await updateDeveloperAccount(accountId, payload)
        : await createDeveloperAccount(payload);
      setAccountsState(response.state);
      showMessage(response.message);
      navigate(response.account.detailPath);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  async function refreshDetail(responseMessage?: string) {
    const nextRoute = parseAccountRoute(location.pathname);
    if (nextRoute.kind === 'detail' || nextRoute.kind === 'edit' || nextRoute.kind === 'app') {
      setDetailState(await loadDeveloperAccount(nextRoute.accountId));
      if (responseMessage) showMessage(responseMessage);
    }
  }

  async function saveConnector(payload: { name: string; baseUrl: string; authToken: string }) {
    if (!detailState) return;
    setError('');
    try {
      const response = await saveAccountConnector(detailState.account.id, payload);
      setDetailState(response.state);
      showMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  async function checkConnector() {
    if (!detailState) return;
    setError('');
    try {
      const response = await checkAccountConnector(detailState.account.id);
      setDetailState(response.state);
      showMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  async function bindApp(payload: { appId: string; storeAppId: string; storePackageName: string }) {
    if (!detailState) return;
    setError('');
    try {
      const response = await bindAccountApp(detailState.account.id, payload);
      setDetailState(response.state);
      showMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  async function saveAppSettings(
    app: AccountAppItem,
    payload: { storeAppId: string; storePackageName: string }
  ) {
    if (!detailState) return;
    setError('');
    try {
      const response = await updateAccountAppSettings(detailState.account.id, app.id, payload);
      setDetailState(response.state);
      showMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  async function removeApp(app: AccountAppItem) {
    if (!detailState) return;
    setError('');
    try {
      const response = await unbindAccountApp(detailState.account.id, app.id);
      setDetailState(response.state);
      showMessage(response.message);
      await refreshDetail();
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  return (
    <div className="accounts-page">
      {message ? <div className="notice ok">{message}</div> : null}
      {error ? <div className="notice error">{error}</div> : null}
      {loading ? <div className="empty-state">正在加载开发者账号...</div> : null}

      {route.kind === 'list' ? (
        <AccountsList state={accountsState} onNavigate={navigate} />
      ) : null}
      {route.kind === 'new' ? (
        <AccountEditor
          title="新增开发者账号"
          onCancel={() => navigate('/admin/accounts')}
          onSubmit={(payload) => void submitAccount(payload)}
        />
      ) : null}
      {route.kind === 'detail' && detailState ? (
        <AccountDetail
          state={detailState}
          onNavigate={navigate}
          onCheckConnector={() => void checkConnector()}
          onSaveConnector={(payload) => void saveConnector(payload)}
          onBindApp={(payload) => void bindApp(payload)}
          onSaveAppSettings={(app, payload) => void saveAppSettings(app, payload)}
          onRemoveApp={(app) => void removeApp(app)}
        />
      ) : null}
      {route.kind === 'edit' && detailState ? (
        <AccountEditor
          title="编辑开发者账号"
          account={detailState.account}
          onCancel={() => navigate(`/admin/accounts/${detailState.account.id}`)}
          onSubmit={(payload) => void submitAccount(payload, detailState.account.id)}
        />
      ) : null}
      {route.kind === 'app' && detailState ? (
        <StoreWorkspace
          state={detailState}
          appId={route.appId}
          section={route.section}
          pageId={route.pageId}
          onNavigate={navigate}
          onCheckConnector={() => void checkConnector()}
          onSaveConnector={(payload) => void saveConnector(payload)}
          onSaveAppSettings={(app, payload) => void saveAppSettings(app, payload)}
        />
      ) : null}
    </div>
  );
}

function AccountsList({
  state,
  onNavigate
}: {
  state: DeveloperAccountsState | null;
  onNavigate: (path: string) => void;
}) {
  const accounts = state?.accounts ?? [];
  return (
    <div className="accounts-layout">
      <section className="panel accounts-table-panel">
        <div className="panel-head compact">
          <strong>开发者账号</strong>
          <button className="button primary" type="button" onClick={() => onNavigate('/admin/accounts/new')}>
            新增账号
          </button>
        </div>
        <div className="account-stats-row">
          <Metric label="账号" value={state?.stats.total ?? 0} />
          <Metric label="正常" value={state?.stats.ok ?? 0} />
          <Metric label="需处理" value={state?.stats.needs ?? 0} />
          <Metric label="绑定应用" value={state?.stats.boundApps ?? 0} />
        </div>
        <div className="account-table">
          <div className="account-row header">
            <span>账号</span>
            <span>应用</span>
            <span>Connector</span>
            <span>到期</span>
            <span>操作</span>
          </div>
          {accounts.map((account) => (
            <button
              key={account.id}
              className="account-row"
              type="button"
              onClick={() => onNavigate(account.detailPath)}
            >
              <span>
                <strong>{account.teamName}</strong>
                <small>{account.id}</small>
              </span>
              <span>{account.appNames.length ? account.appNames.join('、') : '未绑定 App'}</span>
              <span className={`tag ${account.connectorStatus === 'ok' ? 'ok' : 'warn'}`}>
                {account.connectorStatusLabel}
              </span>
              <span>{account.expiresAtLabel}</span>
              <span className="button slim">打开</span>
            </button>
          ))}
        </div>
        {!accounts.length ? <div className="empty-state">还没有开发者账号。</div> : null}
      </section>
    </div>
  );
}

function AccountDetail({
  state,
  onNavigate,
  onCheckConnector,
  onSaveConnector,
  onBindApp,
  onSaveAppSettings,
  onRemoveApp
}: {
  state: DeveloperAccountDetailState;
  onNavigate: (path: string) => void;
  onCheckConnector: () => void;
  onSaveConnector: (payload: { name: string; baseUrl: string; authToken: string }) => void;
  onBindApp: (payload: { appId: string; storeAppId: string; storePackageName: string }) => void;
  onSaveAppSettings: (
    app: AccountAppItem,
    payload: { storeAppId: string; storePackageName: string }
  ) => void;
  onRemoveApp: (app: AccountAppItem) => void;
}) {
  return (
    <div className="account-detail-layout">
      <section className="panel account-overview-card">
        <div className="panel-head compact">
          <div>
            <strong>{state.account.teamName}</strong>
            <p className="muted">{state.account.id}</p>
          </div>
          <button
            className="button"
            type="button"
            onClick={() => onNavigate(`/admin/accounts/${state.account.id}/edit`)}
          >
            编辑账号
          </button>
        </div>
        <div className="account-stats-row">
          <Metric label="账号状态" value={state.account.statusLabel} />
          <Metric label="到期时间" value={state.account.expiresAtLabel} />
          <Metric label="绑定应用" value={state.apps.length} />
          <Metric label="Connector" value={state.connector?.statusLabel ?? '未配置'} />
        </div>
      </section>

      <section className="panel connector-panel">
        <div className="panel-head compact">
          <strong>Connector</strong>
          <button className="button" type="button" onClick={onCheckConnector}>
            检查连接
          </button>
        </div>
        <ConnectorForm connector={state.connector} onSubmit={onSaveConnector} />
      </section>

      <section className="panel account-apps-panel">
        <div className="panel-head compact">
          <strong>已绑定 App</strong>
          <span>{state.apps.length} 个</span>
        </div>
        <div className="account-app-list">
          {state.apps.map((app) => (
            <BoundAppCard
              key={app.id}
              accountId={state.account.id}
              app={app}
              onNavigate={onNavigate}
              onSave={(payload) => onSaveAppSettings(app, payload)}
              onRemove={() => onRemoveApp(app)}
            />
          ))}
        </div>
        {!state.apps.length ? <div className="empty-state">这个账号还没有绑定 App。</div> : null}
      </section>

      <section className="panel">
        <div className="panel-head compact">
          <strong>绑定新 App</strong>
          <span>{state.unassignedApps.length} 个可选</span>
        </div>
        <BindAppForm state={state} onSubmit={onBindApp} />
      </section>

      <section className="panel">
        <div className="panel-head compact">
          <strong>最近同步</strong>
          <span>{state.syncRuns.length} 条</span>
        </div>
        <div className="sync-run-list">
          {state.syncRuns.map((run) => (
            <div key={run.id} className="sync-run-row">
              <strong>{run.operation || '同步任务'}</strong>
              <span>{run.status}</span>
              <span>{run.startedAtLabel}</span>
              <small>{run.summary}</small>
            </div>
          ))}
        </div>
        {!state.syncRuns.length ? <div className="empty-state">暂无同步记录。</div> : null}
      </section>
    </div>
  );
}

function StoreWorkspace({
  state,
  appId,
  section,
  pageId,
  onNavigate,
  onCheckConnector,
  onSaveConnector,
  onSaveAppSettings
}: {
  state: DeveloperAccountDetailState;
  appId: string;
  section: StoreSection;
  pageId?: string;
  onNavigate: (path: string) => void;
  onCheckConnector: () => void;
  onSaveConnector: (payload: { name: string; baseUrl: string; authToken: string }) => void;
  onSaveAppSettings: (
    app: AccountAppItem,
    payload: { storeAppId: string; storePackageName: string }
  ) => void;
}) {
  const app = state.apps.find((item) => item.id === appId) ?? null;
  const sectionLabel = storeSections.find((item) => item.key === section)?.label ?? '商店工作区';
  const [workspace, setWorkspace] = useState<StoreWorkspaceState | null>(null);
  const [marketingPage, setMarketingPage] = useState<MarketingPageDetailState | null>(null);
  const [workspaceError, setWorkspaceError] = useState('');
  const [workspaceNotice, setWorkspaceNotice] = useState('');
  const [workspaceBusy, setWorkspaceBusy] = useState(false);

  useEffect(() => {
    let active = true;
    setWorkspaceError('');
    setWorkspace(null);
    setMarketingPage(null);
    loadStoreWorkspace(state.account.id, appId, section)
      .then((payload) => {
        if (active) setWorkspace(payload);
      })
      .catch((requestError) => {
        if (active) setWorkspaceError(errorMessage(requestError));
      });
    return () => {
      active = false;
    };
  }, [appId, section, state.account.id]);

  useEffect(() => {
    if (!pageId || section !== 'marketing') return;
    let active = true;
    setWorkspaceError('');
    loadMarketingPage(state.account.id, appId, pageId)
      .then((payload) => {
        if (active) setMarketingPage(payload);
      })
      .catch((requestError) => {
        if (active) setWorkspaceError(errorMessage(requestError));
      });
    return () => {
      active = false;
    };
  }, [appId, pageId, section, state.account.id]);

  function showWorkspaceNotice(value: string) {
    setWorkspaceNotice(value);
    window.setTimeout(() => setWorkspaceNotice(''), 2400);
  }

  async function saveMetadata(locales: StoreLocaleContentInput[]) {
    if (!workspace) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await saveStoreWorkspaceMetadata(state.account.id, appId, {
        version: workspace.version,
        locale: workspace.locale || workspace.sourceLocale,
        locales
      });
      setWorkspace(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function saveReleaseNotes(locales: StoreLocaleContentInput[]) {
    if (!workspace) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await saveStoreWorkspaceReleaseNotes(state.account.id, appId, {
        version: workspace.version,
        locale: workspace.locale || workspace.sourceLocale,
        locales
      });
      setWorkspace(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function checkPreflight(locales: StoreLocaleContentInput[], syncScopes: string[]) {
    if (!workspace) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await checkStoreWorkspacePreflight(state.account.id, appId, {
        version: workspace.version,
        locale: workspace.locale || workspace.sourceLocale,
        syncScopes,
        locales
      });
      setWorkspace(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function syncWorkspace(locales: StoreLocaleContentInput[], syncScopes: string[]) {
    if (!workspace) return;
    const scopeLabel = syncScopes.join('、');
    if (!window.confirm(`确认同步到商店？\n范围：${scopeLabel}\n语言：${locales.map((item) => item.locale).join('、')}`)) {
      return;
    }
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await syncStoreWorkspaceMetadata(state.account.id, appId, {
        version: workspace.version,
        locale: workspace.locale || workspace.sourceLocale,
        syncScopes,
        locales
      });
      setWorkspace(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function deleteImage(payload: { locale: string; slotKey: string; storageKey: string }) {
    if (!workspace) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await deleteStoreWorkspaceImage(state.account.id, appId, {
        ...payload,
        version: workspace.version
      });
      setWorkspace(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function uploadImages(payload: StoreImageUploadRequest) {
    if (!workspace || payload.files.length === 0) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await uploadStoreWorkspaceImages(
        state.account.id,
        appId,
        storeImageFormData(payload)
      );
      setWorkspace(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function createMarketing(payload: MarketingPagePayload) {
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await createMarketingPage(state.account.id, appId, payload);
      if (response.workspace) setWorkspace(response.workspace);
      if (response.state) {
        setMarketingPage(response.state);
        onNavigate(response.state.page.detailPath);
      }
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function saveMarketing(payload: MarketingPagePayload) {
    if (!marketingPage) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await saveMarketingPage(
        state.account.id,
        appId,
        marketingPage.page.pageId,
        payload
      );
      if (response.workspace) setWorkspace(response.workspace);
      if (response.state) setMarketingPage(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function copyMarketing() {
    if (!marketingPage) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await copyMarketingPage(state.account.id, appId, marketingPage.page.pageId);
      if (response.workspace) setWorkspace(response.workspace);
      if (response.state) {
        setMarketingPage(response.state);
        onNavigate(response.state.page.detailPath);
      }
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function removeMarketing() {
    if (!marketingPage) return;
    if (!window.confirm(`确认删除「${marketingPage.page.pageName}」？只会删除中心后台草稿。`)) {
      return;
    }
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await deleteMarketingPage(state.account.id, appId, marketingPage.page.pageId);
      if (response.workspace) setWorkspace(response.workspace);
      setMarketingPage(null);
      showWorkspaceNotice(response.message);
      onNavigate(`/admin/accounts/${state.account.id}/apps/${appId}/marketing`);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function checkMarketing(payload: MarketingPagePayload) {
    if (!marketingPage) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await checkMarketingPagePreflight(
        state.account.id,
        appId,
        marketingPage.page.pageId,
        payload
      );
      if (response.state) setMarketingPage(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function syncMarketing(payload: MarketingPagePayload) {
    if (!marketingPage) return;
    const scopes = payload.syncScopes?.join('、') || '未选择';
    if (!window.confirm(`确认同步营销页面？\n范围：${scopes}\n页面：${marketingPage.page.pageName}`)) {
      return;
    }
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await syncMarketingPage(
        state.account.id,
        appId,
        marketingPage.page.pageId,
        payload
      );
      if (response.workspace) setWorkspace(response.workspace);
      if (response.state) setMarketingPage(response.state);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function deleteMarketingImage(payload: { locale: string; slotKey: string; storageKey: string }) {
    if (!marketingPage) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await deleteMarketingPageImage(
        state.account.id,
        appId,
        marketingPage.page.pageId,
        payload
      );
      if (response.state) setMarketingPage(response.state);
      if (response.workspace) setWorkspace(response.workspace);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function uploadMarketingImages(payload: StoreImageUploadRequest) {
    if (!marketingPage || payload.files.length === 0) return;
    setWorkspaceBusy(true);
    setWorkspaceError('');
    try {
      const response = await uploadMarketingPageImages(
        state.account.id,
        appId,
        marketingPage.page.pageId,
        storeImageFormData(payload)
      );
      if (response.state) setMarketingPage(response.state);
      if (response.workspace) setWorkspace(response.workspace);
      showWorkspaceNotice(response.message);
    } catch (requestError) {
      setWorkspaceError(errorMessage(requestError));
    } finally {
      setWorkspaceBusy(false);
    }
  }

  if (!app) {
    return <div className="notice error">当前账号下没有这个 App。</div>;
  }

  return (
    <div className="store-workspace-page">
      <section className="panel store-workspace-head">
        <div>
          <p className="eyebrow">{state.account.teamName}</p>
          <h2>{app.name}</h2>
          <p className="muted">{app.bundleIdentifier}</p>
        </div>
        <button
          className="button"
          type="button"
          onClick={() => onNavigate(`/admin/accounts/${state.account.id}`)}
        >
          返回账号
        </button>
      </section>

      <section className="store-section-tabs" aria-label="商店工作区">
        {storeSections.map((item) => (
          <button
            key={item.key}
            className={item.key === section ? 'store-section-tab active' : 'store-section-tab'}
            type="button"
            onClick={() => onNavigate(`/admin/accounts/${state.account.id}/apps/${app.id}/${item.key}`)}
          >
            <strong>{item.label}</strong>
            <span>{item.description}</span>
          </button>
        ))}
      </section>

      <section className="panel">
        <div className="panel-head compact">
          <strong>{sectionLabel}</strong>
          <span>{app.platformLabel} / {app.latestVersionLabel}</span>
        </div>

        {section === 'connection' ? (
          <div className="connection-workspace">
            <ConnectorForm connector={state.connector} onSubmit={onSaveConnector} />
            <button className="button" type="button" onClick={onCheckConnector}>
              检查连接
            </button>
            <BoundAppSettings app={app} onSave={(payload) => onSaveAppSettings(app, payload)} />
          </div>
        ) : null}

        {workspaceError ? <div className="notice error">{workspaceError}</div> : null}
        {workspaceNotice ? <div className="notice ok">{workspaceNotice}</div> : null}
        {!workspace && !workspaceError && section !== 'connection' ? (
          <div className="empty-state">正在加载商店工作区...</div>
        ) : null}

        {workspace && section === 'store' ? (
          <StoreDefaultPanel
            workspace={workspace}
            busy={workspaceBusy}
            onSave={saveMetadata}
            onCheck={checkPreflight}
            onSync={syncWorkspace}
            onDeleteImage={deleteImage}
            onUploadImages={uploadImages}
          />
        ) : null}
        {workspace && section === 'marketing' ? (
          pageId ? (
            <MarketingPageDetailPanel
              detail={marketingPage}
              busy={workspaceBusy}
              onBack={() => onNavigate(`/admin/accounts/${state.account.id}/apps/${app.id}/marketing`)}
              onSave={saveMarketing}
              onCheck={checkMarketing}
              onSync={syncMarketing}
              onCopy={() => void copyMarketing()}
              onDelete={() => void removeMarketing()}
              onDeleteImage={deleteMarketingImage}
              onUploadImages={uploadMarketingImages}
            />
          ) : (
            <MarketingPagesPanel
              workspace={workspace}
              busy={workspaceBusy}
              onNavigate={onNavigate}
              onCreate={createMarketing}
            />
          )
        ) : null}
        {workspace && section === 'release-notes' ? (
          <ReleaseNotesPanel
            workspace={workspace}
            busy={workspaceBusy}
            onSave={saveReleaseNotes}
            onCheck={checkPreflight}
            onSync={syncWorkspace}
          />
        ) : null}
      </section>
    </div>
  );
}

function AccountEditor({
  title,
  account,
  onCancel,
  onSubmit
}: {
  title: string;
  account?: DeveloperAccountSummary;
  onCancel: () => void;
  onSubmit: (payload: DeveloperAccountForm) => void;
}) {
  const [accountId, setAccountId] = useState(account?.id ?? '');
  const [teamName, setTeamName] = useState(account?.teamName ?? '');
  const [expiresAt, setExpiresAt] = useState(toDateTimeInput(account?.expiresAt ?? ''));
  const [status, setStatus] = useState(account?.status ?? 'renewal_due');
  const [renewalActionLabel, setRenewalActionLabel] = useState('去续费');

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({
      accountId: account ? account.id : accountId,
      teamName,
      expiresAt,
      status,
      renewalActionLabel
    });
  }

  return (
    <section className="panel account-editor">
      <div className="panel-head compact">
        <strong>{title}</strong>
      </div>
      <form className="form-grid" onSubmit={submit}>
        <label>
          <span>账号 ID</span>
          <input value={accountId} onChange={(event) => setAccountId(event.target.value)} disabled={Boolean(account)} />
        </label>
        <label>
          <span>Team 名称</span>
          <input value={teamName} onChange={(event) => setTeamName(event.target.value)} />
        </label>
        <label>
          <span>到期时间</span>
          <input
            type="datetime-local"
            value={expiresAt}
            onChange={(event) => setExpiresAt(event.target.value)}
          />
        </label>
        <label>
          <span>状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            {accountStatuses.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>提醒动作</span>
          <input
            value={renewalActionLabel}
            onChange={(event) => setRenewalActionLabel(event.target.value)}
          />
        </label>
        <div className="form-actions">
          <button className="button" type="button" onClick={onCancel}>
            取消
          </button>
          <button className="button primary" type="submit">
            保存账号
          </button>
        </div>
      </form>
    </section>
  );
}

function ConnectorForm({
  connector,
  onSubmit
}: {
  connector: DeveloperAccountDetailState['connector'];
  onSubmit: (payload: { name: string; baseUrl: string; authToken: string }) => void;
}) {
  const [name, setName] = useState(connector?.name ?? 'Connector');
  const [baseUrl, setBaseUrl] = useState(connector?.baseUrl ?? '');
  const [authToken, setAuthToken] = useState(connector?.authToken ?? '');

  useEffect(() => {
    setName(connector?.name ?? 'Connector');
    setBaseUrl(connector?.baseUrl ?? '');
    setAuthToken(connector?.authToken ?? '');
  }, [connector]);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ name, baseUrl, authToken });
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <label>
        <span>名称</span>
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        <span>地址</span>
        <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
      </label>
      <label>
        <span>Token</span>
        <input value={authToken} onChange={(event) => setAuthToken(event.target.value)} />
      </label>
      <div className="form-actions">
        <span className={`tag ${connector?.status === 'ok' ? 'ok' : 'warn'}`}>
          {connector?.statusLabel ?? '未配置'}
        </span>
        <button className="button" type="submit">
          保存 Connector
        </button>
      </div>
    </form>
  );
}

function BindAppForm({
  state,
  onSubmit
}: {
  state: DeveloperAccountDetailState;
  onSubmit: (payload: { appId: string; storeAppId: string; storePackageName: string }) => void;
}) {
  const [appId, setAppId] = useState(state.unassignedApps[0]?.id ?? '');
  const [storeAppId, setStoreAppId] = useState('');
  const [storePackageName, setStorePackageName] = useState('');
  const selectedApp = useMemo(
    () => state.unassignedApps.find((app) => app.id === appId) ?? null,
    [appId, state.unassignedApps]
  );

  useEffect(() => {
    if (!appId && state.unassignedApps[0]) setAppId(state.unassignedApps[0].id);
  }, [appId, state.unassignedApps]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!appId) return;
    onSubmit({ appId, storeAppId, storePackageName });
    setStoreAppId('');
    setStorePackageName('');
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <label>
        <span>App</span>
        <select value={appId} onChange={(event) => setAppId(event.target.value)}>
          {state.unassignedApps.map((app) => (
            <option key={app.id} value={app.id}>
              {app.name} / {app.platformLabel}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>iOS App ID</span>
        <input
          value={storeAppId}
          onChange={(event) => setStoreAppId(event.target.value)}
          disabled={selectedApp?.platform === 'android'}
        />
      </label>
      <label>
        <span>Android Package</span>
        <input
          value={storePackageName}
          onChange={(event) => setStorePackageName(event.target.value)}
          disabled={selectedApp?.platform === 'ios'}
        />
      </label>
      <div className="form-actions">
        <button className="button primary" type="submit" disabled={!appId}>
          绑定 App
        </button>
      </div>
    </form>
  );
}

function BoundAppCard({
  accountId,
  app,
  onNavigate,
  onSave,
  onRemove
}: {
  accountId: string;
  app: AccountAppItem;
  onNavigate: (path: string) => void;
  onSave: (payload: { storeAppId: string; storePackageName: string }) => void;
  onRemove: () => void;
}) {
  return (
    <article className="bound-app-card">
      <div className="selected-store-app-title">
        <span className="app-avatar" style={{ backgroundColor: app.iconColor }}>
          {app.iconText}
        </span>
        <div>
          <strong>{app.name}</strong>
          <span>{app.bundleIdentifier}</span>
        </div>
      </div>
      <div className="bound-app-actions">
        <button className="button" type="button" onClick={() => onNavigate(app.storePath)}>
          商店管理
        </button>
        <button className="button" type="button" onClick={() => onNavigate(app.marketingPath)}>
          营销页面
        </button>
        <button className="button" type="button" onClick={() => onNavigate(app.connectionPath)}>
          连接设置
        </button>
        <button className="button" type="button" onClick={onRemove}>
          解绑
        </button>
      </div>
      <BoundAppSettings app={{ ...app, connectionPath: `/admin/accounts/${accountId}/apps/${app.id}/connection` }} onSave={onSave} />
    </article>
  );
}

function BoundAppSettings({
  app,
  onSave
}: {
  app: AccountAppItem;
  onSave: (payload: { storeAppId: string; storePackageName: string }) => void;
}) {
  const [storeAppId, setStoreAppId] = useState(app.storeAppId);
  const [storePackageName, setStorePackageName] = useState(app.storePackageName);

  useEffect(() => {
    setStoreAppId(app.storeAppId);
    setStorePackageName(app.storePackageName);
  }, [app]);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSave({ storeAppId, storePackageName });
  }

  return (
    <form className="app-settings-row" onSubmit={submit}>
      <label>
        <span>iOS App ID</span>
        <input
          value={storeAppId}
          onChange={(event) => setStoreAppId(event.target.value)}
          disabled={app.platform === 'android'}
        />
      </label>
      <label>
        <span>Android Package</span>
        <input
          value={storePackageName}
          onChange={(event) => setStorePackageName(event.target.value)}
          disabled={app.platform === 'ios'}
        />
      </label>
      <button className="button" type="submit">
        保存标识
      </button>
    </form>
  );
}

function StoreDefaultPanel({
  workspace,
  busy,
  onSave,
  onCheck,
  onSync,
  onDeleteImage,
  onUploadImages
}: {
  workspace: StoreWorkspaceState;
  busy: boolean;
  onSave: (locales: StoreLocaleContentInput[]) => void;
  onCheck: (locales: StoreLocaleContentInput[], syncScopes: string[]) => void;
  onSync: (locales: StoreLocaleContentInput[], syncScopes: string[]) => void;
  onDeleteImage: (payload: { locale: string; slotKey: string; storageKey: string }) => void;
  onUploadImages: (payload: StoreImageUploadRequest) => void;
}) {
  const [rows, setRows] = useState<StoreLocaleContent[]>(workspace.localizedMetadata);

  useEffect(() => {
    setRows(workspace.localizedMetadata);
  }, [workspace]);

  const currentLocale = workspace.locale || workspace.sourceLocale || rows[0]?.locale || '';
  const current = rows.find((item) => item.locale === currentLocale) ?? rows[0] ?? null;
  const payload = serializeStoreRows(rows);

  function updateField(field: 'promotionalText' | 'description', value: string) {
    setRows((currentRows) =>
      currentRows.map((item) =>
        item.locale === currentLocale ? { ...item, [field]: value } : item
      )
    );
  }

  return (
    <div className="workspace-content-grid">
      <section className="store-summary-strip">
        <span>当前商店最新版本：{workspace.version || '未确认'}</span>
        <span>{workspace.supportedLocales.length} 个语言</span>
        <span>{workspace.preflightLabel}</span>
        <button className="button" type="button" onClick={() => onSave(payload)} disabled={busy}>
          保存草稿
        </button>
        <button
          className="button"
          type="button"
          onClick={() => onCheck(payload, ['metadata', 'store_images'])}
          disabled={busy}
        >
          实时查询
        </button>
        <button
          className="button primary"
          type="button"
          onClick={() => onSync(payload, ['metadata', 'store_images'])}
          disabled={busy}
        >
          同步商店页
        </button>
      </section>
      <EditableFieldCard
        title="宣传文本"
        value={current?.promotionalText || ''}
        placeholder="App Store Connect promotional text"
        locales={rows}
        field="promotionalText"
        onChange={(value) => updateField('promotionalText', value)}
      />
      <EditableFieldCard
        title="描述"
        value={current?.description || ''}
        placeholder="App Store Connect description"
        locales={rows}
        field="description"
        onChange={(value) => updateField('description', value)}
      />
      <ImageOverview
        locales={rows}
        busy={busy}
        onDeleteImage={onDeleteImage}
        onUploadImages={onUploadImages}
      />
    </div>
  );
}

function ReleaseNotesPanel({
  workspace,
  busy,
  onSave,
  onCheck,
  onSync
}: {
  workspace: StoreWorkspaceState;
  busy: boolean;
  onSave: (locales: StoreLocaleContentInput[]) => void;
  onCheck: (locales: StoreLocaleContentInput[], syncScopes: string[]) => void;
  onSync: (locales: StoreLocaleContentInput[], syncScopes: string[]) => void;
}) {
  const [rows, setRows] = useState<StoreLocaleContent[]>(workspace.localizedMetadata);

  useEffect(() => {
    setRows(workspace.localizedMetadata);
  }, [workspace]);

  const currentLocale = workspace.locale || workspace.sourceLocale || rows[0]?.locale || '';
  const current = rows.find((item) => item.locale === currentLocale) ?? rows[0] ?? null;
  const payload = serializeStoreRows(rows);

  function updateReleaseNotes(value: string) {
    setRows((currentRows) =>
      currentRows.map((item) =>
        item.locale === currentLocale ? { ...item, releaseNotes: value } : item
      )
    );
  }

  return (
    <div className="workspace-content-grid">
      <section className="store-summary-strip">
        <span>当前商店最新版本：{workspace.version || '未确认'}</span>
        <span>{workspace.supportedLocales.length} 个语言</span>
        <span>{workspace.preflightLabel}</span>
        <button className="button" type="button" onClick={() => onSave(payload)} disabled={busy}>
          保存草稿
        </button>
        <button
          className="button"
          type="button"
          onClick={() => onCheck(payload, ['release_notes'])}
          disabled={busy}
        >
          实时查询
        </button>
        <button
          className="button primary"
          type="button"
          onClick={() => onSync(payload, ['release_notes'])}
          disabled={busy}
        >
          同步版本说明
        </button>
      </section>
      <EditableFieldCard
        title="版本说明"
        value={current?.releaseNotes || ''}
        placeholder="Release Notes"
        locales={rows}
        field="releaseNotes"
        onChange={updateReleaseNotes}
      />
    </div>
  );
}

function MarketingPagesPanel({
  workspace,
  busy,
  onNavigate,
  onCreate
}: {
  workspace: StoreWorkspaceState;
  busy: boolean;
  onNavigate: (path: string) => void;
  onCreate: (payload: MarketingPagePayload) => void;
}) {
  const [pageName, setPageName] = useState('新的自定义产品页面');
  const sourceLocale = workspace.sourceLocale || workspace.locale || workspace.supportedLocales[0] || 'en-US';

  function createPage(event: FormEvent) {
    event.preventDefault();
    onCreate({
      pageName,
      pageType: 'custom_product_page',
      deepLinkUrl: '',
      locale: sourceLocale,
      locales: workspace.supportedLocales.map((locale) => ({
        locale,
        promotionalText: locale === sourceLocale ? '' : '',
        storeImages: {}
      }))
    });
  }

  return (
    <div className="workspace-content-grid">
      <section className="store-summary-strip">
        <span>{workspace.marketingPages.length} 个营销页面</span>
        <span>{workspace.supportedLocales.length} 个语言</span>
        <span>{workspace.preflightLabel}</span>
      </section>
      <form className="marketing-create-row" onSubmit={createPage}>
        <label>
          <span>新建自定义产品页面</span>
          <input value={pageName} onChange={(event) => setPageName(event.target.value)} />
        </label>
        <button className="button primary" type="submit" disabled={busy || !pageName.trim()}>
          新建页面
        </button>
      </form>
      <div className="marketing-page-list">
        {workspace.marketingPages.map((page) => (
          <button
            key={page.id}
            className="marketing-page-row"
            type="button"
            onClick={() => onNavigate(page.detailPath)}
          >
            <span>
              <strong>{page.pageName}</strong>
              <small>{page.typeLabel} / {page.pageId}</small>
            </span>
            <span>{page.languageCount} 语言</span>
            <span>{page.assetCount} 张图</span>
            <span className={`tag ${page.status === 'synced' ? 'ok' : 'warn'}`}>
              {page.statusLabel}
            </span>
          </button>
        ))}
      </div>
      {!workspace.marketingPages.length ? (
        <div className="empty-state">还没有营销页面。</div>
      ) : null}
    </div>
  );
}

function MarketingPageDetailPanel({
  detail,
  busy,
  onBack,
  onSave,
  onCheck,
  onSync,
  onCopy,
  onDelete,
  onDeleteImage,
  onUploadImages
}: {
  detail: MarketingPageDetailState | null;
  busy: boolean;
  onBack: () => void;
  onSave: (payload: MarketingPagePayload) => void;
  onCheck: (payload: MarketingPagePayload) => void;
  onSync: (payload: MarketingPagePayload) => void;
  onCopy: () => void;
  onDelete: () => void;
  onDeleteImage: (payload: { locale: string; slotKey: string; storageKey: string }) => void;
  onUploadImages: (payload: StoreImageUploadRequest) => void;
}) {
  const [pageName, setPageName] = useState('');
  const [deepLinkUrl, setDeepLinkUrl] = useState('');
  const [rows, setRows] = useState<MarketingPageLocaleContent[]>([]);

  useEffect(() => {
    setPageName(detail?.page.pageName ?? '');
    setDeepLinkUrl(detail?.page.deepLinkUrl ?? '');
    setRows(detail?.localizedPage ?? []);
  }, [detail]);

  if (!detail) {
    return <div className="empty-state">正在加载营销页面...</div>;
  }

  const currentLocale = detail.locale || detail.sourceLocale || rows[0]?.locale || '';
  const current = rows.find((item) => item.locale === currentLocale) ?? rows[0] ?? null;
  const payload = marketingPayloadFromRows(detail, pageName, deepLinkUrl, rows);

  function updatePromotionalText(value: string) {
    setRows((currentRows) =>
      currentRows.map((item) =>
        item.locale === currentLocale ? { ...item, promotionalText: value } : item
      )
    );
  }

  return (
    <div className="workspace-content-grid">
      <section className="store-summary-strip">
        <button className="button" type="button" onClick={onBack}>
          返回营销页面
        </button>
        <span>{detail.page.typeLabel}</span>
        <span>Apple 页面 ID：{detail.page.applePageIdLabel}</span>
        <span>{detail.preflightLabel}</span>
        <button className="button" type="button" onClick={() => onSave(payload)} disabled={busy}>
          保存草稿
        </button>
        <button
          className="button"
          type="button"
          onClick={() => onCheck({ ...payload, syncScopes: ['marketing_text', 'store_images'] })}
          disabled={busy}
        >
          实时查询
        </button>
        <button
          className="button primary"
          type="button"
          onClick={() => onSync({ ...payload, syncScopes: ['marketing_text', 'store_images'] })}
          disabled={busy}
        >
          同步营销页
        </button>
      </section>

      <section className="field-card marketing-detail-fields">
        <header>
          <div>
            <strong>页面基础信息</strong>
            <span>中心后台草稿，不会自动同步到商店</span>
          </div>
          <div className="button-row">
            <button className="button" type="button" onClick={onCopy} disabled={busy}>
              复制页面
            </button>
            <button className="button danger" type="button" onClick={onDelete} disabled={busy}>
              删除页面
            </button>
          </div>
        </header>
        <div className="form-grid">
          <label>
            <span>页面名称</span>
            <input value={pageName} onChange={(event) => setPageName(event.target.value)} />
          </label>
          <label>
            <span>Deep Link URL</span>
            <input value={deepLinkUrl} onChange={(event) => setDeepLinkUrl(event.target.value)} />
          </label>
        </div>
      </section>

      <MarketingTextCard
        title="宣传文本"
        value={current?.promotionalText || ''}
        locales={rows}
        onChange={updatePromotionalText}
      />
      <MarketingImageOverview
        locales={rows}
        busy={busy}
        onDeleteImage={onDeleteImage}
        onUploadImages={onUploadImages}
      />
    </div>
  );
}

function MarketingTextCard({
  title,
  value,
  locales,
  onChange
}: {
  title: string;
  value: string;
  locales: MarketingPageLocaleContent[];
  onChange: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="field-card">
      <header>
        <div>
          <strong>{title}</strong>
          <span>{locales.length} 个语言</span>
        </div>
        <button className="button" type="button" onClick={() => setExpanded((current) => !current)}>
          {expanded ? '收起多语言' : '展开多语言'}
        </button>
      </header>
      <textarea
        value={value}
        placeholder="App Store Connect promotional text"
        onChange={(event) => onChange(event.target.value)}
      />
      {expanded ? (
        <div className="locale-content-list">
          {locales.map((locale) => (
            <div key={locale.locale} className="locale-content-row">
              <strong>{locale.locale}</strong>
              <span className={locale.isSource ? 'tag ok' : 'tag'}>
                {locale.isSource ? '源文案' : '翻译'}
              </span>
              <p>{locale.promotionalText || '未填写'}</p>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function MarketingImageOverview({
  locales,
  busy,
  onDeleteImage,
  onUploadImages
}: {
  locales: MarketingPageLocaleContent[];
  busy: boolean;
  onDeleteImage: (payload: { locale: string; slotKey: string; storageKey: string }) => void;
  onUploadImages: (payload: StoreImageUploadRequest) => void;
}) {
  return (
    <article className="field-card">
      <header>
        <div>
          <strong>营销页截图</strong>
          <span>{locales.length} 个语言</span>
        </div>
      </header>
      <div className="locale-content-list">
        {locales.map((locale) => {
          const assets = imageAssets(locale.storeImages);
          return (
            <div key={locale.locale} className="locale-content-row">
              <strong>{locale.locale}</strong>
              <span>{assets.length} 张</span>
              <ImageUploadActions
                locale={locale.locale}
                busy={busy}
                onUploadImages={onUploadImages}
              />
              <div className="store-image-assets">
                {assets.length ? (
                  assets.map((asset) => (
                    <div key={asset.storageKey} className="store-image-asset-row">
                      {asset.downloadUrl ? <img src={asset.downloadUrl} alt={`${locale.locale} 营销页截图`} /> : null}
                      <span>{asset.fileName || asset.storageKey}</span>
                      <button
                        className="button slim"
                        type="button"
                        onClick={() =>
                          onDeleteImage({
                            locale: locale.locale,
                            slotKey: asset.slotKey,
                            storageKey: asset.storageKey
                          })
                        }
                      >
                        删除
                      </button>
                    </div>
                  ))
                ) : (
                  <p>还没有上传图片</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function EditableFieldCard({
  title,
  value,
  locales,
  field,
  placeholder,
  onChange
}: {
  title: string;
  value: string;
  locales: StoreLocaleContent[];
  field: 'promotionalText' | 'description' | 'releaseNotes';
  placeholder: string;
  onChange: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="field-card">
      <header>
        <div>
          <strong>{title}</strong>
          <span>{locales.length} 个语言</span>
        </div>
        <button className="button" type="button" onClick={() => setExpanded((current) => !current)}>
          {expanded ? '收起多语言' : '展开多语言'}
        </button>
      </header>
      <textarea value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
      {expanded ? (
        <div className="locale-content-list">
          {locales.map((locale) => (
            <div key={locale.locale} className="locale-content-row">
              <strong>{locale.locale}</strong>
              <span className={locale.isSource ? 'tag ok' : 'tag'}>
                {locale.isSource ? '源文案' : '翻译'}
              </span>
              <p>{locale[field] || '未填写'}</p>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function ImageOverview({
  locales,
  busy,
  onDeleteImage,
  onUploadImages
}: {
  locales: StoreLocaleContent[];
  busy: boolean;
  onDeleteImage: (payload: { locale: string; slotKey: string; storageKey: string }) => void;
  onUploadImages: (payload: StoreImageUploadRequest) => void;
}) {
  return (
    <article className="field-card">
      <header>
        <div>
          <strong>商店图</strong>
          <span>{locales.length} 个语言</span>
        </div>
      </header>
      <div className="locale-content-list">
        {locales.map((locale) => {
          const assets = imageAssets(locale.storeImages);
          const count = assets.length;
          return (
            <div key={locale.locale} className="locale-content-row">
              <strong>{locale.locale}</strong>
              <span>{count} 张</span>
              <ImageUploadActions
                locale={locale.locale}
                busy={busy}
                onUploadImages={onUploadImages}
              />
              <div className="store-image-assets">
                {assets.length ? (
                  assets.map((asset) => (
                    <div key={asset.storageKey} className="store-image-asset-row">
                      {asset.downloadUrl ? <img src={asset.downloadUrl} alt={`${locale.locale} 商店图`} /> : null}
                      <span>{asset.fileName || asset.storageKey}</span>
                      <button
                        className="button slim"
                        type="button"
                        onClick={() =>
                          onDeleteImage({
                            locale: locale.locale,
                            slotKey: asset.slotKey,
                            storageKey: asset.storageKey
                          })
                        }
                      >
                        删除
                      </button>
                    </div>
                  ))
                ) : (
                  <p>还没有上传图片</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function ImageUploadActions({
  locale,
  busy,
  onUploadImages
}: {
  locale: string;
  busy: boolean;
  onUploadImages: (payload: StoreImageUploadRequest) => void;
}) {
  function selectFiles(slotKey: string, files: FileList | null) {
    const selected = Array.from(files ?? []);
    if (selected.length === 0) return;
    onUploadImages({ locale, slotKey, files: selected });
  }

  return (
    <div className="store-image-upload-actions">
      <label className={busy ? 'button slim disabled' : 'button slim'}>
        手机截图
        <input
          type="file"
          multiple
          accept="image/png,image/jpeg"
          disabled={busy}
          onChange={(event) => {
            selectFiles('phone_screenshots', event.currentTarget.files);
            event.currentTarget.value = '';
          }}
        />
      </label>
      <label className={busy ? 'button slim disabled' : 'button slim'}>
        平板截图
        <input
          type="file"
          multiple
          accept="image/png,image/jpeg"
          disabled={busy}
          onChange={(event) => {
            selectFiles('tablet_screenshots', event.currentTarget.files);
            event.currentTarget.value = '';
          }}
        />
      </label>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="account-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function parseAccountRoute(pathname: string): AccountRoute {
  const parts = pathname.replace(/^\/admin\/?/, '').split('/').filter(Boolean);
  if (parts[0] !== 'accounts') return { kind: 'list' };
  if (!parts[1]) return { kind: 'list' };
  if (parts[1] === 'new') return { kind: 'new' };
  if (parts[2] === 'edit') return { kind: 'edit', accountId: parts[1] };
  if (parts[2] === 'apps' && parts[3]) {
    if (parts[4] === 'marketing-pages' && parts[5]) {
      return {
        kind: 'app',
        accountId: parts[1],
        appId: parts[3],
        section: 'marketing',
        pageId: parts[5]
      };
    }
    const section = isStoreSection(parts[4]) ? parts[4] : 'store';
    return { kind: 'app', accountId: parts[1], appId: parts[3], section };
  }
  return { kind: 'detail', accountId: parts[1] };
}

function isStoreSection(value: string | undefined): value is StoreSection {
  return value === 'store' || value === 'marketing' || value === 'release-notes' || value === 'connection';
}

function toDateTimeInput(value: string) {
  if (!value) return '';
  return value.slice(0, 16);
}

function serializeStoreRows(rows: StoreLocaleContent[]): StoreLocaleContentInput[] {
  return rows.map((item) => ({
    locale: item.locale,
    promotionalText: item.promotionalText,
    description: item.description,
    releaseNotes: item.releaseNotes,
    storeImages: item.storeImages
  }));
}

function marketingPayloadFromRows(
  detail: MarketingPageDetailState,
  pageName: string,
  deepLinkUrl: string,
  rows: MarketingPageLocaleContent[]
): MarketingPagePayload {
  return {
    pageId: detail.page.pageId,
    pageName,
    pageType: detail.page.pageType,
    deepLinkUrl,
    locale: detail.locale || detail.sourceLocale,
    locales: serializeMarketingRows(rows)
  };
}

function serializeMarketingRows(rows: MarketingPageLocaleContent[]): MarketingPageLocaleInput[] {
  return rows.map((item) => ({
    locale: item.locale,
    promotionalText: item.promotionalText,
    storeImages: item.storeImages
  }));
}

function storeImageFormData(payload: StoreImageUploadRequest): FormData {
  const formData = new FormData();
  payload.files.forEach((file) => {
    formData.append(`storeImageFiles__${payload.slotKey}__${payload.locale}`, file);
  });
  return formData;
}

function imageAssets(storeImages: Record<string, unknown>): Array<{
  slotKey: string;
  storageKey: string;
  downloadUrl: string;
  fileName: string;
}> {
  const assets: Array<{
    slotKey: string;
    storageKey: string;
    downloadUrl: string;
    fileName: string;
  }> = [];
  Object.entries(storeImages).forEach(([slotKey, value]) => {
    if (!value || typeof value !== 'object') return;
    const rawAssets = (value as { assets?: unknown }).assets;
    if (!Array.isArray(rawAssets)) return;
    rawAssets.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const asset = item as {
        storageKey?: unknown;
        downloadUrl?: unknown;
        fileName?: unknown;
      };
      const storageKey = typeof asset.storageKey === 'string' ? asset.storageKey : '';
      if (!storageKey) return;
      assets.push({
        slotKey,
        storageKey,
        downloadUrl: typeof asset.downloadUrl === 'string' ? asset.downloadUrl : '',
        fileName: typeof asset.fileName === 'string' ? asset.fileName : ''
      });
    });
  });
  return assets;
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
