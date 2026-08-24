import axios from 'axios';
import {
    apiClient,
    apiFetch,
    getApiBaseUrl,
    normalizeApiError,
    resolveApiUrl,
    setApiBaseUrl,
} from '../../../src/static/js/utils/helpers/apiClient';

jest.mock('axios');

const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('apiClient', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        setApiBaseUrl('/api/v1');
        document.cookie = 'csrftoken=csrf-test-token';
    });

    test('resolves relative API paths and leaves absolute paths unchanged', () => {
        setApiBaseUrl('/custom/api/');

        expect(getApiBaseUrl()).toBe('/custom/api');
        expect(resolveApiUrl('media')).toBe('/custom/api/media');
        expect(resolveApiUrl('/api/v1/media')).toBe('/api/v1/media');
        expect(resolveApiUrl('https://example.com/api')).toBe(
            'https://example.com/api'
        );
    });

    test('sends Session cookies and CSRF token for unsafe methods', async () => {
        mockedAxios.request.mockResolvedValueOnce({ data: { ok: true } } as any);

        await apiClient.post('media/action', { type: 'like' });

        expect(mockedAxios.request).toHaveBeenCalledWith({
            method: 'post',
            url: '/api/v1/media/action',
            data: { type: 'like' },
            headers: { 'X-CSRFToken': 'csrf-test-token' },
            withCredentials: true,
        });
    });

    test('adapts JSON fetch calls to the unified client', async () => {
        mockedAxios.request.mockResolvedValueOnce({
            data: { updated: true },
            status: 200,
            statusText: 'OK',
            headers: {},
            config: { url: '/api/v1/media/user/bulk_actions' },
        } as any);

        const response = await apiFetch('/api/v1/media/user/bulk_actions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'publish' }),
        });

        expect(mockedAxios.request).toHaveBeenCalledWith(
            expect.objectContaining({
                method: 'post',
                data: { action: 'publish' },
                withCredentials: true,
                headers: expect.objectContaining({
                    'X-CSRFToken': 'csrf-test-token',
                }),
            })
        );
        expect(response.ok).toBe(true);
        await expect(response.json()).resolves.toEqual({ updated: true });
    });

    test('returns a fetch-style response for HTTP errors', async () => {
        mockedAxios.request.mockRejectedValueOnce({
            response: {
                data: { detail: 'Forbidden' },
                status: 403,
                statusText: 'Forbidden',
                headers: {},
                config: { url: '/api/v1/media/user/bulk_actions' },
            },
        });

        const response = await apiFetch('/api/v1/media/user/bulk_actions');

        expect(response.ok).toBe(false);
        expect(response.status).toBe(403);
        await expect(response.json()).resolves.toEqual({ detail: 'Forbidden' });
    });

    test('announces normalized errors for the global notification layer', async () => {
        const listener = jest.fn();
        window.addEventListener('mediacms:api-error', listener);
        mockedAxios.request.mockRejectedValueOnce({
            response: {
                status: 429,
                data: { detail: 'Try again later.' },
            },
        });

        await expect(
            apiClient.get('/api/v1/media', { redirectOnAuth: false })
        ).rejects.toEqual(
            expect.objectContaining({
                type: 'rate-limit',
                status: 429,
            })
        );

        expect(listener).toHaveBeenCalledTimes(1);
        expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual(
            expect.objectContaining({
                type: 'rate-limit',
                message: 'Try again later.',
            })
        );
        window.removeEventListener('mediacms:api-error', listener);
    });

    test('does not overwrite an explicit CSRF header', async () => {
        mockedAxios.request.mockResolvedValueOnce({ data: {} } as any);

        await apiClient.delete('/api/v1/item', {
            headers: { 'X-CSRFToken': 'explicit-token' },
        });

        expect(mockedAxios.request).toHaveBeenCalledWith(
            expect.objectContaining({
                headers: { 'X-CSRFToken': 'explicit-token' },
            })
        );
    });

    test.each([
        [401, 'authentication'],
        [403, 'forbidden'],
        [404, 'not-found'],
        [429, 'rate-limit'],
        [500, 'server'],
    ])('normalizes HTTP %s as %s', (status, type) => {
        const normalized = normalizeApiError({
            response: { status, data: {} },
        });

        expect(normalized).toEqual(
            expect.objectContaining({
                isApiError: true,
                status,
                type,
            })
        );
    });

    test('distinguishes private-media 401 responses', () => {
        const normalized = normalizeApiError({
            response: {
                status: 401,
                data: { detail: 'media is private' },
            },
        });

        expect(normalized.type).toBe('private');
        expect(normalized.message).toBe('media is private');
    });

    test('normalizes network and canceled failures', () => {
        const network = normalizeApiError(new Error('offline'));
        const canceled = normalizeApiError({
            code: 'ERR_CANCELED',
            name: 'CanceledError',
        });

        expect(network.type).toBe('network');
        expect(canceled.type).toBe('canceled');
    });

    test('reports normalized upload progress', async () => {
        mockedAxios.request.mockImplementationOnce(async (config: any) => {
            config.onUploadProgress({ loaded: 25, total: 100 });
            return { data: { ok: true } } as any;
        });
        const onProgress = jest.fn();

        await apiClient.upload('/fu/upload/', new FormData(), { onProgress });

        expect(onProgress).toHaveBeenCalledWith({
            loaded: 25,
            total: 100,
            percent: 25,
        });
    });

    test('creates AbortController instances for request cancellation', () => {
        const controller = apiClient.createCancelController();

        expect(controller.signal.aborted).toBe(false);
        controller.abort();
        expect(controller.signal.aborted).toBe(true);
    });
});
