import { useEffect, useState } from 'react';
import {
  AdminApiError,
  loadNotificationsState,
  type NotificationItem,
  type NotificationsState
} from '../app/apiClient';

export function NotificationsPage() {
  const [state, setState] = useState<NotificationsState | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    void loadFromLocation();
    const onPopState = () => void loadFromLocation();
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  async function loadFromLocation() {
    setError('');
    try {
      setState(await loadNotificationsState(location.search || ''));
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  async function selectType(type: string) {
    const params = new URLSearchParams();
    if (type !== 'all') params.set('type', type);
    const query = params.toString();
    history.pushState(
      { adminRoute: 'notifications', type },
      '',
      query ? `/admin/notifications?${query}` : '/admin/notifications'
    );
    await loadFromLocation();
  }

  return (
    <div className="notifications-page" data-notifications-page>
      <section className="panel">
        <div className="panel-head">
          <strong>通知</strong>
          <span>{state?.total ?? 0} 条</span>
        </div>
        {state ? <DingTalkSetup state={state.dingtalk} /> : null}
        <div className="filter-tabs notification-filter-tabs" aria-label="通知类型筛选">
          {(state?.typeCounts ?? [{ type: 'all', label: '全部', count: 0 }]).map((item) => (
            <button
              key={item.type}
              type="button"
              className={state?.activeType === item.type ? 'filter-tab active' : 'filter-tab'}
              onClick={() => void selectType(item.type)}
            >
              {item.label}
              <span>{item.count}</span>
            </button>
          ))}
        </div>
        {error ? <div className="notice error">{error}</div> : null}
        <div className="notification-list">
          {(state?.notifications ?? []).map((notification) => (
            <NotificationRow key={notification.id} notification={notification} />
          ))}
        </div>
        {!state && !error ? <div className="empty-state">正在加载通知...</div> : null}
        {state && state.notifications.length === 0 ? (
          <div className="empty-state">当前筛选下没有通知。</div>
        ) : null}
      </section>
    </div>
  );
}

function DingTalkSetup({ state }: { state: NotificationsState['dingtalk'] }) {
  return (
    <section className="dingtalk-setup" aria-labelledby="dingtalk-setup-title">
      <div className="dingtalk-setup-head">
        <div>
          <strong id="dingtalk-setup-title">钉钉机器人配置</strong>
          <span>构建进入人工处理或失败状态时发送群通知</span>
        </div>
        <span className={`tag ${state.configured ? 'ok' : 'warn'}`}>
          {state.configured ? '已配置' : '未配置'}
        </span>
      </div>
      <div className="dingtalk-delivery-stats" aria-label="钉钉投递状态">
        <span>待发送 {state.pendingDeliveryCount}</span>
        <span>失败 {state.deadDeliveryCount}</span>
      </div>
      <ol className="dingtalk-setup-steps">
        <li>在目标钉钉群的机器人管理中创建自定义机器人。</li>
        <li>安全设置选择“加签”，取得 Webhook URL 和加签密钥。</li>
        <li>在 TestFlying 服务端配置以下环境变量。</li>
        <li>重启 TestFlying API 服务。</li>
        <li>返回本页面确认状态显示为“已配置”。</li>
      </ol>
      <pre className="dingtalk-env-example"><code>{`TESTFLYING_DINGTALK_WEBHOOK_URL: \${TESTFLYING_DINGTALK_WEBHOOK_URL}
TESTFLYING_DINGTALK_SECRET: \${TESTFLYING_DINGTALK_SECRET}`}</code></pre>
      <p className="dingtalk-trigger-note">
        触发状态：<code>{state.triggers.join(', ') || 'failed, needs_human'}</code>
      </p>
    </section>
  );
}

function NotificationRow({ notification }: { notification: NotificationItem }) {
  return (
    <article className="notification-row">
      <span className="notification-dot" style={{ backgroundColor: notification.tagColor }} />
      <div>
        <strong>{notification.title}</strong>
        <span>{notification.subtitle}</span>
        <small>{notification.section} · {notification.createdAtLabel}</small>
      </div>
      <em>{notification.tag}</em>
    </article>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
}
