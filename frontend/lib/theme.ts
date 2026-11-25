'use client';

import { useEffect, useState } from 'react';
import { THEME_KEY } from './themeScript';

export { THEME_KEY };

/**
 * Light/dark theme. The choice lives in <html data-theme> and localStorage (THEME_KEY).
 * app/layout.tsx sets the attribute before first paint (saved choice, else the OS setting),
 * so pages never flash the wrong theme.
 */
export type Theme = 'light' | 'dark';

export function getTheme(): Theme {
  if (typeof document === 'undefined') return 'dark';
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

/** Switch theme and remember it. Colour transitions are paused for one frame so the swap is instant. */
export function setTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.add('theme-switching');
  root.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // storage blocked: the theme still applies for this page
  }
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-switching')));
}

/** The current theme, kept in sync with <html data-theme> (toggle, other tabs' choices, OS changes). */
export function useTheme(): Theme {
  const [theme, setState] = useState<Theme>('dark');
  useEffect(() => {
    setState(getTheme());
    const observer = new MutationObserver(() => setState(getTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const onStorage = (e: StorageEvent) => {
      if (e.key === THEME_KEY && (e.newValue === 'light' || e.newValue === 'dark')) {
        document.documentElement.setAttribute('data-theme', e.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      observer.disconnect();
      window.removeEventListener('storage', onStorage);
    };
  }, []);
  return theme;
}
