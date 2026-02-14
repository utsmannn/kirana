import { goto } from '$app/navigation';
import { browser } from '$app/environment';
import { adminToken, apiKey } from './stores.svelte';

const API_BASE = '/v1';

export class ApiError extends Error {
	status: number;
	body: unknown;

	constructor(status: number, message: string, body?: unknown) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.body = body;
	}
}

function handleUnauthorized() {
	if (!browser) return;
	// Clear auth state
	adminToken.value = null;
	apiKey.value = '';
	// Redirect to login
	goto('/login');
}

async function request<T>(
	path: string,
	options: RequestInit & { token?: string } = {}
): Promise<T> {
	const { token, ...fetchOptions } = options;
	const headers = new Headers(fetchOptions.headers);

	if (token) {
		headers.set('Authorization', `Bearer ${token}`);
	}

	if (fetchOptions.body && typeof fetchOptions.body === 'string') {
		headers.set('Content-Type', 'application/json');
	}

	const response = await fetch(`${API_BASE}${path}`, {
		...fetchOptions,
		headers
	});

	if (!response.ok) {
		// Handle 401 Unauthorized - redirect to login
		if (response.status === 401) {
			handleUnauthorized();
		}

		let body: unknown;
		try {
			body = await response.json();
		} catch {
			body = await response.text();
		}
		const message =
			typeof body === 'object' && body !== null && 'detail' in body
				? String((body as { detail: string }).detail)
				: `Request failed with status ${response.status}`;
		throw new ApiError(response.status, message, body);
	}

	if (response.status === 204) {
		return undefined as T;
	}

	return response.json() as Promise<T>;
}

// ---------- Admin ----------

export interface AdminLoginResponse {
	token: string;
}

export function adminLogin(password: string): Promise<AdminLoginResponse> {
	return request('/admin/login', {
		method: 'POST',
		body: JSON.stringify({ password })
	});
}

export function adminVerify(token: string): Promise<{ status: string }> {
	return request('/admin/verify', { token });
}

// ---------- Clients ----------

export interface Client {
	id: string;
	name: string;
	email: string;
	api_key: string;
	created_at: string;
	is_active: boolean;
}

export function createClient(name: string, email: string): Promise<Client> {
	return request('/clients/', {
		method: 'POST',
		body: JSON.stringify({ name, email })
	});
}

export function getClientMe(token: string): Promise<Client> {
	return request('/clients/me', { token });
}

// ---------- Config ----------

export interface AppConfig {
	model: string;
	temperature: number;
	max_tokens: number;
	thinking_mode: boolean;
	provider_api_key: string;
	provider_base_url: string;
	system_prompt: string;
	personality_slug: string;
	tools_enabled: boolean;
	[key: string]: unknown;
}

export function getConfig(token: string): Promise<AppConfig> {
	return request('/config/', { token });
}

export function updateConfig(token: string, data: Partial<AppConfig>): Promise<AppConfig> {
	return request('/config/', {
		method: 'PATCH',
		token,
		body: JSON.stringify(data)
	});
}

// ---------- Personalities ----------

export interface Personality {
	slug: string;
	name: string;
	description: string;
	system_prompt: string;
}

export interface PersonalitiesResponse {
	templates: Personality[];
}

export function getPersonalities(token: string): Promise<PersonalitiesResponse> {
	return request('/personalities/', { token });
}

export function getPersonality(token: string, slug: string): Promise<Personality> {
	return request(`/personalities/${slug}`, { token });
}

// ---------- Chat ----------

export interface ChatMessage {
	role: 'system' | 'user' | 'assistant';
	content: string;
}

export interface ChatRequest {
	model: string;
	messages: ChatMessage[];
	stream?: boolean;
	session_id?: string;
	stream_id?: string;
}

export async function* streamChat(
	token: string,
	data: ChatRequest
): AsyncGenerator<string, void, unknown> {
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		Authorization: `Bearer ${token}`
	};

	const response = await fetch(`${API_BASE}/chat/completions`, {
		method: 'POST',
		headers,
		body: JSON.stringify({ ...data, stream: true })
	});

	if (!response.ok) {
		// Handle 401 Unauthorized - redirect to login
		if (response.status === 401) {
			handleUnauthorized();
		}

		let body: unknown;
		try {
			body = await response.json();
		} catch {
			body = await response.text();
		}
		const message =
			typeof body === 'object' && body !== null && 'detail' in body
				? String((body as { detail: string }).detail)
				: `Chat request failed with status ${response.status}`;
		throw new ApiError(response.status, message, body);
	}

	const reader = response.body?.getReader();
	if (!reader) throw new Error('No readable stream');

	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;

		buffer += decoder.decode(value, { stream: true });
		const lines = buffer.split('\n');
		buffer = lines.pop() ?? '';

		for (const line of lines) {
			const trimmed = line.trim();
			if (!trimmed || !trimmed.startsWith('data: ')) continue;
			const payload = trimmed.slice(6);
			if (payload === '[DONE]') return;

			try {
				const parsed = JSON.parse(payload);
				// Skip stream_id event (client already has it)
				if (parsed.stream_id) continue;
				const content = parsed.choices?.[0]?.delta?.content;
				if (content) {
					yield content;
				}
			} catch {
				// skip unparseable chunks
			}
		}
	}
}

export function sendChat(
	token: string,
	data: ChatRequest
): Promise<{ choices: { message: ChatMessage }[] }> {
	return request('/chat/completions', {
		method: 'POST',
		token,
		body: JSON.stringify({ ...data, stream: false })
	});
}

export interface StreamChunksResponse {
	stream_id: string;
	chunks: string[];
	offset: number;
	total: number;
	done: boolean;
}

export function getStreamChunks(
	token: string,
	streamId: string,
	offset = 0
): Promise<StreamChunksResponse> {
	return request(`/chat/stream/${streamId}?offset=${offset}`, { token });
}

// ---------- Sessions ----------

export interface Session {
	id: string;
	name: string;
	message_count?: number;
	created_at: string;
	updated_at: string;
	[key: string]: unknown;
}

export interface PaginatedResponse<T> {
	items: T[];
	total: number;
	page: number;
	limit: number;
	pages: number;
}

export function getSessions(
	token: string,
	page = 1,
	limit = 20
): Promise<PaginatedResponse<Session>> {
	return request(`/sessions/?page=${page}&limit=${limit}`, { token });
}

export function getSession(token: string, id: string): Promise<Session> {
	return request(`/sessions/${id}`, { token });
}

export interface SessionCreate {
	name: string;
	channel_id?: string;
}

export function createSession(token: string, data: string | SessionCreate): Promise<Session> {
	const body = typeof data === 'string' ? { name: data } : data;
	return request('/sessions/', {
		method: 'POST',
		token,
		body: JSON.stringify(body)
	});
}

export function deleteSession(token: string, id: string): Promise<void> {
	return request(`/sessions/${id}`, { method: 'DELETE', token });
}

export interface SessionMessage {
	id: string;
	role: string;
	content: string;
	created_at: string;
	[key: string]: unknown;
}

export interface SessionMessagesResponse {
	messages: SessionMessage[];
	total: number;
	page: number;
	limit: number;
}

export function getSessionMessages(token: string, id: string): Promise<SessionMessagesResponse> {
	return request(`/sessions/${id}/messages`, { token });
}

// ---------- Knowledge ----------

export interface KnowledgeItem {
	id: string;
	title: string;
	content: string;
	content_type: string;
	created_at: string;
	updated_at: string;
	[key: string]: unknown;
}

export function getKnowledge(
	token: string,
	page = 1,
	limit = 20,
	search = ''
): Promise<PaginatedResponse<KnowledgeItem>> {
	const params = new URLSearchParams({ page: String(page), limit: String(limit) });
	if (search) params.set('search', search);
	return request(`/knowledge/?${params}`, { token });
}

export function createKnowledge(
	token: string,
	data: { title: string; content: string; content_type: string }
): Promise<KnowledgeItem> {
	return request('/knowledge/', {
		method: 'POST',
		token,
		body: JSON.stringify(data)
	});
}

export function updateKnowledge(
	token: string,
	id: string,
	data: { title: string; content: string }
): Promise<KnowledgeItem> {
	return request(`/knowledge/${id}`, {
		method: 'PATCH',
		token,
		body: JSON.stringify(data)
	});
}

export function deleteKnowledge(token: string, id: string): Promise<void> {
	return request(`/knowledge/${id}`, { method: 'DELETE', token });
}

// ---------- Usage ----------

export interface UsageData {
	total_requests: number;
	total_tokens: number;
	total_input_tokens: number;
	total_output_tokens: number;
	[key: string]: unknown;
}

export function getUsage(token: string): Promise<UsageData> {
	return request('/usage/', { token });
}

// ---------- Tools ----------

export interface Tool {
	name: string;
	description: string;
	[key: string]: unknown;
}

export interface ToolsResponse {
	tools: Tool[];
}

export function getTools(token: string): Promise<ToolsResponse> {
	return request('/tools/', { token });
}

// ---------- Providers ----------

export interface Provider {
	id: string;
	name: string;
	model: string;
	base_url: string | null;
	is_active: boolean;
	is_default: boolean;
	priority_order: number;
	created_at: string;
}

export interface ProvidersResponse {
	providers: Provider[];
	active_provider: Provider | null;
}

export interface ProviderCreate {
	name: string;
	model: string;
	api_key: string;
	base_url?: string;
}

export function getProviders(token: string): Promise<ProvidersResponse> {
	return request('/providers/', { token });
}

export function getProvider(token: string, id: string): Promise<Provider> {
	return request(`/providers/${id}`, { token });
}

export function createProvider(token: string, data: ProviderCreate): Promise<Provider> {
	return request('/providers/', {
		method: 'POST',
		token,
		body: JSON.stringify(data)
	});
}

export function updateProvider(token: string, id: string, data: Partial<ProviderCreate>): Promise<Provider> {
	return request(`/providers/${id}`, {
		method: 'PATCH',
		token,
		body: JSON.stringify(data)
	});
}

export function deleteProvider(token: string, id: string): Promise<void> {
	return request(`/providers/${id}`, { method: 'DELETE', token });
}

export function activateProvider(token: string, id: string): Promise<Provider> {
	return request(`/providers/${id}/activate`, {
		method: 'POST',
		token
	});
}

// ---------- Channels ----------

export interface Channel {
	id: string;
	name: string;
	provider_id: string;
	provider_name?: string;
	system_prompt: string | null;
	personality_name: string | null;
	is_default: boolean;
	created_at: string;
	// Embed fields
	embed_enabled?: boolean;
	embed_token?: string | null;
	embed_config?: Record<string, unknown>;
}

export interface EmbedConfig {
	public: boolean;
	save_history: boolean;
	regenerate_token?: boolean;
}

export interface EmbedConfigResponse {
	embed_enabled: boolean;
	embed_url?: string;
	public: boolean;
	save_history: boolean;
	has_token: boolean;
}

export interface ChannelsResponse {
	channels: Channel[];
	default_channel: Channel | null;
}

export interface ChannelCreate {
	name: string;
	provider_id: string;
	system_prompt?: string;
	personality_name?: string;
}

export function getChannels(token: string): Promise<ChannelsResponse> {
	return request('/channels/', { token });
}

export function getChannel(token: string, id: string): Promise<Channel> {
	return request(`/channels/${id}`, { token });
}

export function createChannel(token: string, data: ChannelCreate): Promise<Channel> {
	return request('/channels/', {
		method: 'POST',
		token,
		body: JSON.stringify(data)
	});
}

export function updateChannel(token: string, id: string, data: Partial<ChannelCreate>): Promise<Channel> {
	return request(`/channels/${id}`, {
		method: 'PATCH',
		token,
		body: JSON.stringify(data)
	});
}

export function deleteChannel(token: string, id: string): Promise<void> {
	return request(`/channels/${id}`, { method: 'DELETE', token });
}

export function setDefaultChannel(token: string, id: string): Promise<Channel> {
	return request(`/channels/${id}/set-default`, {
		method: 'POST',
		token
	});
}

// ---------- Embed Configuration ----------

export function getEmbedConfig(token: string, channelId: string): Promise<EmbedConfigResponse> {
	return request(`/channels/${channelId}/embed`, { token });
}

export function configureEmbed(
	token: string,
	channelId: string,
	config: EmbedConfig
): Promise<EmbedConfigResponse> {
	return request(`/channels/${channelId}/embed`, {
		method: 'POST',
		token,
		body: JSON.stringify(config)
	});
}

export function disableEmbed(token: string, channelId: string): Promise<void> {
	return request(`/channels/${channelId}/embed`, { method: 'DELETE', token });
}

// ---------- WebSocket Chat ----------

export interface WsMessage {
	type: 'stream_start' | 'chunk' | 'stream_end' | 'error';
	stream_id?: string;
	content?: string;
	message?: string;
	resumed?: boolean;
}

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

export interface WsChatOptions {
	token: string;
	onMessage: (msg: WsMessage) => void;
	onStatusChange?: (status: WsStatus) => void;
}

export class WsChat {
	private ws: WebSocket | null = null;
	private token: string;
	private onMessage: (msg: WsMessage) => void;
	private onStatusChange?: (status: WsStatus) => void;
	private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	private activeStreamId: string | null = null;
	private _status: WsStatus = 'disconnected';
	private connecting = false;

	constructor(options: WsChatOptions) {
		this.token = options.token;
		this.onMessage = options.onMessage;
		this.onStatusChange = options.onStatusChange;
	}

	get status(): WsStatus {
		return this._status;
	}

	get streamId(): string | null {
		return this.activeStreamId;
	}

	connect(): void {
		if (this.ws?.readyState === WebSocket.OPEN) return;
		if (this.connecting) return;

		this.connecting = true;
		this.setStatus('connecting');
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const wsUrl = `${protocol}//${window.location.host}/v1/chat/ws?token=${encodeURIComponent(this.token)}`;

		this.ws = new WebSocket(wsUrl);

		this.ws.onopen = () => {
			this.connecting = false;
			this.setStatus('connected');
			// If there was an active stream, try to resume
			if (this.activeStreamId) {
				this.resume(this.activeStreamId);
			}
		};

		this.ws.onmessage = (event) => {
			try {
				const msg: WsMessage = JSON.parse(event.data);
				if (msg.type === 'stream_start' && msg.stream_id) {
					this.activeStreamId = msg.stream_id;
				}
				if (msg.type === 'stream_end' || msg.type === 'error') {
					this.activeStreamId = null;
				}
				this.onMessage(msg);
			} catch {
				// ignore unparseable
			}
		};

		this.ws.onclose = () => {
			this.connecting = false;
			this.setStatus('disconnected');
			this.scheduleReconnect();
		};

		this.ws.onerror = () => {
			this.connecting = false;
		};
	}

	disconnect(): void {
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
		this.ws?.close();
		this.ws = null;
		this.setStatus('disconnected');
	}

	send(data: ChatRequest): void {
		if (this.ws?.readyState !== WebSocket.OPEN) return;
		this.ws.send(JSON.stringify({ action: 'chat', data }));
	}

	resume(streamId: string): void {
		this.activeStreamId = streamId;
		if (this.ws?.readyState !== WebSocket.OPEN) {
			this.connect();
			return;
		}
		this.ws.send(JSON.stringify({ action: 'resume', stream_id: streamId }));
	}

	private setStatus(status: WsStatus): void {
		this._status = status;
		this.onStatusChange?.(status);
	}

	private scheduleReconnect(): void {
		if (this.reconnectTimer) return;
		this.reconnectTimer = setTimeout(() => {
			this.reconnectTimer = null;
			if (this._status === 'disconnected') {
				this.connect();
			}
		}, 3000);
	}
}
