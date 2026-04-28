import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const initialState = {
	interactions: [],
	sessions: [],
	currentSessionId: null,
	messages: [],
	loading: 'idle',
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
				// prepend new session locally; server returns session_id and title
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
					// append assistant response to messages
					const assistant = action.payload.response ?? ''
					state.messages.push({ role: 'user', content: action.meta.arg.message })
					state.messages.push({ role: 'assistant', content: assistant })
				}
			})
			.addCase(postChatMessage.rejected, (state) => {
				state.loading = 'failed'
			})
	},
})

export const { setCurrentSession, clearCurrentSession } = interactionSlice.actions

export default interactionSlice.reducer
