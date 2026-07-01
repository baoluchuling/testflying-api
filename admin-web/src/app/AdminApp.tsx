import { useEffect, useMemo, useState } from 'react';
import { bootstrapAdmin, type BootstrapResponse } from './apiClient';
import { routeKeyFromPath, routeTitles, type AdminRouteKey } from './routes';
import { StoreAppsPage } from '../pages/StoreAppsPage';
import { StoreReviewsPage } from '../pages/StoreReviewsPage';

const fallbackNav = [
  { key: 'dashboard', label: '总览', path: '/admin-next' },
  { key: 'uploads', label: '上传', path: '/admin-next/uploads' },
  { key: 'apps', label: '商店管理', path: '/admin-next/apps' },
  { key: 'store-reviews', label: '商店评论', path: '/admin-next/store-reviews' },
  { key: 'api-docs', label: '接口文档', path: '/admin-next/api-docs' },
  { key: 'builds', label: '构建', path: '/admin-next/builds' },
  { key: 'devices', label: '设备', path: '/admin-next/devices' },
  { key: 'app-logs', label: 'App 日志', path: '/admin-next/app-logs' },
  { key: 'notifications', label: '通知', path: '/admin-next/notifications' }
] as const;

type HealthState = BootstrapResponse['health'] & { checking?: boolean };

export function AdminApp() {
  const [activeRoute, setActiveRoute] = useState<AdminRouteKey>(() => routeKeyFromPath(location.pathname));
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [health, setHealth] = useState<HealthState>({ state: 'idle', label: '未检查' });
  const [error, setError] = useState('');

  useEffect(() => {
    bootstrapAdmin()
      .then((payload) => {
        setBootstrap(payload);
        setHealth(payload.health);
      })
      .catch((requestError: Error) => setError(requestError.message));
  }, []);

  useEffect(() => {
    const onPopState = () => setActiveRoute(routeKeyFromPath(location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navItems = bootstrap?.navItems ?? fallbackNav;
  const title = useMemo(() => routeTitles[activeRoute], [activeRoute]);

  function navigate(path: string, key: AdminRouteKey) {
    if (location.pathname !== path) {
      history.pushState({ adminRoute: key }, '', path);
    }
    setActiveRoute(key);
  }

  async function checkHealth() {
    setHealth((current) => ({ ...current, checking: true, label: '检查中' }));
    try {
      const response = await fetch('/health', { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.status !== 'ok') throw new Error('health_not_ok');
      setHealth({ state: 'ok', label: '正常' });
    } catch {
      setHealth({ state: 'error', label: '异常' });
    }
  }

  return (
    <div className="admin-shell" data-admin-app-shell>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">TF</span>
          <strong>testflying</strong>
        </div>
        <nav className="global-nav" aria-label="主导航">
          {navItems.map((item) => {
            const key = item.key as AdminRouteKey;
            return (
              <button
                key={item.key}
                className={key === activeRoute ? 'nav-link active' : 'nav-link'}
                type="button"
                onClick={() => navigate(item.path, key)}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="topbar-actions">
          <button className="button" type="button" onClick={checkHealth} disabled={health.checking}>
            服务健康
          </button>
          <span className={`status-pill ${health.state}`}>{health.label}</span>
        </div>
      </header>

      <main className="admin-main">
        <section className="page-title-row">
          <div>
            <p className="eyebrow">{title.eyebrow}</p>
            <h1>{title.title}</h1>
            <p>{title.summary}</p>
          </div>
          <a className="button" href={legacyHref(activeRoute)}>
            打开旧版后台
          </a>
        </section>

        {error ? (
          <section className="notice error">
            <strong>新后台初始化失败</strong>
            <span>{error}</span>
          </section>
        ) : null}

        {activeRoute === 'apps' ? <StoreAppsPage /> : null}
        {activeRoute === 'store-reviews' ? <StoreReviewsPage /> : null}
        {activeRoute !== 'apps' && activeRoute !== 'store-reviews' ? <LegacyBackedRoute /> : null}
      </main>
    </div>
  );
}

function LegacyBackedRoute() {
  return (
    <section className="panel">
      <div className="panel-head">
        <strong>新后台重构中</strong>
        <span>无刷新路由已启用</span>
      </div>
      <p className="muted">
        当前页面已经在 React Admin App 内切换，不会重新加载浏览器文档。功能迁移完成前，可以通过右上角进入旧版后台继续操作。
      </p>
    </section>
  );
}

function legacyHref(route: AdminRouteKey): string {
  if (route === 'dashboard') return '/admin';
  return `/admin/${route}`;
}
