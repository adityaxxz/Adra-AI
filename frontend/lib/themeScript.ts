// Plain module (no 'use client') so the server layout can inline the script as a string.
export const THEME_KEY = 'adra_theme';

/** Runs inline in <head> before the page paints: saved choice, else the OS setting; follows OS changes until the user picks. */
export const THEME_INIT_SCRIPT = `(function(){try{var d=document.documentElement,k='${THEME_KEY}',m=window.matchMedia('(prefers-color-scheme: light)');var s=localStorage.getItem(k);d.setAttribute('data-theme',s==='light'||s==='dark'?s:(m.matches?'light':'dark'));m.addEventListener('change',function(e){var t=localStorage.getItem(k);if(t!=='light'&&t!=='dark')d.setAttribute('data-theme',e.matches?'light':'dark');});}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

