import type { AppProps } from 'next/app';
import { useEffect } from 'react';
import { useRouter } from 'next/router';
import '../styles/globals.css';
import { trackPageview } from '../lib/analytics';

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();

  useEffect(() => {
    trackPageview(router.asPath);
    const handleRouteChange = (path: string) => trackPageview(path);
    router.events.on('routeChangeComplete', handleRouteChange);
    return () => router.events.off('routeChangeComplete', handleRouteChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <Component {...pageProps} />;
}
