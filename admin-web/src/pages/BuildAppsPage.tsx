import { useEffect, useMemo, useState } from 'react';
import {
  AdminApiError,
  createAgentBuild,
  loadBuildAppsState,
  type BuildAppItem,
  type BuildAppsState,
  type BuildEnvironmentOption,
  type BuildItem
} from '../app/apiClient';

export function BuildAppsPage() {
  const [state, setState] = useState<BuildAppsState | null>(null);
  const [selectedAppId, setSelectedAppId] = useState('');
  const [environment, setEnvironment] = useState('');
  const [gitRef, setGitRef] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [createdBuild, setCreatedBuild] = useState<BuildItem | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    loadBuildAppsState()
      .then((payload) => {
        if (!cancelled) setState(payload);
      })
      .catch((requestError) => {
        if (!cancelled) setError(errorMessage(requestError));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedApp = useMemo(
    () => state?.apps.find((item) => item.app.id === selectedAppId) ?? null,
    [selectedAppId, state]
  );
  const selectedEnvironment = useMemo(
    () => selectedApp?.environments.find((item) => item.environment === environment) ?? null,
    [environment, selectedApp]
  );

  function selectApp(item: BuildAppItem) {
    const firstEnvironment = item.environments[0];
    setSelectedAppId(item.app.id);
    setEnvironment(firstEnvironment?.environment ?? '');
    setGitRef(defaultGitRef(firstEnvironment));
    setCreatedBuild(null);
    setMessage('');
    setError('');
  }

  function selectEnvironment(value: string) {
    const option = selectedApp?.environments.find((item) => item.environment === value) ?? null;
    setEnvironment(value);
    setGitRef(defaultGitRef(option));
    setCreatedBuild(null);
    setMessage('');
    setError('');
  }

  async function submitBuild() {
    if (!selectedApp || !selectedEnvironment || !gitRef.trim()) return;
    setSubmitting(true);
    setMessage('');
    setError('');
    try {
      const setting = selectedEnvironment.setting;
      const response = await createAgentBuild(selectedApp.app.id, {
        environment: selectedEnvironment.environment,
        gitUrl: setting.gitUrl,
        gitRef: gitRef.trim(),
        repoSubpath: setting.repoSubpath,
        runnerLabels: setting.runnerLabels,
        credentialRefs: setting.credentialRefs,
        artifactType: setting.artifactType
      });
      setCreatedBuild(response.build);
      setMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  function openApps() {
    history.pushState({ adminRoute: 'apps' }, '', '/admin/apps');
  }

  function openBuildHistory() {
    history.pushState({ adminRoute: 'builds' }, '', '/admin/builds/history');
  }

  if (!state && !error) {
    return <div className="empty-state">正在加载构建应用...</div>;
  }

  if (state && state.apps.length === 0) {
    return (
      <section className="panel workspace-empty-state">
        <h2>还没有接入构建的应用</h2>
        <p>先在应用详情中配置开发环境或线上环境的构建设置。</p>
        <button className="button primary" type="button" onClick={openApps}>
          前往应用
        </button>
      </section>
    );
  }

  return (
    <div className="build-apps-layout" data-build-apps-page>
      <section className="panel build-app-list-panel">
        <div className="panel-head compact">
          <div>
            <strong>已接入应用</strong>
            <span>{state?.total ?? 0} 个应用</span>
          </div>
        </div>
        <div className="build-app-list">
          {(state?.apps ?? []).map((item) => (
            <button
              key={item.app.id}
              className={item.app.id === selectedAppId ? 'build-app-option active' : 'build-app-option'}
              type="button"
              onClick={() => selectApp(item)}
            >
              <span className="app-avatar" style={{ backgroundColor: item.app.iconColor }}>
                {item.app.iconText}
              </span>
              <span className="build-app-option-copy">
                <strong>{item.app.name}</strong>
                <small>{item.app.bundleIdentifier}</small>
                <small>{item.environments.map((option) => option.environmentLabel).join(' · ')}</small>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel build-form-panel">
        {error ? <div className="notice error">{error}</div> : null}
        {!selectedApp ? (
          <div className="workspace-selection-empty">
            <h2>选择应用开始构建</h2>
            <p>只展示已经完成构建配置的应用。</p>
          </div>
        ) : (
          <>
            <div className="panel-head compact">
              <div>
                <strong>{selectedApp.app.name}</strong>
                <span>{selectedApp.app.bundleIdentifier}</span>
              </div>
              <span className="tag">{selectedApp.app.platform.toUpperCase()}</span>
            </div>
            <div className="form-grid two build-create-form">
              <label>
                <span>构建环境</span>
                <select value={environment} onChange={(event) => selectEnvironment(event.target.value)}>
                  {selectedApp.environments.map((option) => (
                    <option key={option.environment} value={option.environment}>
                      {option.environmentLabel}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Git ref</span>
                <input value={gitRef} onChange={(event) => setGitRef(event.target.value)} placeholder="main" />
              </label>
            </div>
            {selectedEnvironment ? (
              <dl className="build-setting-summary">
                <div>
                  <dt>Git 仓库</dt>
                  <dd>{selectedEnvironment.setting.gitUrl}</dd>
                </div>
                <div>
                  <dt>Runner 标签</dt>
                  <dd>{selectedEnvironment.setting.runnerLabels.join(', ') || '无标签要求'}</dd>
                </div>
                <div>
                  <dt>产物类型</dt>
                  <dd>{selectedEnvironment.setting.artifactType}</dd>
                </div>
                <div>
                  <dt>匹配节点</dt>
                  <dd>{selectedEnvironment.matchingRunnerCount} 个在线节点</dd>
                </div>
              </dl>
            ) : null}
            {selectedEnvironment && !selectedEnvironment.hasOnlineRunner ? (
              <div className="notice warning compact-notice">当前无匹配在线节点</div>
            ) : null}
            {message ? (
              <div className="notice ok build-created-notice">
                <div>
                  <strong>{message}</strong>
                  {createdBuild ? (
                    <span>
                      {createdBuild.id} · {createdBuild.lifecycleStatusLabel || createdBuild.status}
                    </span>
                  ) : null}
                </div>
                <button className="button slim" type="button" onClick={openBuildHistory}>
                  查看构建记录
                </button>
              </div>
            ) : null}
            <div className="form-actions">
              <button
                className="button primary"
                type="button"
                disabled={submitting || !selectedEnvironment || !gitRef.trim()}
                onClick={submitBuild}
              >
                {submitting ? '正在创建...' : '立即构建'}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function defaultGitRef(option: BuildEnvironmentOption | null | undefined): string {
  const value = option?.setting.optionalDefaults.gitRef;
  return typeof value === 'string' && value.trim() ? value.trim() : 'main';
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
