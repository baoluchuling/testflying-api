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
    summary: '后台概览会在后续迁移，当前可从旧版后台查看。'
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
    summary: '对外接口文档会迁移为可定位的前端文档页。'
  },
  builds: {
    eyebrow: 'Internal Distribution',
    title: '构建',
    summary: '构建列表会在普通页面迁移阶段接入。'
  },
  devices: {
    eyebrow: 'Internal Distribution',
    title: '设备',
    summary: '设备列表会在普通页面迁移阶段接入。'
  },
  'app-logs': {
    eyebrow: 'App Log Console',
    title: 'App 日志',
    summary: 'App 日志会迁移为保持连接状态的前端页面。'
  },
  notifications: {
    eyebrow: 'Internal Distribution',
    title: '通知',
    summary: '通知列表会在普通页面迁移阶段接入。'
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
