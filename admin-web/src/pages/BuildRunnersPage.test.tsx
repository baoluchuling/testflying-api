import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BuildRunnersPage } from './BuildRunnersPage';

describe('BuildRunnersPage', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
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
                  capabilities: { platforms: ['ios'], llmAdapters: ['codex'] },
                  latestVersion: '0.2.0',
                  updateStatus: 'outdated',
                  updateStatusLabel: '可更新至 0.2.0'
                }
              ],
              total: 1
            }),
            { headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (String(input) === '/admin/api/build-runners/provision' && init?.method === 'POST') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              runner: {
                id: 'runner-mac-2',
                name: 'Mac mini 2',
                status: 'offline',
                labels: ['ios-release'],
                version: '',
                packageAgentVersion: '',
                lastSeenAtLabel: '-',
                currentBuildId: null,
                capabilities: {
                  platforms: ['ios'],
                  llmAdapters: ['codex'],
                  capacity: 1,
                  hostPlatform: 'darwin',
                  arch: 'arm64'
                },
                latestVersion: '0.2.0',
                updateStatus: 'outdated',
                updateStatusLabel: '可更新至 0.2.0'
              },
              token: 'runner-secret-once'
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
    expect(screen.getByText('可更新至 0.2.0')).toBeTruthy();
  });

  it('provisions a runner and only shows the token in the one-time result', async () => {
    render(<BuildRunnersPage />);

    fireEvent.click(await screen.findByRole('button', { name: '新增节点' }));
    fireEvent.change(screen.getByLabelText('节点 ID'), { target: { value: 'runner-mac-2' } });
    fireEvent.change(screen.getByLabelText('节点名称'), { target: { value: 'Mac mini 2' } });
    fireEvent.change(screen.getByLabelText('节点标签'), { target: { value: 'ios-release' } });
    fireEvent.change(screen.getByLabelText('LLM 适配器'), { target: { value: 'codex' } });
    fireEvent.click(screen.getByRole('button', { name: '生成接入配置' }));

    expect(await screen.findByText('请立即保存，关闭后无法再次查看')).toBeTruthy();
    expect(screen.getByText('runner-secret-once')).toBeTruthy();
    expect(screen.getByRole('button', { name: '复制配置 JSON' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '关闭一次性配置' }));
    await waitFor(() => expect(screen.queryByText('runner-secret-once')).toBeNull());
  });
});
