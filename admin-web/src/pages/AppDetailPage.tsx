import { useEffect, useMemo, useState } from 'react';
import {
  AdminApiError,
  createAgentBuild,
  loadAppDetailState,
  saveAppBuildSettings,
  type AppDetailState,
  type BuildItem,
  type BuildArtifact,
  type BuildSettingItem
} from '../app/apiClient';

type BuildEnvironment = 'development' | 'production';
type SettingDraft = {
  gitUrl: string;
  repoSubpath: string;
  runnerLabels: string;
  credentialRefs: string;
  artifactType: string;
};

export function AppDetailPage({ appId }: { appId: string }) {
  const [state, setState] = useState<AppDetailState | null>(null);
  const [environment, setEnvironment] = useState<BuildEnvironment>('development');
  const [gitRef, setGitRef] = useState('main');
  const [drafts, setDrafts] = useState<Record<BuildEnvironment, SettingDraft>>(() => ({
    development: emptyDraft(),
    production: emptyDraft()
  }));
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [savingEnvironment, setSavingEnvironment] = useState<BuildEnvironment | ''>('');

  useEffect(() => {
    let cancelled = false;
    setState(null);
    setMessage('');
    setError('');
    loadAppDetailState(appId)
      .then((payload) => {
        if (cancelled) return;
        setState(payload);
        const nextEnvironment = payload.settings.development ? 'development' : 'production';
        setEnvironment(nextEnvironment);
        setGitRef(payload.builds[0]?.gitRef || 'main');
        setDrafts({
          development: settingToDraft(payload.settings.development),
          production: settingToDraft(payload.settings.production)
        });
      })
      .catch((requestError) => {
        if (!cancelled) setError(errorMessage(requestError));
      });
    return () => {
      cancelled = true;
    };
  }, [appId]);

  const selectedSetting = useMemo(() => {
    if (!state) return null;
    return environment === 'development' ? state.settings.development : state.settings.production;
  }, [environment, state]);

  function updateDraft(environmentKey: BuildEnvironment, patch: Partial<SettingDraft>) {
    setDrafts((current) => ({
      ...current,
      [environmentKey]: {
        ...current[environmentKey],
        ...patch
      }
    }));
  }

  async function submitBuild() {
    if (!state || !selectedSetting) {
      setError('请先保存该环境的构建配置。');
      return;
    }
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const response = await createAgentBuild(state.app.id, {
        environment,
        gitUrl: selectedSetting.gitUrl,
        gitRef: gitRef.trim() || 'main',
        repoSubpath: selectedSetting.repoSubpath,
        runnerLabels: selectedSetting.runnerLabels,
        credentialRefs: selectedSetting.credentialRefs,
        artifactType: selectedSetting.artifactType
      });
      setState(response.state);
      setMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveSettings(environmentKey: BuildEnvironment) {
    if (!state) return;
    setSavingEnvironment(environmentKey);
    setError('');
    setMessage('');
    try {
      const draft = drafts[environmentKey];
      const environmentSetting =
        environmentKey === 'development' ? state.settings.development : state.settings.production;
      const response = await saveAppBuildSettings(state.app.id, environmentKey, {
        gitUrl: draft.gitUrl.trim(),
        repoSubpath: draft.repoSubpath.trim(),
        runnerLabels: splitList(draft.runnerLabels),
        credentialRefs: parseCredentialRefs(draft.credentialRefs),
        artifactType: draft.artifactType.trim(),
        optionalDefaults: environmentSetting?.optionalDefaults ?? {}
      });
      setState(response.state);
      setDrafts({
        development: settingToDraft(response.state.settings.development),
        production: settingToDraft(response.state.settings.production)
      });
      setMessage(response.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSavingEnvironment('');
    }
  }

  if (error && !state) return <section className="notice error">{error}</section>;
  if (!state) return <section className="empty-state">正在加载应用...</section>;

  return (
    <div className="app-detail-page" data-app-detail-page>
      <section className="panel app-detail-overview">
        <div className="app-detail-header">
          <span className="app-avatar" style={{ backgroundColor: state.app.iconColor }}>
            {state.app.iconText}
          </span>
          <div className="app-detail-copy">
            <h2>{state.app.name}</h2>
            <p>{state.app.bundleIdentifier}</p>
            <div className="meta-line">
              <span>{state.app.platform.toUpperCase()}</span>
              <span>{state.builds.length} 条构建</span>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="notice error">{error}</div> : null}
      {message ? <div className="notice ok">{message}</div> : null}

      <div className="app-detail-grid">
        <section className="panel quick-build-panel">
          <div className="panel-head">
            <strong>快速构建</strong>
            <span>{selectedSetting ? selectedSetting.updatedAtLabel : '未配置'}</span>
          </div>
          <div className="form-grid two">
            <label>
              环境
              <select
                value={environment}
                onChange={(event) => setEnvironment(event.target.value as BuildEnvironment)}
              >
                <option value="development">测试</option>
                <option value="production">线上</option>
              </select>
            </label>
            <label>
              Git ref
              <input
                aria-label="Git ref"
                value={gitRef}
                onChange={(event) => setGitRef(event.target.value)}
                placeholder="main"
              />
            </label>
          </div>
          {selectedSetting ? (
            <dl className="detail-list compact">
              <div>
                <dt>Git URL</dt>
                <dd>{selectedSetting.gitUrl}</dd>
              </div>
              <div>
                <dt>子目录</dt>
                <dd>{selectedSetting.repoSubpath || '/'}</dd>
              </div>
              <div>
                <dt>Runner Labels</dt>
                <dd>{selectedSetting.runnerLabels.join(', ') || '-'}</dd>
              </div>
              <div>
                <dt>产物类型</dt>
                <dd>{selectedSetting.artifactType}</dd>
              </div>
            </dl>
          ) : (
            <div className="empty-state inline">该环境尚未配置构建设置。</div>
          )}
          <div className="form-actions align-start">
            <button
              type="button"
              className="button primary"
              disabled={!selectedSetting || submitting}
              onClick={() => void submitBuild()}
            >
              {submitting ? '提交中' : '立即构建'}
            </button>
          </div>
        </section>

        <section className="panel app-settings-panel">
          <div className="panel-head">
            <strong>构建设置</strong>
            <span>仅显示 credential ref，不展示原始密钥</span>
          </div>
          <div className="settings-grid">
            <BuildSettingCard
              label="测试环境"
              tone="development"
              setting={state.settings.development}
              draft={drafts.development}
              saving={savingEnvironment === 'development'}
              onChange={(patch) => updateDraft('development', patch)}
              onSave={() => void saveSettings('development')}
            />
            <BuildSettingCard
              label="线上环境"
              tone="production"
              setting={state.settings.production}
              draft={drafts.production}
              saving={savingEnvironment === 'production'}
              onChange={(patch) => updateDraft('production', patch)}
              onSave={() => void saveSettings('production')}
            />
          </div>
        </section>
      </div>

      <section className="panel build-history-panel">
        <div className="panel-head">
          <strong>构建历史</strong>
          <span>{state.builds.length} 条</span>
        </div>
        <div className="build-history-list">
          {state.builds.map((build) => (
            <BuildHistoryRow key={build.id} build={build} />
          ))}
        </div>
        {state.builds.length === 0 ? <div className="empty-state inline">暂无构建。</div> : null}
      </section>
    </div>
  );
}

function BuildSettingCard({
  label,
  setting,
  tone,
  draft,
  saving,
  onChange,
  onSave
}: {
  label: string;
  setting: BuildSettingItem | null;
  tone: 'development' | 'production';
  draft: SettingDraft;
  saving: boolean;
  onChange: (patch: Partial<SettingDraft>) => void;
  onSave: () => void;
}) {
  return (
    <section className={`setting-card ${tone}`}>
      <div className="setting-card-head">
        <strong>{label}</strong>
        <span>{setting?.updatedAtLabel || '未配置'}</span>
      </div>
      <div className="form-grid two">
        <label>
          Git URL
          <input value={draft.gitUrl} onChange={(event) => onChange({ gitUrl: event.target.value })} />
        </label>
        <label>
          Artifact Type
          <input
            value={draft.artifactType}
            onChange={(event) => onChange({ artifactType: event.target.value })}
          />
        </label>
        <label>
          Repo Subpath
          <input
            value={draft.repoSubpath}
            onChange={(event) => onChange({ repoSubpath: event.target.value })}
            placeholder="/"
          />
        </label>
        <label>
          Runner Labels
          <input
            value={draft.runnerLabels}
            onChange={(event) => onChange({ runnerLabels: event.target.value })}
            placeholder="ios-release, mac-sign"
          />
        </label>
        <label className="setting-card-full">
          Credential Refs
          <input
            value={draft.credentialRefs}
            onChange={(event) => onChange({ credentialRefs: event.target.value })}
            placeholder="git: git-main, signing: ios-signing"
          />
        </label>
      </div>
      <div className="setting-card-meta">
        <small>当前 refs：{setting ? credentialRefsLabel(setting.credentialRefs) : '-'}</small>
      </div>
      <div className="form-actions align-start">
        <button type="button" className="button" disabled={saving} onClick={onSave}>
          {saving ? '保存中' : '保存设置'}
        </button>
      </div>
    </section>
  );
}

function BuildHistoryRow({ build }: { build: BuildItem }) {
  const artifacts = buildArtifacts(build);

  return (
    <div className="build-history-row">
      <div>
        <strong>{build.version || '待解析'}</strong>
        <small>build {build.buildNumber || '-'}</small>
      </div>
      <div>
        <span>{build.environmentLabel}</span>
        <small>{build.sourceLabel || build.source || '-'}</small>
      </div>
      <div>
        <span>{build.lifecycleStatusLabel || build.lifecycleStatus || build.status}</span>
        <small>{build.uploadedAtLabel}</small>
      </div>
      <div>
        <span>{build.gitRef || '-'}</span>
        <small>{artifacts.length ? `${artifacts.length} 个产物` : '无产物'}</small>
      </div>
    </div>
  );
}

function buildArtifacts(build: BuildItem): BuildArtifact[] {
  if (build.artifacts?.length) return build.artifacts;
  return build.artifact ? [build.artifact] : [];
}

function credentialRefsLabel(credentialRefs: Record<string, string>): string {
  const entries = Object.entries(credentialRefs);
  if (entries.length === 0) return '-';
  return entries.map(([key, value]) => `${key}: ${value}`).join(', ');
}

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseCredentialRefs(value: string): Record<string, string> {
  const refs: Record<string, string> = {};
  for (const item of value.split(',')) {
    const normalized = item.trim();
    if (!normalized) continue;
    const separatorIndex = normalized.indexOf(':');
    if (separatorIndex < 0) {
      refs[normalized] = normalized;
      continue;
    }
    const key = normalized.slice(0, separatorIndex).trim();
    const refValue = normalized.slice(separatorIndex + 1).trim();
    if (key && refValue) refs[key] = refValue;
  }
  return refs;
}

function settingToDraft(setting: BuildSettingItem | null): SettingDraft {
  if (!setting) return emptyDraft();
  return {
    gitUrl: setting.gitUrl,
    repoSubpath: setting.repoSubpath,
    runnerLabels: setting.runnerLabels.join(', '),
    credentialRefs: credentialRefsLabel(setting.credentialRefs) === '-' ? '' : credentialRefsLabel(setting.credentialRefs),
    artifactType: setting.artifactType
  };
}

function emptyDraft(): SettingDraft {
  return {
    gitUrl: '',
    repoSubpath: '',
    runnerLabels: '',
    credentialRefs: '',
    artifactType: ''
  };
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
