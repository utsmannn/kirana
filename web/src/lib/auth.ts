import { goto } from '$app/navigation';
import { base } from '$app/paths';
import { adminToken } from './stores.svelte';

export function requireAdmin(): boolean {
	if (!adminToken.value) {
		goto(`${base}/login`);
		return false;
	}
	return true;
}

export function logout(): void {
	adminToken.value = null;
	goto(`${base}/login`);
}
