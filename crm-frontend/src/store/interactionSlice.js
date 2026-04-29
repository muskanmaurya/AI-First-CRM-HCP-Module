import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const todayIso = () => new Date().toISOString().split('T')[0]

const createEmptyFormDraft = () => ({
	hcpName: '',
	interactionType: 'Meeting',
	interactionDate: todayIso(),
	interactionTime: '',
	attendees: [],
	topicsDiscussed: '',
	materialsShared: [],
	samplesDistributed: [],
	hcpSentiment: 'Neutral',
	outcomes: '',
	followUpActions: '',
})

const normalizeList = (value) => {
	if (Array.isArray(value)) {
		return value.map((item) => String(item).trim()).filter(Boolean)
	}
	if (typeof value === 'string') {
		return value
			.split(/[\n,]/)
			.map((item) => item.trim())
			.filter(Boolean)
	}
	return []
}

const normalizeFormDraft = (draft = {}) => ({
	...createEmptyFormDraft(),
	...draft,
	attendees: normalizeList(draft.attendees),
	materialsShared: normalizeList(draft.materialsShared),
	samplesDistributed: normalizeList(draft.samplesDistributed),
})

const formFieldMap = {
	hcp_name: 'hcpName',
	interaction_date: 'interactionDate',
	interaction_type: 'interactionType',
	time: 'interactionTime',
	attendees: 'attendees',
	topics: 'topicsDiscussed',
	materials: 'materialsShared',
	samples: 'samplesDistributed',
	sentiment: 'hcpSentiment',
	outcomes: 'outcomes',
	follow_up: 'followUpActions',
}

const listFields = new Set(['attendees', 'materialsShared', 'samplesDistributed'])

const normalizeIncomingAiUpdates = (updates = {}) => {
	const normalized = {}
	Object.entries(updates).forEach(([rawKey, rawValue]) => {
		const mappedKey = formFieldMap[rawKey] ?? rawKey
		if (!mappedKey) return
		if (listFields.has(mappedKey)) {
			normalized[mappedKey] = normalizeList(rawValue)
			return
		}
		normalized[mappedKey] = rawValue
	})
	return normalized
}

const initialState = {
	interactions: [],
	sessions: [],
	currentSessionId: null,
	messages: [],
	loading: 'idle',
	formDraft: createEmptyFormDraft(),
	aiHighlightedFields: {},
}

export const fetchInteractions = createAsyncThunk(
	'interactions/fetchInteractions',
	async (hcpName, { rejectWithValue }) => {
		try {
			const { data } = await axios.get(
				`${API_BASE_URL}/history/${encodeURIComponent(hcpName)}`,
			)

			return data.records ?? []
		} catch (error) {
			return rejectWithValue(
				error?.response?.data?.detail ?? error.message ?? 'Failed to fetch interactions',
			)
		}
	},
)

export const addInteraction = createAsyncThunk(
	'interactions/addInteraction',
	async (interactionPayload, { rejectWithValue }) => {
		try {
			const { data } = await axios.post(
				`${API_BASE_URL}/manual-log`,
				interactionPayload,
			)

			return data.interaction
		} catch (error) {
			return rejectWithValue(
				error?.response?.data?.detail ?? error.message ?? 'Failed to add interaction',
			)
		}
	},
)

export const fetchSessions = createAsyncThunk('interactions/fetchSessions', async (_, { rejectWithValue }) => {
	try {
		const { data } = await axios.get(`${API_BASE_URL}/sessions`)
		return data.sessions ?? []
	} catch (err) {
		return rejectWithValue(err?.response?.data?.detail ?? err.message ?? 'Failed to fetch sessions')
	}
})

export const createSession = createAsyncThunk('interactions/createSession', async ({ sessionId, title }, { rejectWithValue }) => {
	try {
		const { data } = await axios.post(`${API_BASE_URL}/sessions`, { session_id: sessionId, title })
		return data
	} catch (err) {
		return rejectWithValue(err?.response?.data?.detail ?? err.message ?? 'Failed to create session')
	}
})

export const fetchSessionMessages = createAsyncThunk('interactions/fetchSessionMessages', async (sessionId, { rejectWithValue }) => {
	try {
		const { data } = await axios.get(`${API_BASE_URL}/sessions/${sessionId}/messages`)
		return { sessionId, messages: data.messages ?? [] }
	} catch (err) {
		return rejectWithValue(err?.response?.data?.detail ?? err.message ?? 'Failed to fetch messages')
	}
})

export const postChatMessage = createAsyncThunk('interactions/postChatMessage', async ({ sessionId, message }, { rejectWithValue }) => {
	try {
		const { data } = await axios.post(`${API_BASE_URL}/chat`, { session_id: sessionId, message })
		return data
	} catch (err) {
		return rejectWithValue(err?.response?.data?.detail ?? err.message ?? 'Failed to post chat message')
	}
})

const interactionSlice = createSlice({
	name: 'interactions',
	initialState,
	reducers: {
		setCurrentSession(state, action) {
			state.currentSessionId = action.payload
		},
		clearCurrentSession(state) {
			state.currentSessionId = null
			state.messages = []
		},
		setFormField(state, action) {
			const { field, value } = action.payload
			if (Object.prototype.hasOwnProperty.call(state.formDraft, field)) {
				state.formDraft[field] = value
				delete state.aiHighlightedFields[field]
			}
		},
		addFormListItem(state, action) {
			const { field, value } = action.payload
			if (!Array.isArray(state.formDraft[field])) return
			const cleaned = String(value ?? '').trim()
			if (!cleaned) return
			if (!state.formDraft[field].includes(cleaned)) {
				state.formDraft[field].push(cleaned)
			}
		},
		removeFormListItem(state, action) {
			const { field, index } = action.payload
			if (!Array.isArray(state.formDraft[field])) return
			state.formDraft[field].splice(index, 1)
		},
		setFormDraft(state, action) {
			state.formDraft = normalizeFormDraft(action.payload)
		},
		populateFormDraftFromSummary(state, action) {
			state.formDraft = normalizeFormDraft({
				...state.formDraft,
				...action.payload,
			})
		},
		applyAiFormUpdates(state, action) {
			const updates = normalizeIncomingAiUpdates(action.payload)
			Object.entries(updates).forEach(([field, value]) => {
				if (!Object.prototype.hasOwnProperty.call(state.formDraft, field)) return
				state.formDraft[field] = value
				state.aiHighlightedFields[field] = Date.now()
			})
		},
		clearAiFieldHighlight(state, action) {
			const field = action.payload
			if (!field) return
			delete state.aiHighlightedFields[field]
		},
		clearFormDraft(state) {
			state.formDraft = createEmptyFormDraft()
			state.aiHighlightedFields = {}
		},
	},
	extraReducers: (builder) => {
		builder
			.addCase(fetchInteractions.pending, (state) => {
				state.loading = 'loading'
			})
			.addCase(fetchInteractions.fulfilled, (state, action) => {
				state.loading = 'succeeded'
				state.interactions = action.payload
			})
			.addCase(fetchInteractions.rejected, (state) => {
				state.loading = 'failed'
			})
			.addCase(addInteraction.pending, (state) => {
				state.loading = 'loading'
			})
			.addCase(addInteraction.fulfilled, (state, action) => {
				state.loading = 'succeeded'
				state.interactions.unshift(action.payload)
			})
			.addCase(addInteraction.rejected, (state) => {
				state.loading = 'failed'
			})
			.addCase(fetchSessions.pending, (state) => {
				state.loading = 'loading'
			})
			.addCase(fetchSessions.fulfilled, (state, action) => {
				state.loading = 'succeeded'
				state.sessions = action.payload
			})
			.addCase(fetchSessions.rejected, (state) => {
				state.loading = 'failed'
			})
			.addCase(createSession.pending, (state) => {
				state.loading = 'loading'
			})
			.addCase(createSession.fulfilled, (state, action) => {
				state.loading = 'succeeded'
				const s = { id: action.payload.session_id, title: action.payload.title, created_at: new Date().toISOString() }
				state.sessions.unshift(s)
				state.currentSessionId = action.payload.session_id
				state.messages = []
			})
			.addCase(createSession.rejected, (state) => {
				state.loading = 'failed'
			})
			.addCase(fetchSessionMessages.pending, (state) => {
				state.loading = 'loading'
			})
			.addCase(fetchSessionMessages.fulfilled, (state, action) => {
				state.loading = 'succeeded'
				if (state.currentSessionId === action.payload.sessionId) {
					state.messages = action.payload.messages
				}
			})
			.addCase(fetchSessionMessages.rejected, (state) => {
				state.loading = 'failed'
			})
			.addCase(postChatMessage.pending, (state) => {
				state.loading = 'loading'
			})
			.addCase(postChatMessage.fulfilled, (state, action) => {
				state.loading = 'succeeded'
				const sessionId = action.payload.session_id ?? action.payload.sessionId ?? null
				if (sessionId) {
					state.currentSessionId = sessionId
					const assistant = action.payload.response ?? ''
					const structuredResponse = action.payload.structured_response ?? null
					state.messages.push({ role: 'user', content: action.meta.arg.message })
					state.messages.push({ role: 'assistant', content: assistant, structured_response: structuredResponse })
				}
			})
			.addCase(postChatMessage.rejected, (state) => {
				state.loading = 'failed'
			})
	},
})

export const {
	setCurrentSession,
	clearCurrentSession,
	setFormField,
	addFormListItem,
	removeFormListItem,
	setFormDraft,
	populateFormDraftFromSummary,
	applyAiFormUpdates,
	clearAiFieldHighlight,
	clearFormDraft,
} = interactionSlice.actions

export const selectFormDraft = (state) => state.interactions.formDraft
export const selectAiHighlightedFields = (state) => state.interactions.aiHighlightedFields

export default interactionSlice.reducer
