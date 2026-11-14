// Only the explicitly requested demo mode can activate API mocks.
export const IS_DEMO = import.meta.env.MODE === 'demo' && import.meta.env.VITE_USE_MOCKS === 'true';
