import { describe, expect, it } from 'vitest';
import { navKeyFromPath, routeKeyFromPath } from './routes';

describe('routeKeyFromPath', () => {
  it('keeps developer account and store workspace paths inside the React shell', () => {
    expect(routeKeyFromPath('/admin/accounts')).toBe('accounts');
    expect(routeKeyFromPath('/admin/accounts/account-ios')).toBe('accounts');
    expect(routeKeyFromPath('/admin/accounts/account-ios/apps/app-ios/store')).toBe('accounts');
    expect(routeKeyFromPath('/admin/accounts/account-ios/apps/app-ios/marketing')).toBe('accounts');
    expect(routeKeyFromPath('/admin/accounts/account-ios/apps/app-ios/marketing-pages/page-1')).toBe('accounts');
  });
});

describe('navKeyFromPath', () => {
  it('highlights store management for app store workspace pages', () => {
    expect(navKeyFromPath('/admin/apps/app-ios-demo')).toBe('apps');
    expect(navKeyFromPath('/admin/accounts/account-ios/apps/app-ios/store')).toBe('apps');
    expect(navKeyFromPath('/admin/accounts/account-ios/apps/app-ios/marketing')).toBe('apps');
    expect(navKeyFromPath('/admin/accounts/account-ios/apps/app-ios/connection')).toBe('apps');
  });
});
