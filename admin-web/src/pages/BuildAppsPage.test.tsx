import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BuildAppsPage } from './BuildAppsPage';

describe('BuildAppsPage', () => {
  beforeEach(() => {
    history.replaceState(null, '', '/admin/builds/apps');
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input);
      if (url === '/admin/api/builds/apps') {
        return jsonResponse(buildAppsState);
      }
      if (url === '/admin/api/apps/app-lookrva/builds' && init?.method === 'POST') {
        return jsonResponse(buildCreatedResponse);
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('selects a configured app and creates a build without leaving the page', async () => {
    const user = userEvent.setup();
    render(<BuildAppsPage />);

    await user.click(await screen.findByRole('button', { name: /lookrva/ }));
    await user.selectOptions(screen.getByLabelText('构建环境'), 'production');
    await user.clear(screen.getByLabelText('Git ref'));
    await user.type(screen.getByLabelText('Git ref'), 'release/1.2.0');
    expect(screen.getByText('当前无匹配在线节点')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '立即构建' }));

    expect(await screen.findByText('构建任务已创建')).toBeTruthy();
    expect(screen.getByText('build-agent-123')).toBeTruthy();
    expect(location.pathname).toBe('/admin/builds/apps');

    const request = vi.mocked(globalThis.fetch).mock.calls.find(
      ([input]) => String(input) === '/admin/api/apps/app-lookrva/builds'
    );
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
      environment: 'production',
      gitRef: 'release/1.2.0',
      gitUrl: 'git@example.com:lookrva/ios.git',
      runnerLabels: ['ios-production']
    });
  });
});

const appSummary = {
  id: 'app-lookrva',
  name: 'lookrva',
  bundleIdentifier: 'com.example.lookrva',
  platform: 'ios',
  iconColor: '#171717',
  iconText: 'LO'
};

const buildAppsState = {
  total: 1,
  apps: [
    {
      app: appSummary,
      environments: [
        {
          environment: 'development',
          environmentLabel: '开发环境',
          matchingRunnerCount: 1,
          hasOnlineRunner: true,
          setting: {
            environment: 'development',
            gitUrl: 'git@example.com:lookrva/ios.git',
            repoSubpath: '',
            runnerLabels: ['ios-development'],
            credentialRefs: { git: 'git-main' },
            artifactType: 'ipa',
            optionalDefaults: { gitRef: 'main' },
            updatedAtLabel: '2026-07-13 10:00'
          }
        },
        {
          environment: 'production',
          environmentLabel: '线上环境',
          matchingRunnerCount: 0,
          hasOnlineRunner: false,
          setting: {
            environment: 'production',
            gitUrl: 'git@example.com:lookrva/ios.git',
            repoSubpath: '',
            runnerLabels: ['ios-production'],
            credentialRefs: { git: 'git-main' },
            artifactType: 'ipa',
            optionalDefaults: { gitRef: 'release/latest' },
            updatedAtLabel: '2026-07-13 10:00'
          }
        }
      ],
      latestBuild: null
    }
  ]
};

const buildCreatedResponse = {
  message: '构建任务已创建',
  build: {
    id: 'build-agent-123',
    app: appSummary,
    version: '',
    buildNumber: '',
    platform: 'ios',
    platformLabel: 'iOS',
    environment: 'production',
    environmentLabel: '线上环境',
    status: 'queued',
    note: '',
    minOsVersion: '',
    uploadedAt: '2026-07-13T10:00:00Z',
    uploadedAtLabel: '2026-07-13 10:00',
    expiresAt: null,
    expiresAtLabel: '-',
    artifact: null,
    artifacts: [],
    failureClassification: '',
    failureSummary: '',
    humanAction: '',
    recentEvents: []
  },
  state: {
    app: appSummary,
    builds: [],
    settings: { development: null, production: null }
  }
};

function jsonResponse(payload: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  );
}
