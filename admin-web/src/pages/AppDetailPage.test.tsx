import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppDetailPage } from './AppDetailPage';

describe('AppDetailPage', () => {
  beforeEach(() => {
    history.replaceState(null, '', '/admin/apps/app-ios-demo');
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url === '/admin/api/apps/app-ios-demo') {
        return jsonResponse(appDetailState);
      }
      if (url === '/admin/api/apps/app-ios-demo/builds') {
        return jsonResponse({
          message: '构建任务已创建',
          build: {
            ...appDetailState.builds[0],
            id: 'build-agent-1',
            lifecycleStatus: 'queued',
            lifecycleStatusLabel: '排队中',
            source: 'agent',
            sourceLabel: 'Agent'
          },
          state: appDetailState
        });
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders app summary, quick build controls, settings, and build history', async () => {
    render(<AppDetailPage appId="app-ios-demo" />);

    expect(await screen.findByRole('heading', { name: 'AnyStories' })).toBeTruthy();
    expect(screen.getByText('com.example.any')).toBeTruthy();
    expect(screen.getByRole('button', { name: '立即构建' })).toBeTruthy();
    expect(screen.getByText('构建历史')).toBeTruthy();
    expect(screen.getByText('build 45')).toBeTruthy();
  });

  it('submits a quick build request', async () => {
    const user = userEvent.setup();
    render(<AppDetailPage appId="app-ios-demo" />);

    await screen.findByRole('heading', { name: 'AnyStories' });
    await user.clear(screen.getByLabelText('Git ref'));
    await user.type(screen.getByLabelText('Git ref'), 'release/1.2.0');
    await user.click(screen.getByRole('button', { name: '立即构建' }));

    expect(await screen.findByText('构建任务已创建')).toBeTruthy();
  });
});

const appDetailState = {
  app: {
    id: 'app-ios-demo',
    name: 'AnyStories',
    bundleIdentifier: 'com.example.any',
    platform: 'ios',
    iconColor: '#2478FF',
    iconText: 'AN'
  },
  settings: {
    development: {
      environment: 'development',
      gitUrl: 'git@example.com:any/ios.git',
      repoSubpath: '',
      runnerLabels: ['ios-release'],
      credentialRefs: { git: 'git-main' },
      artifactType: 'ipa',
      optionalDefaults: {},
      updatedAtLabel: '2026-07-09 10:00'
    },
    production: null
  },
  builds: [
    {
      id: 'build-1',
      app: {
        id: 'app-ios-demo',
        name: 'AnyStories',
        bundleIdentifier: 'com.example.any',
        platform: 'ios',
        iconColor: '#2478FF',
        iconText: 'AN'
      },
      version: '1.0',
      buildNumber: '45',
      platform: 'ios',
      platformLabel: 'iOS',
      environment: 'development',
      environmentLabel: '开发环境',
      source: 'upload',
      sourceLabel: '上传',
      lifecycleStatus: 'succeeded',
      lifecycleStatusLabel: '成功',
      status: 'available',
      note: '',
      minOsVersion: '',
      gitRef: 'main',
      uploadedAt: '2026-07-09T10:00:00Z',
      uploadedAtLabel: '2026-07-09 10:00',
      expiresAt: null,
      expiresAtLabel: '-',
      artifact: null,
      artifacts: []
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
