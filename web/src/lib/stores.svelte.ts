import { browser } from '$app/environment';

class PersistedStore<T> {
	private key: string;
	private _value: T;

	constructor(key: string, initial: T) {
		this.key = key;
		let stored: T = initial;
		if (browser) {
			try {
				const raw = localStorage.getItem(key);
				if (raw !== null) {
					stored = JSON.parse(raw);
				}
			} catch {
				// ignore parse errors
			}
		}
		this._value = $state(stored);
	}

	get value(): T {
		return this._value;
	}

	set value(v: T) {
		this._value = v;
		if (browser) {
			try {
				if (v === null || v === undefined) {
					localStorage.removeItem(this.key);
				} else {
					localStorage.setItem(this.key, JSON.stringify(v));
				}
			} catch {
				// ignore storage errors
			}
		}
	}
}

// Admin auth for panel access
export const adminToken = new PersistedStore<string | null>('kirana_admin_token', null);

// API key for all backend API calls (single-tenant mode)
export const apiKey = new PersistedStore<string>('kirana_api_key', 'kirana-default-api-key-change-me');
