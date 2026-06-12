import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

const backendPort = process.env.BACKEND_PORT ?? '8000';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			'/v1': `http://localhost:${backendPort}`
		}
	}
});
