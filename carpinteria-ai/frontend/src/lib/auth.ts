const COOKIE = 'auth_token';

export function getToken(): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${COOKIE}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

export function setToken(token: string): void {
  const maxAge = 8 * 60 * 60; // 8 hours
  document.cookie = `${COOKIE}=${encodeURIComponent(token)}; path=/; max-age=${maxAge}; SameSite=Strict`;
}

export function clearToken(): void {
  document.cookie = `${COOKIE}=; path=/; max-age=0`;
}
