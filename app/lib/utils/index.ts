export const API_BASE_URL = import.meta.url.startsWith('http') ? new URL(import.meta.url).origin : Deno.env.get('API_BASE_URL') || 'http://localhost:8000';
