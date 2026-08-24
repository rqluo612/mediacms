import { apiClient } from './apiClient';

function legacyGetError(error) {
  if (error.type === 'private') {
    return {
      type: 'private',
      error: error.originalError || error,
      message: 'Media is private',
    };
  }

  if (error.type === 'bad-request') {
    return {
      type: 'unavailable',
      error: error.originalError || error,
      message: 'Media is unavailable',
    };
  }

  if (error.type === 'network') {
    return {
      type: 'network',
      error: error.originalError || error,
    };
  }

  return error;
}

function executeRequest(request, callback, errorCallback, mapError = (error) => error) {
  return request
    .then((response) => {
      if (typeof callback === 'function') {
        callback(response);
      }
      return response;
    })
    .catch((error) => {
      if (typeof errorCallback === 'function') {
        errorCallback(mapError(error));
      }
      return undefined;
    });
}

export async function getRequest(url, sync, callback, errorCallback) {
  const requestConfig = {
    timeout: null,
    maxContentLength: null,
    redirectOnAuth: false,
  };

  return executeRequest(apiClient.get(url, requestConfig), callback, errorCallback, legacyGetError);
}

export async function postRequest(url, postData, configData, sync, callback, errorCallback) {
  postData = postData || {};
  return executeRequest(apiClient.post(url, postData, configData || {}), callback, errorCallback);
}

export async function putRequest(url, putData, configData, sync, callback, errorCallback) {
  putData = putData || {};
  return executeRequest(apiClient.put(url, putData, configData || {}), callback, errorCallback);
}

export async function deleteRequest(url, configData, sync, callback, errorCallback) {
  configData = configData || {};
  return executeRequest(apiClient.delete(url, configData), callback, errorCallback);
}
