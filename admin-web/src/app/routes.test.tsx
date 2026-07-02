import { describe, expect, it } from 'vitest';
import { routeKeyFromPath } from './routes';

describe('routeKeyFromPath', () => {
  it('keeps developer account and store workspace paths inside the React shell', () => {
    expect(routeKeyFromPath('/admin-next/accounts')).toBe('accounts');
    expect(routeKeyFromPath('/admin-next/accounts/account-ios')).toBe('accounts');
    expect(routeKeyFromPath('/admin-next/accounts/account-ios/apps/app-ios/store')).toBe('accounts');
    expect(routeKeyFromPath('/admin-next/accounts/account-ios/apps/app-ios/marketing')).toBe('accounts');
    expect(routeKeyFromPath('/admin-next/accounts/account-ios/apps/app-ios/marketing-pages/page-1')).toBe('accounts');
  });
});
