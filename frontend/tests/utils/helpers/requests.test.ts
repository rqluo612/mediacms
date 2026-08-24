import axios from 'axios';
import {
    deleteRequest,
    getRequest,
    postRequest,
    putRequest,
} from '../../../src/static/js/utils/helpers/requests';

jest.mock('axios');

const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('legacy request helpers', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    test('getRequest uses the unified client and invokes its callback', async () => {
        const response = { data: 'ok' } as any;
        mockedAxios.request.mockResolvedValueOnce(response);
        const callback = jest.fn();

        await getRequest('/api/test', true, callback, undefined);

        expect(mockedAxios.request).toHaveBeenCalledWith({
            method: 'get',
            url: '/api/test',
            headers: {},
            maxContentLength: null,
            redirectOnAuth: false,
            timeout: null,
            withCredentials: true,
        });
        expect(callback).toHaveBeenCalledWith(response);
    });

    test('getRequest preserves the private-media legacy error shape', async () => {
        const original = {
            response: {
                status: 401,
                data: { detail: 'media is private' },
            },
        };
        mockedAxios.request.mockRejectedValueOnce(original);
        const errorCallback = jest.fn();

        await getRequest('/api/private', true, undefined, errorCallback);

        expect(errorCallback).toHaveBeenCalledWith({
            type: 'private',
            error: original,
            message: 'Media is private',
        });
    });

    test('getRequest preserves the unavailable-media legacy error shape', async () => {
        const original = {
            response: {
                status: 400,
                data: { detail: 'bad media' },
            },
        };
        mockedAxios.request.mockRejectedValueOnce(original);
        const errorCallback = jest.fn();

        await getRequest('/api/unavailable', true, undefined, errorCallback);

        expect(errorCallback).toHaveBeenCalledWith({
            type: 'unavailable',
            error: original,
            message: 'Media is unavailable',
        });
    });

    test('getRequest preserves the legacy network error shape', async () => {
        const original = new Error('offline');
        mockedAxios.request.mockRejectedValueOnce(original);
        const errorCallback = jest.fn();

        await getRequest('/api/offline', true, undefined, errorCallback);

        expect(errorCallback).toHaveBeenCalledWith({
            type: 'network',
            error: original,
        });
    });

    test.each([
        ['post', postRequest, { value: 1 }],
        ['put', putRequest, { value: 1 }],
    ])('%s helper sends data, configuration and CSRF-ready headers', async (method, helper, data) => {
        const response = { data: 'ok' } as any;
        mockedAxios.request.mockResolvedValueOnce(response);
        const callback = jest.fn();

        await (helper as any)(
            `/api/${method}`,
            data,
            { headers: { 'X-Test': 'yes' } },
            true,
            callback,
            undefined
        );

        expect(mockedAxios.request).toHaveBeenCalledWith({
            method,
            url: `/api/${method}`,
            data,
            headers: { 'X-Test': 'yes' },
            withCredentials: true,
        });
        expect(callback).toHaveBeenCalledWith(response);
    });

    test('delete helper uses the unified client', async () => {
        mockedAxios.request.mockResolvedValueOnce({ data: 'ok' } as any);

        await deleteRequest(
            '/api/delete',
            { headers: { 'X-Test': 'yes' } },
            true,
            undefined,
            undefined
        );

        expect(mockedAxios.request).toHaveBeenCalledWith({
            method: 'delete',
            url: '/api/delete',
            headers: { 'X-Test': 'yes' },
            withCredentials: true,
        });
    });

    test('write helpers deliver normalized errors to error callbacks', async () => {
        mockedAxios.request.mockRejectedValueOnce({
            response: {
                status: 403,
                data: { detail: 'not allowed' },
            },
        });
        const errorCallback = jest.fn();

        await postRequest('/api/write', {}, undefined, true, undefined, errorCallback);

        expect(errorCallback).toHaveBeenCalledWith(
            expect.objectContaining({
                isApiError: true,
                type: 'forbidden',
                status: 403,
                message: 'not allowed',
            })
        );
    });

    test('missing callbacks never cause an unhandled rejection', async () => {
        mockedAxios.request.mockRejectedValueOnce(new Error('boom'));

        await expect(
            getRequest('/api/test', false, undefined as any, undefined as any)
        ).resolves.toBeUndefined();
    });
});
