interface ToastItem {
	id: number;
	message: string;
	type: 'success' | 'error' | 'info';
}

let toasts = $state<ToastItem[]>([]);
let nextId = 0;

export function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
	const id = nextId++;
	toasts.push({ id, message, type });
	setTimeout(() => {
		toasts = toasts.filter((t) => t.id !== id);
	}, 4000);
}

export function dismissToast(id: number) {
	toasts = toasts.filter((t) => t.id !== id);
}

export function getToasts(): ToastItem[] {
	return toasts;
}
