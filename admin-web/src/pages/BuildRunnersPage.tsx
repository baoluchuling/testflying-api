import { useEffect, useState } from 'react';
import {
  AdminApiError,
  loadBuildRunnersState,
  type BuildRunnerItem,
  type BuildRunnersState
} from '../app/apiClient';

export function BuildRunnersPage() {
  const [state, setState] = useState<BuildRunnersState | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    loadBuildRunnersState()
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

  return (
    <section className="panel table-panel" data-build-runners-page>
      <div className="panel-head">
        <strong>构建节点</strong>
        <span>{state?.total ?? 0} 个节点</span>
      </div>
      {error ? <div className="notice error">{error}</div> : null}
      <div className="data-table builds-runners-table" role="table" aria-label="构建节点列表">
        <div className="data-table-row header" role="row">
          <span>节点</span>
          <span>标签</span>
          <span>版本</span>
          <span>能力</span>
          <span>最近心跳</span>
          <span>当前构建</span>
        </div>
        {(state?.runners ?? []).map((runner) => (
          <BuildRunnerRow key={runner.id} runner={runner} />
        ))}
      </div>
      {!state && !error ? <div className="empty-state">正在加载构建节点...</div> : null}
      {state && state.runners.length === 0 ? <div className="empty-state">暂无构建节点。</div> : null}
    </section>
  );
}

function BuildRunnerRow({ runner }: { runner: BuildRunnerItem }) {
  const platforms = valueList(runner.capabilities.platforms);
  const llmAdapters = valueList(runner.capabilities.llmAdapters);
  const statusTone = runner.status === 'online' ? 'ok' : runner.status === 'busy' ? 'warn' : 'danger';

  return (
    <div className="data-table-row build-runner-row" role="row">
      <span>
        <strong>{runner.name}</strong>
        <small>{runner.id}</small>
        <span className={`tag ${statusTone}`}>{runner.status}</span>
      </span>
      <span>{runner.labels.join(', ') || '-'}</span>
      <span>
        <strong>{runner.version || '-'}</strong>
        <small>package-agent {runner.packageAgentVersion || '-'}</small>
      </span>
      <span>
        <strong>{platforms.join(', ') || '-'}</strong>
        <small>LLM: {llmAdapters.join(', ') || '-'}</small>
      </span>
      <span>{runner.lastSeenAtLabel}</span>
      <span>{runner.currentBuildId || '-'}</span>
    </div>
  );
}

function valueList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
