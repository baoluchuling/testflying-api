export type AdminRouteKey =
  | 'dashboard'
  | 'uploads'
  | 'apps'
  | 'store-reviews'
  | 'api-docs'
  | 'builds'
  | 'devices'
  | 'app-logs'
  | 'notifications';

export const routeTitles: Record<AdminRouteKey, { eyebrow: string; title: string; summary: string }> = {
  dashboard: {
    eyebrow: 'Internal Distribution',
    title: '总览',
    summary: '查看应用、构建、设备和账号提醒的当前状态。'
  },
  uploads: {
    eyebrow: 'Internal Distribution',
    title: '上传构建',
    summary: '上传 IPA / APK，解析包信息并生成安装地址。'
  },
  apps: {
    eyebrow: 'Store Management',
    title: '商店管理',
    summary: '从应用进入商店内容、评论和账号连接。'
  },
  'store-reviews': {
    eyebrow: 'Store Reviews',
    title: '商店评论',
    summary: '增量拉取最近评论，并通过 LLM 归纳需要关注的问题。'
  },
  'api-docs': {
    eyebrow: 'Developer API',
    title: '接口文档',
    summary: '查看商店管理对外接口、参数和调用示例。'
  },
  builds: {
    eyebrow: 'Internal Distribution',
    title: '构建',
    summary: '查看所有上传构建和可复制的安装地址。'
  },
  devices: {
    eyebrow: 'Internal Distribution',
    title: '设备',
    summary: '查看已登记设备、平台、系统和签名状态。'
  },
  'app-logs': {
    eyebrow: 'App Log Console',
    title: 'App 日志',
    summary: 'App 日志会迁移为保持连接状态的前端页面。'
  },
  notifications: {
    eyebrow: 'Internal Distribution',
    title: '通知',
    summary: '按类型筛选构建、账号和设备相关通知。'
  }
};

export function routeKeyFromPath(pathname: string): AdminRouteKey {
  const relative = pathname.replace(/^\/admin-next\/?/, '').replace(/^\/+/, '');
  const first = relative.split('/')[0] || 'dashboard';
  if (first === 'store-reviews') return 'store-reviews';
  if (first === 'api-docs') return 'api-docs';
  if (first === 'app-logs') return 'app-logs';
  if (
    first === 'uploads'
    || first === 'apps'
    || first === 'builds'
    || first === 'devices'
    || first === 'notifications'
  ) {
    return first;
  }
  return 'dashboard';
}
