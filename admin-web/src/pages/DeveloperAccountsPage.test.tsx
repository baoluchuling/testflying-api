import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DeveloperAccountsPage } from './DeveloperAccountsPage';
import type {
  DeveloperAccountDetailState,
  MarketingPageActionResponse,
  MarketingPageDetailState,
  StoreWorkspaceActionResponse,
  StoreWorkspaceState
} from '../app/apiClient';

describe('DeveloperAccountsPage store workspace', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows editable inputs after expanding store page languages', async () => {
    const user = userEvent.setup();
    history.replaceState(null, '', '/admin/accounts/account-ios/apps/app-ios/store');

    render(<DeveloperAccountsPage />);

    await screen.findByRole('heading', { name: 'lookrva' });
    await screen.findByText('当前商店最新版本：1.0');
    await user.click(screen.getByRole('button', { name: '展开描述多语言' }));
    const hantDescription = await screen.findByRole('textbox', { name: 'zh-Hant 描述' });
    await user.clear(hantDescription);
    await user.type(hantDescription, '繁體描述');
    await user.click(screen.getByRole('button', { name: '保存草稿' }));

    await waitFor(() => {
      expect(lastJsonPayload('/workspace/metadata')?.locales).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ locale: 'zh-Hant', description: '繁體描述' })
        ])
      );
    });
  });

  it('shows editable inputs after expanding marketing page languages', async () => {
    const user = userEvent.setup();
    history.replaceState(
      null,
      '',
      '/admin/accounts/account-ios/apps/app-ios/marketing-pages/page-1'
    );

    render(<DeveloperAccountsPage />);

    await screen.findByDisplayValue('测试自定义产品页');
    await user.click(screen.getByRole('button', { name: '展开宣传文本多语言' }));
    const frenchText = await screen.findByRole('textbox', { name: 'fr-FR 宣传文本' });
    await user.clear(frenchText);
    await user.type(frenchText, 'Texte promotionnel');
    await user.click(screen.getByRole('button', { name: '保存草稿' }));

    await waitFor(() => {
      expect(lastJsonPayload('/marketing-pages/page-1')?.locales).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ locale: 'fr-FR', promotionalText: 'Texte promotionnel' })
        ])
      );
    });
  });
});

const accountDetail: DeveloperAccountDetailState = {
  account: {
    id: 'account-ios',
    teamName: '测试账号',
    status: 'ok',
    statusLabel: '正常',
    expiresAt: '',
    expiresAtLabel: '未设置',
    remainingDays: 0,
    appNames: ['lookrva'],
    connectorName: 'Mac Connector',
    connectorStatus: 'ok',
    connectorStatusLabel: '正常',
    latestSyncStatus: 'ok',
    latestSyncAtLabel: '刚刚',
    detailPath: '/admin/accounts/account-ios'
  },
  connector: {
    name: 'Mac Connector',
    baseUrl: 'http://127.0.0.1:18080',
    authToken: '',
    status: 'ok',
    statusLabel: '正常',
    checkedAtLabel: '刚刚'
  },
  accountStorePlatform: 'ios',
  apps: [
    {
      id: 'app-ios',
      name: 'lookrva',
      bundleIdentifier: 'com.example.lookrva',
      platform: 'ios',
      platformLabel: 'iOS',
      iconColor: '#18181b',
      iconText: 'LO',
      storeAppId: '1234567890',
      storePackageName: '',
      latestVersionLabel: '1.0',
      storePath: '/admin/accounts/account-ios/apps/app-ios/store',
      marketingPath: '/admin/accounts/account-ios/apps/app-ios/marketing',
      releaseNotesPath: '/admin/accounts/account-ios/apps/app-ios/release-notes',
      connectionPath: '/admin/accounts/account-ios/apps/app-ios/connection'
    }
  ],
  unassignedApps: [],
  syncRuns: []
};

const workspaceState: StoreWorkspaceState = {
  account: accountDetail.account,
  app: accountDetail.apps[0],
  section: 'store',
  version: '1.0',
  locale: 'en-US',
  sourceLocale: 'en-US',
  supportedLocales: ['en-US', 'zh-Hant', 'fr-FR'],
  localizedMetadata: [
    {
      locale: 'en-US',
      isSource: true,
      keywords: '',
      promotionalText: 'Source promo',
      description: 'Source description',
      releaseNotes: 'Fix bugs',
      storeImages: {}
    },
    {
      locale: 'zh-Hant',
      isSource: false,
      keywords: '',
      promotionalText: '',
      description: '',
      releaseNotes: '',
      storeImages: {}
    },
    {
      locale: 'fr-FR',
      isSource: false,
      keywords: '',
      promotionalText: '',
      description: '',
      releaseNotes: '',
      storeImages: {}
    }
  ],
  connector: accountDetail.connector,
  preflightStatus: 'idle',
  preflightLabel: '等待检查',
  syncRuns: [],
  marketingPages: [
    {
      id: 'page-1',
      pageId: 'page-1',
      pageName: '测试自定义产品页',
      pageType: 'custom_product_page',
      typeLabel: '自定义产品页',
      status: 'draft',
      statusLabel: '草稿',
      applePageIdLabel: '暂无',
      deepLinkUrl: '',
      languageCount: 3,
      filledTextCount: 1,
      assetCount: 0,
      detailPath: '/admin/accounts/account-ios/apps/app-ios/marketing-pages/page-1'
    }
  ]
};

const marketingPageState: MarketingPageDetailState = {
  account: accountDetail.account,
  app: accountDetail.apps[0],
  page: workspaceState.marketingPages[0],
  section: 'marketing',
  locale: 'en-US',
  sourceLocale: 'en-US',
  supportedLocales: ['en-US', 'zh-Hant', 'fr-FR'],
  localizedPage: [
    { locale: 'en-US', isSource: true, promotionalText: 'Source promo', storeImages: {} },
    { locale: 'zh-Hant', isSource: false, promotionalText: '', storeImages: {} },
    { locale: 'fr-FR', isSource: false, promotionalText: '', storeImages: {} }
  ],
  connector: accountDetail.connector,
  preflightStatus: 'idle',
  preflightLabel: '等待检查',
  syncRuns: []
};

function mockFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (url === '/admin/api/developer-accounts/account-ios') {
    return jsonResponse(accountDetail);
  }
  if (url.startsWith('/admin/api/developer-accounts/account-ios/apps/app-ios/workspace?')) {
    return jsonResponse({ ...workspaceState, section: new URL(url, 'http://localhost').searchParams.get('section') || 'store' });
  }
  if (url.endsWith('/workspace/metadata')) {
    const response: StoreWorkspaceActionResponse = {
      message: '已保存',
      state: workspaceState,
      syncRuns: []
    };
    return jsonResponse(response);
  }
  if (url.endsWith('/workspace/marketing-pages/page-1') && init?.method === 'PUT') {
    const response: MarketingPageActionResponse = {
      message: '已保存',
      state: marketingPageState,
      workspace: null,
      syncRuns: []
    };
    return jsonResponse(response);
  }
  if (url.endsWith('/workspace/marketing-pages/page-1')) {
    return jsonResponse(marketingPageState);
  }
  return Promise.reject(new Error(`unexpected fetch ${url}`));
}

function lastJsonPayload(urlPart: string): Record<string, unknown> | null {
  const calls = vi.mocked(fetch).mock.calls;
  for (const [url, init] of calls.slice().reverse()) {
    if (!String(url).includes(urlPart) || typeof init?.body !== 'string') continue;
    return JSON.parse(init.body) as Record<string, unknown>;
  }
  return null;
}

function jsonResponse(payload: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  );
}
