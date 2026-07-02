import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminApp } from './AdminApp';
import type { BuildsState, DashboardState, StoreReviewsState } from './apiClient';

const bootstrapPayload = {
  appName: 'testflying',
  navItems: [
    { key: 'dashboard', label: '总览', path: '/admin-next' },
    { key: 'uploads', label: '上传', path: '/admin-next/uploads' },
    { key: 'apps', label: '商店管理', path: '/admin-next/apps' },
    { key: 'store-reviews', label: '商店评论', path: '/admin-next/store-reviews' },
    { key: 'llm-config', label: 'LLM 配置', path: '/admin-next/llm-config' },
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
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url === '/admin/api/bootstrap') {
        return jsonResponse(bootstrapPayload);
      }
      if (url === '/admin/api/dashboard') {
        return jsonResponse(dashboardState);
      }
      if (url.startsWith('/admin/api/store-reviews')) {
        return jsonResponse(emptyReviewsState);
      }
      if (url === '/admin/api/builds') {
        return jsonResponse(buildsState);
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
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

  it('renders ordinary pages inside the React shell', async () => {
    const user = userEvent.setup();

    render(<AdminApp />);
    await screen.findByText('最近构建');
    await user.click(screen.getByRole('button', { name: '构建' }));

    expect(location.pathname).toBe('/admin-next/builds');
    expect(await screen.findByText('构建列表')).toBeTruthy();
    expect(screen.queryByText('新后台重构中')).toBeNull();
  });
});

const dashboardState: DashboardState = {
  stats: [
    { label: '应用', value: '1', tone: 'neutral' },
    { label: '构建', value: '1', tone: 'neutral' }
  ],
  recentBuilds: [],
  recentNotifications: []
};

const emptyReviewsState: StoreReviewsState = {
  apps: [],
  selectedAccountId: null,
  selectedAppId: null,
  rating: null,
  stats: { total: 0, low: 0, ios: 0, android: 0 },
  reviews: [],
  latestFetch: null,
  latestAnalysis: null,
  analysisIssues: [],
  analysisBoundaries: []
};

const buildsState: BuildsState = {
  total: 1,
  builds: [
    {
      id: 'build-1',
      app: {
        id: 'app-1',
        name: 'lookrva',
        bundleIdentifier: 'com.example.lookrva',
        platform: 'ios',
        iconColor: '#171717',
        iconText: 'LO'
      },
      version: '1.0',
      buildNumber: '1',
      platform: 'ios',
      platformLabel: 'iOS',
      environment: 'development',
      environmentLabel: '开发环境',
      status: 'available',
      note: '',
      minOsVersion: 'iOS 16.0',
      uploadedAt: '2026-06-29T00:00:00',
      uploadedAtLabel: '2026-06-29 00:00',
      expiresAt: null,
      expiresAtLabel: '-',
      artifact: null
    }
  ]
};

function jsonResponse(payload: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  );
}
