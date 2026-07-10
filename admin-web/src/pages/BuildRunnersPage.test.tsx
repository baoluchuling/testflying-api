import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BuildRunnersPage } from './BuildRunnersPage';

describe('BuildRunnersPage', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      if (String(input) === '/admin/api/build-runners') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              runners: [
                {
                  id: 'runner-mac-1',
                  name: 'Mac mini 1',
                  status: 'online',
                  labels: ['ios-release'],
                  version: '0.1.0',
                  packageAgentVersion: '0.1.0',
                  lastSeenAtLabel: '刚刚',
                  currentBuildId: null,
                  capabilities: { platforms: ['ios'], llmAdapters: ['codex'] }
                }
              ],
              total: 1
            }),
            { headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      return Promise.reject(new Error(`unexpected fetch ${String(input)}`));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders runner status and capabilities', async () => {
    render(<BuildRunnersPage />);

    expect(await screen.findByText('Mac mini 1')).toBeTruthy();
    expect(screen.getByText('online')).toBeTruthy();
    expect(screen.getByText('ios-release')).toBeTruthy();
    expect(screen.getByText('LLM: codex')).toBeTruthy();
    expect(screen.getByText('刚刚')).toBeTruthy();
  });
});
