import { z } from 'zod';
import { detailSchema, modelSchema, readinessSchema, slateSchema } from './contracts';

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
  allow503 = false,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const timer = setTimeout(abort, 10_000);
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok && !(allow503 && response.status === 503)) {
      throw new ApiError(
        response.status === 404
          ? path.startsWith('/api/v1/games/')
            ? 'No retained game was found for this ID.'
            : 'The forecast service is unavailable at this address.'
          : response.status === 422
            ? 'Check the date or game ID and try again.'
            : 'Forecast data is temporarily unavailable. Try refreshing.',
        response.status,
      );
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError('The API returned an unreadable response.');
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success)
      throw new ApiError(
        'The API response failed validation. No unverified forecast is displayed.',
      );
    return parsed.data;
  } catch (error) {
    if (signal.aborted) throw error;
    if (controller.signal.aborted)
      throw new ApiError('The API did not respond in time. Try refreshing.');
    if (error instanceof ApiError) throw error;
    throw new ApiError('Cannot reach the forecast API. Check that the local API is running.');
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}

export const api = {
  slate: (date: string, signal: AbortSignal) =>
    request(`/api/v1/predictions?date=${encodeURIComponent(date)}`, slateSchema, signal),
  detail: (id: number, signal: AbortSignal) => request(`/api/v1/games/${id}`, detailSchema, signal),
  model: (signal: AbortSignal) => request('/api/v1/model', modelSchema, signal),
  readiness: (signal: AbortSignal) => request('/health/ready', readinessSchema, signal, true),
};
