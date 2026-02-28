const API_BASE = 'http://localhost:8000/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`, {
		headers: { 'Content-Type': 'application/json', ...options?.headers },
		...options
	});
	if (!res.ok) {
		const error = await res.json().catch(() => ({ detail: res.statusText }));
		throw new Error(error.detail || `HTTP ${res.status}`);
	}
	return res.json();
}

// ── Types ────────────────────────────────────────────────

export interface CategoryResponse {
	id: number;
	session_id: number;
	name: string;
	display_name: string | null;
	family_id: number | null;
	family_name: string | null;
	family_display_name: string | null;
	family_type: string | null;
	position: number;
	total_minutes: number;
}

export interface SessionResponse {
	id: number;
	year: number;
	season: string;
	label: string | null;
	start_date: string | null;
	end_date: string | null;
	is_active: boolean;
	source_file: string | null;
	created_at: string | null;
	categories: CategoryResponse[];
	total_minutes: number;
	days_logged: number;
}

export interface FamilyResponse {
	id: number;
	name: string;
	display_name: string | null;
	description: string | null;
	color: string | null;
	family_type: string | null;
	category_count: number;
	total_minutes: number;
}

export interface ImportCategoryPreview {
	name: string;
	display_name: string | null;
	auto_family: string | null;
	family_display_name: string | null;
	is_new_family: boolean;
	source_columns: string[];
}

export interface ImportPreviewResponse {
	preview_id: string;
	session_year: number;
	session_season: string;
	session_label: string;
	row_count: number;
	date_range: string[];
	categories: ImportCategoryPreview[];
	text_row_count: number;
	warnings: string[];
}

export interface DBInfoResponse {
	db_path: string;
	db_size_bytes: number;
	session_count: number;
	observation_count: number;
	text_entry_count: number;
}

export interface SettingResponse {
	key: string;
	value: string;
}

export interface TimerEntryResponse {
	id: number;
	session_id: number;
	category_id: number;
	category_name: string | null;
	date: string;
	start_time: string;
	end_time: string | null;
	pause_start: string | null;
	total_paused_seconds: number;
	duration_minutes: number | null;
	is_active: boolean;
	is_paused: boolean;
	description: string | null;
	location: string | null;
}

export interface ManualEntryResponse {
	id: number;
	session_id: number;
	category_id: number;
	category_name: string | null;
	date: string;
	duration_minutes: number;
	description: string | null;
	location: string | null;
	created_at: string | null;
}

export interface ObservationResponse {
	id: number;
	category_id: number;
	category_name: string | null;
	minutes: number;
	source: string | null;
}

export interface DailyActivityResponse {
	date: string;
	total_minutes: number;
	timer_entries: TimerEntryResponse[];
	manual_entries: ManualEntryResponse[];
	observations: ObservationResponse[];
}

export interface StreakResponse {
	current: number;
	longest: number;
}

export interface CategoryGroupResponse {
	id: number;
	name: string;
	display_name: string | null;
	description: string | null;
	color: string | null;
	is_auto: boolean;
	member_count: number;
	total_minutes: number;
}

export interface BubbleCategoryData {
	category_id: number;
	name: string;
	merge_key: string;
	total_minutes: number;
	session_label: string | null;
}

export interface BubbleGroupData {
	group_id: number | null;
	name: string;
	color: string | null;
	is_auto: boolean;
	categories: BubbleCategoryData[];
	total_minutes: number;
}

export interface BubbleDataResponse {
	groups: BubbleGroupData[];
	total_minutes: number;
}

// ── Analytics Types ──────────────────────────────────────

export interface AnalyticsOverviewResponse {
	total_minutes: number;
	days_tracked: number;
	daily_average: number;
	active_categories: number;
}

export interface DailyCategoryData {
	name: string;
	minutes: number;
	color: string | null;
}

export interface DailySeriesPoint {
	date: string;
	total_minutes: number;
	categories: DailyCategoryData[];
}

export interface CategoryBreakdownItem {
	name: string;
	display_name: string | null;
	family_name: string | null;
	color: string | null;
	total_minutes: number;
	session_count: number;
	session_label: string | null;
}

export interface HeatmapPoint {
	date: string;
	day_of_week: number;
	total_minutes: number;
}

export interface SessionGroupData {
	name: string;
	minutes: number;
	color: string | null;
}

export interface SessionComparisonItem {
	session_id: number;
	label: string;
	year: number;
	season: string;
	total_minutes: number;
	days_logged: number;
	groups: SessionGroupData[];
}

// ── Chat Types ───────────────────────────────────────────

export interface ChatContextInfo {
	summary: string;
	sessions_included: string[];
	categories_included: string[];
	date_range: (string | null)[];
	data_points: number;
	context_preview: string | null;
}

export interface ChatApprovalResponse {
	approval_id: string;
	user_message: string;
	context_info: ChatContextInfo;
}

export interface ChatMessageResponse {
	id: number | null;
	role: string;
	content: string;
	created_at: string | null;
}

export interface ChatStatusResponse {
	has_api_key: boolean;
	selected_model: string;
	available_models: { id: string; name: string }[];
}

// ── Projects Types ───────────────────────────────────────

export interface ProjectSessionEntry {
	session_id: number;
	session_label: string | null;
	year: number;
	season: string;
	total_minutes: number;
	active_days: number;
	ai_description: string | null;
}

export interface ProjectFamilyTimeline {
	family_id: number;
	family_name: string;
	display_name: string | null;
	family_type: string | null;
	color: string | null;
	total_minutes: number;
	sessions: ProjectSessionEntry[];
}

export interface ProjectTimelineResponse {
	families: ProjectFamilyTimeline[];
	sessions: { id: number; label: string | null; year: number; season: string }[];
}

export interface DescribeResponse {
	family_id: number;
	session_id: number;
	description: string;
}

// ── Research Projects Types ──────────────────────────────

export interface GitHubRepoInfo {
	full_name: string;
	name: string;
	description: string | null;
	language: string | null;
	stars: number;
	html_url: string | null;
	readme_excerpt: string | null;
	recent_commits: { sha: string; message: string; date: string }[];
}

export interface ResearchSessionEntry {
	session_id: number;
	session_label: string | null;
	year: number;
	season: string;
	total_minutes: number;
	active_days: number;
	ai_description: string | null;
	text_entries_count: number;
}

export interface ResearchFamilyDetail {
	family_id: number;
	family_name: string;
	display_name: string | null;
	color: string | null;
	total_minutes: number;
	sessions: ResearchSessionEntry[];
	github_repos: GitHubRepoInfo[];
	linked_repo_count: number;
}

export interface ResearchFamilyListItem {
	family_id: number;
	family_name: string;
	display_name: string | null;
	color: string | null;
	total_minutes: number;
	session_count: number;
	github_linked: boolean;
}

export interface ResearchFamiliesResponse {
	families: ResearchFamilyListItem[];
	github_username: string | null;
}

export interface EnrichedDescribeResponse {
	family_id: number;
	session_id: number;
	description: string;
	github_context_used: boolean;
}

// ── Group Types ─────────────────────────────────────────

export interface GroupSummary {
	group_type: string;
	label: string;
	family_count: number;
	total_minutes: number;
}

export interface GroupFamilyItem {
	family_id: number;
	family_name: string;
	display_name: string | null;
	color: string | null;
	total_minutes: number;
	sessions: ResearchSessionEntry[];
	github_repos: GitHubRepoInfo[];
	linked_repo_count: number;
}

export interface GroupListResponse {
	groups: GroupSummary[];
	github_username: string | null;
}

export interface GroupDetailResponse {
	group_type: string;
	label: string;
	families: GroupFamilyItem[];
	github_username: string | null;
}

export interface AnalyticsFilters {
	session_ids?: number[];
	from_date?: string;
	to_date?: string;
	week_number?: number;
}

function buildAnalyticsQs(filters?: AnalyticsFilters): string {
	if (!filters) return '';
	const params = new URLSearchParams();
	if (filters.session_ids?.length) params.set('session_ids', filters.session_ids.join(','));
	if (filters.from_date) params.set('from_date', filters.from_date);
	if (filters.to_date) params.set('to_date', filters.to_date);
	if (filters.week_number != null) params.set('week_number', String(filters.week_number));
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

// ── API Functions ────────────────────────────────────────

export const api = {
	// Sessions
	getSessions: () => request<{ sessions: SessionResponse[] }>('/sessions'),
	getSession: (id: number) => request<SessionResponse>(`/sessions/${id}`),
	getActiveSession: () => request<SessionResponse | null>('/sessions/active'),

	// Categories
	getCategories: (sessionId: number) =>
		request<CategoryResponse[]>(`/sessions/${sessionId}/categories`),

	// Categories
	addCategory: (sessionId: number, data: { name: string; display_name?: string; family?: string }) =>
		request<CategoryResponse>(`/sessions/${sessionId}/categories`, {
			method: 'POST',
			body: JSON.stringify(data),
		}),
	updateCategory: (categoryId: number, data: { family_id?: number; display_name?: string; name?: string }) =>
		request<CategoryResponse>(`/categories/${categoryId}`, {
			method: 'PUT',
			body: JSON.stringify(data),
		}),
	deleteCategory: (categoryId: number) =>
		request<Record<string, unknown>>(`/categories/${categoryId}`, {
			method: 'DELETE',
		}),

	// Families
	getFamilies: () => request<FamilyResponse[]>('/families'),
	createFamily: (data: { name: string; display_name?: string; color?: string; family_type?: string }) =>
		request<FamilyResponse>('/families', {
			method: 'POST',
			body: JSON.stringify(data),
		}),
	updateFamily: (familyId: number, data: { name?: string; display_name?: string; description?: string; color?: string; family_type?: string }) =>
		request<FamilyResponse>(`/families/${familyId}`, {
			method: 'PUT',
			body: JSON.stringify(data),
		}),
	deleteFamily: (familyId: number) =>
		request<{ deleted: boolean; categories_unlinked: number }>(`/families/${familyId}`, {
			method: 'DELETE',
		}),

	// Import
	importPreview: async (studyCsv: File, textCsv?: File): Promise<ImportPreviewResponse> => {
		const form = new FormData();
		form.append('study_csv', studyCsv);
		if (textCsv) form.append('text_csv', textCsv);

		const res = await fetch(`${API_BASE}/import/preview`, { method: 'POST', body: form });
		if (!res.ok) {
			const error = await res.json().catch(() => ({ detail: res.statusText }));
			throw new Error(error.detail || `HTTP ${res.status}`);
		}
		return res.json();
	},

	importConfirm: (previewId: string) =>
		request<Record<string, unknown>>('/import/confirm', {
			method: 'POST',
			body: JSON.stringify({ preview_id: previewId })
		}),

	// Settings
	getSettings: () => request<SettingResponse[]>('/settings'),
	updateSetting: (key: string, value: string) =>
		request<SettingResponse>(`/settings/${key}`, {
			method: 'PUT',
			body: JSON.stringify({ value })
		}),
	getDBInfo: () => request<DBInfoResponse>('/settings/db-info'),

	// Timers
	getActiveTimers: () => request<TimerEntryResponse[]>('/timers/active'),
	startTimer: (categoryId: number) =>
		request<TimerEntryResponse>('/timers/start', {
			method: 'POST',
			body: JSON.stringify({ category_id: categoryId })
		}),
	pauseTimer: (id: number) =>
		request<TimerEntryResponse>(`/timers/${id}/pause`, { method: 'POST' }),
	resumeTimer: (id: number) =>
		request<TimerEntryResponse>(`/timers/${id}/resume`, { method: 'POST' }),
	stopTimer: (id: number, description?: string, location?: string) =>
		request<TimerEntryResponse>(`/timers/${id}/stop`, {
			method: 'POST',
			body: JSON.stringify({ description: description || null, location: location || null })
		}),
	discardTimer: (id: number) =>
		request<Record<string, unknown>>(`/timers/${id}`, { method: 'DELETE' }),

	// Manual Entries
	createManualEntry: (data: {
		category_id: number;
		date: string;
		duration_minutes: number;
		description?: string;
		location?: string;
	}) =>
		request<ManualEntryResponse>('/manual-entries', {
			method: 'POST',
			body: JSON.stringify(data)
		}),
	getManualEntries: (date?: string, sessionId?: number) => {
		const params = new URLSearchParams();
		if (date) params.set('date', date);
		if (sessionId) params.set('session_id', String(sessionId));
		const qs = params.toString();
		return request<ManualEntryResponse[]>(`/manual-entries${qs ? `?${qs}` : ''}`);
	},
	deleteManualEntry: (id: number) =>
		request<Record<string, unknown>>(`/manual-entries/${id}`, { method: 'DELETE' }),

	// Daily
	getDailyActivity: (date: string) =>
		request<DailyActivityResponse>(`/daily/${date}`),
	getStreak: () => request<StreakResponse>('/daily/streak/current'),

	// Sessions (create)
	createSession: (data: {
		year: number;
		season: string;
		label?: string;
		categories?: { name: string; display_name?: string; family?: string }[];
		continue_from_session_id?: number;
	}) =>
		request<SessionResponse>('/sessions', {
			method: 'POST',
			body: JSON.stringify(data)
		}),
	updateSession: (id: number, data: { label?: string; start_date?: string; end_date?: string; is_active?: boolean }) =>
		request<SessionResponse>(`/sessions/${id}`, {
			method: 'PUT',
			body: JSON.stringify(data)
		}),

	// Groups
	getGroups: () => request<CategoryGroupResponse[]>('/groups'),
	getBubbleData: () => request<BubbleDataResponse>('/groups/bubble-data'),
	createGroup: (data: { name: string; display_name?: string; description?: string; color?: string }) =>
		request<Record<string, unknown>>('/groups', {
			method: 'POST',
			body: JSON.stringify(data)
		}),
	autoGenerateGroups: () =>
		request<Record<string, unknown>>('/groups/auto-generate', { method: 'POST' }),
	addGroupMembers: (groupId: number, categoryIds: number[]) =>
		request<Record<string, unknown>>(`/groups/${groupId}/members`, {
			method: 'POST',
			body: JSON.stringify({ category_ids: categoryIds })
		}),
	removeGroupMembers: (groupId: number, categoryIds: number[]) =>
		request<Record<string, unknown>>(`/groups/${groupId}/members`, {
			method: 'DELETE',
			body: JSON.stringify({ category_ids: categoryIds })
		}),

	// Batch Import
	batchImport: (dataDir?: string) =>
		request<{ imported: number; errors: { file: string; error: string }[]; sessions: Record<string, unknown>[] }>('/import/batch', {
			method: 'POST',
			body: JSON.stringify(dataDir ? { data_dir: dataDir } : {})
		}),

	// Analytics
	getAnalyticsOverview: (filters?: AnalyticsFilters) =>
		request<AnalyticsOverviewResponse>(`/analytics/overview${buildAnalyticsQs(filters)}`),
	getAnalyticsDaily: (filters?: AnalyticsFilters) =>
		request<DailySeriesPoint[]>(`/analytics/daily${buildAnalyticsQs(filters)}`),
	getAnalyticsCategories: (filters?: AnalyticsFilters) =>
		request<CategoryBreakdownItem[]>(`/analytics/categories${buildAnalyticsQs(filters)}`),
	getAnalyticsHeatmap: (filters?: AnalyticsFilters) =>
		request<HeatmapPoint[]>(`/analytics/heatmap${buildAnalyticsQs(filters)}`),
	getAnalyticsSessions: () =>
		request<SessionComparisonItem[]>(`/analytics/sessions`),

	// Chat
	getChatStatus: () => request<ChatStatusResponse>('/chat/status'),
	getChatHistory: () => request<ChatMessageResponse[]>('/chat/history'),
	sendChatQuery: (message: string) =>
		request<ChatApprovalResponse>('/chat/query', {
			method: 'POST',
			body: JSON.stringify({ message })
		}),
	rejectChatQuery: (approvalId: string) =>
		request<Record<string, unknown>>('/chat/reject', {
			method: 'POST',
			body: JSON.stringify({ approval_id: approvalId })
		}),
	clearChatHistory: () =>
		request<Record<string, unknown>>('/chat/history', { method: 'DELETE' }),
	saveApiKey: (apiKey: string) =>
		request<Record<string, unknown>>('/chat/api-key', {
			method: 'POST',
			body: JSON.stringify({ api_key: apiKey })
		}),
	deleteApiKey: () =>
		request<Record<string, unknown>>('/chat/api-key', { method: 'DELETE' }),
	setChatModel: (modelId: string) =>
		request<Record<string, unknown>>('/chat/model', {
			method: 'PUT',
			body: JSON.stringify({ model_id: modelId })
		}),

	// Projects (legacy)
	getProjectTimeline: () =>
		request<ProjectTimelineResponse>('/projects/timeline'),
	generateDescription: (familyId: number, sessionId: number) =>
		request<DescribeResponse>('/projects/describe', {
			method: 'POST',
			body: JSON.stringify({ family_id: familyId, session_id: sessionId })
		}),

	// Project Groups
	getProjectGroups: () =>
		request<GroupListResponse>('/projects/groups'),
	getGroupDetail: (groupType: string) =>
		request<GroupDetailResponse>(`/projects/group/${groupType}`),

	// Research Projects
	getResearchFamilies: () =>
		request<ResearchFamiliesResponse>('/projects/research'),
	getResearchFamilyDetail: (familyId: number) =>
		request<ResearchFamilyDetail>(`/projects/research/${familyId}`),
	generateEnrichedDescription: (familyId: number, sessionId: number, includeGithub: boolean = true) =>
		request<EnrichedDescribeResponse>('/projects/describe/enriched', {
			method: 'POST',
			body: JSON.stringify({ family_id: familyId, session_id: sessionId, include_github: includeGithub })
		}),
	searchGithubRepos: () =>
		request<{ repos: GitHubRepoInfo[] }>('/projects/github/search', { method: 'POST' }),
	linkGithubRepo: (familyId: number, repoFullName: string) =>
		request<Record<string, unknown>>('/projects/github/link', {
			method: 'PUT',
			body: JSON.stringify({ family_id: familyId, repo_full_name: repoFullName })
		}),
	unlinkGithubRepo: (familyId: number, repoFullName: string) =>
		request<Record<string, unknown>>('/projects/github/unlink', {
			method: 'POST',
			body: JSON.stringify({ family_id: familyId, repo_full_name: repoFullName })
		}),
	clearGithubCache: () =>
		request<Record<string, unknown>>('/projects/github/clear-cache', {
			method: 'POST'
		}),
};
