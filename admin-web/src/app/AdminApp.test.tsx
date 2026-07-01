import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminApp } from './AdminApp';

const bootstrapPayload = {
  appName: 'testflying',
  navItems: [
    { key: 'dashboard', label: '总览', path: '/admin-next' },
    { key: 'uploads', label: '上传', path: '/admin-next/uploads' },
    { key: 'apps', label: '商店管理', path: '/admin-next/apps' },
    { key: 'store-reviews', label: '商店评论', path: '/admin-next/store-reviews' },
    { key: 'api-docs', label: '接口文档', path: '/admin-next/api-docs' },
    { key: 'builds', label: '构建', path: '/admin-next/builds' },
    { key: 'devices', label: '设备', path: '/admin-next/devices' },
    { key: 'app-logs', label: 'App 日志', path: '/admin-next/app-logs' },
    { key: 'notifications', label: '通知', path: '/admin-next/notifications' }
  ],
  health: { state: 'idle', label: '未检查' }
};

describe('AdminApp', () => {
  beforeEach(() => {
    history.replaceState(null, '', '/admin-next');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(bootstrapPayload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('switches top-level tabs without assigning a new document location', async () => {
    const pushState = vi.spyOn(history, 'pushState');
    const user = userEvent.setup();

    render(<AdminApp />);
    await screen.findByText('服务健康');
    await user.click(screen.getByRole('button', { name: '商店评论' }));

    expect(pushState).toHaveBeenCalledWith(
      { adminRoute: 'store-reviews' },
      '',
      '/admin-next/store-reviews'
    );
    expect(location.pathname).toBe('/admin-next/store-reviews');
    expect(screen.getByRole('heading', { name: '商店评论' })).toBeTruthy();
  });
});
