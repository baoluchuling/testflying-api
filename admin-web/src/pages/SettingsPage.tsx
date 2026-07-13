import type { SettingsView } from '../app/routes';
import { LlmConfigPage } from './LlmConfigPage';

const views: Array<{ key: SettingsView; label: string; path: string }> = [
  { key: 'general', label: '通用设置', path: '/admin/settings/general' },
  { key: 'notifications', label: '通知设置', path: '/admin/settings/notifications' },
  { key: 'llm', label: 'LLM 配置', path: '/admin/settings/llm' },
  { key: 'runtime', label: '运行环境', path: '/admin/settings/runtime' }
];

const placeholder: Record<Exclude<SettingsView, 'llm'>, { eyebrow: string; title: string; summary: string }> = {
  general: {
    eyebrow: 'General',
    title: '通用设置',
    summary: '维护 Connector 地址模板等业务配置。'
  },
  notifications: {
    eyebrow: 'Notifications',
    title: '通知设置',
    summary: '维护通知渠道并执行连接检查。'
  },
  runtime: {
    eyebrow: 'Runtime',
    title: '运行环境',
    summary: '只读查看部署环境变量的配置状态。'
  }
};

export function SettingsPage({ view }: { view: SettingsView }) {
  function navigate(path: string) {
    history.pushState({ adminRoute: 'settings' }, '', path);
  }

  const content = view === 'llm' ? null : placeholder[view];

  return (
    <div className="section-workspace" data-settings-workspace>
      <nav className="secondary-nav" aria-label="设置导航">
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
      {content ? (
        <section className="panel workspace-placeholder">
          <p className="eyebrow">{content.eyebrow}</p>
          <h2>{content.title}</h2>
          <p>{content.summary}</p>
        </section>
      ) : (
        <LlmConfigPage />
      )}
    </div>
  );
}
