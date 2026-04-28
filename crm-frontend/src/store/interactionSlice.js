import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const initialState = {
	interactions: [],
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

const interactionSlice = createSlice({
	name: 'interactions',
	initialState,
	reducers: {},
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
	},
})

export default interactionSlice.reducer
