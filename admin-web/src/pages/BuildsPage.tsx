import { useEffect, useState } from 'react';
import {
  AdminApiError,
  loadBuildsState,
  type BuildItem,
  type BuildsState
} from '../app/apiClient';

export function BuildsPage() {
  const [state, setState] = useState<BuildsState | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');

  useEffect(() => {
    let cancelled = false;
    loadBuildsState()
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

  async function copy(label: string, value: string) {
    if (!value) return;
    await navigator.clipboard?.writeText(value);
    setCopied(label);
  }

  return (
    <section className="panel table-panel" data-builds-page>
      <div className="panel-head">
        <strong>构建列表</strong>
        <span>{state?.total ?? 0} 个构建</span>
      </div>
      {error ? <div className="notice error">{error}</div> : null}
      {copied ? <div className="notice ok">已复制 {copied}</div> : null}
      <div className="data-table builds-table" role="table" aria-label="构建列表">
        <div className="data-table-row header" role="row">
          <span>应用</span>
          <span>版本</span>
          <span>平台</span>
          <span>环境</span>
          <span>大小</span>
          <span>操作</span>
        </div>
        {(state?.builds ?? []).map((build) => (
          <BuildRow key={build.id} build={build} onCopy={copy} />
        ))}
      </div>
      {!state && !error ? <div className="empty-state">正在加载构建...</div> : null}
      {state && state.builds.length === 0 ? <div className="empty-state">暂无构建。</div> : null}
    </section>
  );
}

function BuildRow({
  build,
  onCopy
}: {
  build: BuildItem;
  onCopy: (label: string, value: string) => Promise<void>;
}) {
  return (
    <div className="data-table-row build-row" role="row">
      <span className="app-cell">
        <span className="app-avatar" style={{ backgroundColor: build.app.iconColor }}>
          {build.app.iconText}
        </span>
        <span>
          <strong>{build.app.name}</strong>
          <small>{build.app.bundleIdentifier}</small>
        </span>
      </span>
      <span>
        <strong>{build.version}</strong>
        <small>build {build.buildNumber}</small>
      </span>
      <span>{build.platformLabel}</span>
      <span>{build.environmentLabel}</span>
      <span>{build.artifact?.sizeLabel ?? '-'}</span>
      <span className="inline-actions">
        <button
          type="button"
          className="button"
          disabled={!build.artifact?.installUrl}
          onClick={() => onCopy('installUrl', build.artifact?.installUrl ?? '')}
        >
          复制安装
        </button>
        <button
          type="button"
          className="button"
          disabled={!build.artifact?.downloadUrl}
          onClick={() => onCopy('downloadUrl', build.artifact?.downloadUrl ?? '')}
        >
          下载地址
        </button>
      </span>
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
