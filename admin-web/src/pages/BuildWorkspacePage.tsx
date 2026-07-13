import { BuildRunnersPage } from './BuildRunnersPage';
import { BuildsPage } from './BuildsPage';
import type { BuildView } from '../app/routes';

const views: Array<{ key: BuildView; label: string; path: string }> = [
  { key: 'apps', label: '构建应用', path: '/admin/builds/apps' },
  { key: 'history', label: '构建历史', path: '/admin/builds/history' },
  { key: 'runners', label: '构建节点', path: '/admin/builds/runners' }
];

export function BuildWorkspacePage({ view }: { view: BuildView }) {
  function navigate(path: string) {
    history.pushState({ adminRoute: 'builds' }, '', path);
  }

  return (
    <div className="section-workspace" data-build-workspace>
      <nav className="secondary-nav" aria-label="构建导航">
        {views.map((item) => (
          <button
            key={item.key}
            className={view === item.key ? 'secondary-nav-item active' : 'secondary-nav-item'}
            type="button"
            onClick={() => navigate(item.path)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {view === 'apps' ? (
        <section className="panel workspace-placeholder">
          <p className="eyebrow">Configured Applications</p>
          <h2>构建应用</h2>
          <p>从已配置构建环境的应用中选择目标并发起构建。</p>
        </section>
      ) : null}
      {view === 'history' ? <BuildsPage /> : null}
      {view === 'runners' ? <BuildRunnersPage /> : null}
    </div>
  );
}
