import { useEffect, useMemo, useState } from 'react';
import {
  AdminApiError,
  analyzeStoreReviews,
  fetchStoreReviews,
  loadStoreReviews,
  type ReviewAppItem,
  type StoreReviewsState
} from '../app/apiClient';

const ratingFilters = [
  { label: '全部', value: null },
  { label: '1 星', value: 1 },
  { label: '2 星', value: 2 },
  { label: '3 星', value: 3 }
];

type LoadingAction = 'idle' | 'load' | 'fetch' | 'analyze';

export function StoreReviewsPage() {
  const [state, setState] = useState<StoreReviewsState | null>(null);
  const [loading, setLoading] = useState<LoadingAction>('load');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const selectedApp = useMemo(
    () => state?.apps.find((app) => app.selected) ?? null,
    [state]
  );

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
      const query = location.search || '';
      setState(await loadStoreReviews(query));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading('idle');
    }
  }

  async function selectApp(app: ReviewAppItem) {
    const nextPath = reviewPath({ accountId: app.accountId, appId: app.appId, rating: null });
    history.pushState({ adminRoute: 'store-reviews', accountId: app.accountId, appId: app.appId }, '', nextPath);
    await loadFromLocation();
  }

  async function selectRating(rating: number | null) {
    if (!state?.selectedAccountId || !state.selectedAppId) return;
    const nextPath = reviewPath({
      accountId: state.selectedAccountId,
      appId: state.selectedAppId,
      rating
    });
    history.pushState({ adminRoute: 'store-reviews', rating }, '', nextPath);
    await loadFromLocation();
  }

  async function runFetch() {
    if (!state?.selectedAccountId || !state.selectedAppId) return;
    setLoading('fetch');
    setError('');
    setNotice('');
    try {
      const response = await fetchStoreReviews(state.selectedAccountId, state.selectedAppId);
      setState(response.state);
      setNotice(`${response.message}：新增 ${response.state.latestFetch?.insertedCount ?? 0} 条`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading('idle');
    }
  }

  async function runAnalyze() {
    if (!state?.selectedAccountId || !state.selectedAppId) return;
    setLoading('analyze');
    setError('');
    setNotice('');
    try {
      const response = await analyzeStoreReviews(state.selectedAccountId, state.selectedAppId);
      setState(response.state);
      if (response.error) {
        setError(response.error.message);
      } else {
        setNotice(response.message);
      }
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading('idle');
    }
  }

  return (
    <div className="reviews-workspace" data-store-reviews-page>
      <aside className="panel review-apps-panel">
        <div className="panel-head compact">
          <strong>商店应用</strong>
          <span>{state?.apps.length ?? 0} 个</span>
        </div>
        <div className="review-apps-list">
          {state?.apps.map((app) => (
            <button
              key={`${app.accountId}:${app.appId}`}
              className={app.selected ? 'review-app-row active' : 'review-app-row'}
              type="button"
              onClick={() => void selectApp(app)}
            >
              <span className="app-avatar" style={{ backgroundColor: app.iconColor }}>
                {app.appName.slice(0, 2).toUpperCase()}
              </span>
              <span className="review-app-copy">
                <strong>{app.appName}</strong>
                <small>{app.bundleIdentifier}</small>
                <small>{app.platform} · {app.accountName}</small>
              </span>
              <em>{app.reviewCount}</em>
            </button>
          ))}
          {state && state.apps.length === 0 ? (
            <div className="empty-state">还没有绑定开发者账号的应用。</div>
          ) : null}
        </div>
      </aside>

      <section className="panel review-stream-panel">
        <div className="review-page-toolbar">
          <div>
            <strong>{selectedApp ? `${selectedApp.appName} 评论` : '评论'}</strong>
            <span>空库只拉 20 条；有历史后遇到已存在同创建日评论就停止。</span>
          </div>
          <div className="review-actions">
            <button className="button" type="button" onClick={() => void runFetch()} disabled={!selectedApp || loading !== 'idle'}>
              {loading === 'fetch' ? '拉取中' : '拉取最新评论'}
            </button>
            <button className="button primary" type="button" onClick={() => void runAnalyze()} disabled={!selectedApp || loading !== 'idle'}>
              {loading === 'analyze' ? '分析中' : 'LLM 分析'}
            </button>
          </div>
        </div>

        {notice ? <div className="notice ok">{notice}</div> : null}
        {error ? <div className="notice error">{error}</div> : null}

        <div className="review-summary">
          <Metric label="本地评论" value={state?.stats.total ?? 0} />
          <Metric label="低分需关注" value={state?.stats.low ?? 0} />
          <Metric label="iOS" value={state?.stats.ios ?? 0} />
          <Metric label="Android" value={state?.stats.android ?? 0} />
        </div>

        <div className="review-filter-row">
          {ratingFilters.map((filter) => (
            <button
              key={filter.label}
              className={state?.rating === filter.value ? 'filter-pill active' : 'filter-pill'}
              type="button"
              onClick={() => void selectRating(filter.value)}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="review-list">
          {loading === 'load' ? <div className="empty-state">正在加载评论...</div> : null}
          {state?.reviews.map((review) => (
            <article className="review-card" key={review.id}>
              <header>
                <strong>{review.title || '无标题评论'}</strong>
                <span>{review.rating ?? '-'} 星</span>
              </header>
              <p>{review.body || '暂无评论内容'}</p>
              <footer>
                <span>{review.locale || '未知语言'}</span>
                <span>{review.appVersion || '未知版本'}</span>
                <span>{formatDate(review.createdAt)}</span>
                <span>{review.authorName || '匿名用户'}</span>
              </footer>
            </article>
          ))}
          {state && state.reviews.length === 0 && loading !== 'load' ? (
            <div className="empty-state">还没有匹配的本地评论。</div>
          ) : null}
        </div>
      </section>

      <aside className="panel review-analysis-panel">
        <div className="panel-head compact">
          <strong>LLM 分析</strong>
          <span>{state?.latestAnalysis?.status === 'succeeded' ? '已完成' : '未完成'}</span>
        </div>
        {state?.latestAnalysis?.status === 'succeeded' ? (
          <>
            <p className="analysis-summary">{state.latestAnalysis.summary}</p>
            <div className="issue-list">
              {state.analysisIssues.map((issue) => (
                <article className="issue-card" key={`${issue.title}:${issue.severity}`}>
                  <strong>{issue.title}</strong>
                  <span>{issue.focus}</span>
                  <em>{issue.severity}</em>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-state">拉取评论后运行 LLM 分析。</div>
        )}
        <ul className="boundary-list">
          {state?.analysisBoundaries.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </aside>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="review-metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function reviewPath({
  accountId,
  appId,
  rating
}: {
  accountId: string;
  appId: string;
  rating: number | null;
}) {
  const params = new URLSearchParams({ accountId, appId });
  if (rating) params.set('rating', String(rating));
  return `/admin-next/store-reviews?${params.toString()}`;
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}
