import { useEffect, useRef, useState } from 'react';

type Resource<T> = { key: string; data?: T; loadedAt?: Date; loading: boolean; error?: string };

// Data may survive a same-query refresh failure, but never cross dates, games, or demo mode.
export function useResource<T>(
  key: string,
  refresh: number,
  load: (signal: AbortSignal) => Promise<T>,
) {
  const loader = useRef(load);
  loader.current = load;
  const [state, setState] = useState<Resource<T>>({ key, loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({ ...(previous.key === key ? previous : {}), key, loading: true }));
    void loader
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ key, data, loadedAt: new Date(), loading: false });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState((previous) => ({
            ...previous,
            key,
            loading: false,
            error: error instanceof Error ? error.message : 'Unable to load this view.',
          }));
      });
    return () => controller.abort();
  }, [key, refresh]);
  return state.key === key ? state : ({ key, loading: true } as Resource<T>);
}
