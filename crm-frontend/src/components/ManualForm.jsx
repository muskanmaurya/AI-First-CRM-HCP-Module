import { useEffect, useMemo, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
	Calendar,
	Clock,
	Frown,
	Loader,
	Mic,
	Plus,
	Package2,
	Search,
	Send,
	Smile,
	Sparkles,
	User,
	Meh,
	X,
} from 'lucide-react'
import {
	addFormListItem,
	addInteraction,
	clearAiFieldHighlight,
	clearFormDraft,
	postChatMessage,
	removeFormListItem,
	selectAiHighlightedFields,
	selectFormDraft,
	setFormField,
} from '../store/interactionSlice'

const interactionTypes = ['Meeting', 'Email', 'Call', 'Virtual Meeting', 'Lunch', 'Conference', 'Other']

const sentimentOptions = [
	{ value: 'Positive', label: 'Positive', icon: Smile, emoji: '😄' },
	{ value: 'Neutral', label: 'Neutral', icon: Meh, emoji: '😐' },
	{ value: 'Negative', label: 'Negative', icon: Frown, emoji: '☹️' },
]

const buildSummary = (draft) => {
	const lines = []
	if (draft.topicsDiscussed) lines.push(`Topics Discussed: ${draft.topicsDiscussed}`)
	if (draft.attendees.length) lines.push(`Attendees: ${draft.attendees.join(', ')}`)
	if (draft.materialsShared.length) lines.push(`Materials Shared: ${draft.materialsShared.join(', ')}`)
	if (draft.samplesDistributed.length) lines.push(`Samples Distributed: ${draft.samplesDistributed.join(', ')}`)
	if (draft.hcpSentiment) lines.push(`HCP Sentiment: ${draft.hcpSentiment}`)
	if (draft.outcomes) lines.push(`Outcomes: ${draft.outcomes}`)
	if (draft.followUpActions) lines.push(`Follow-up Actions: ${draft.followUpActions}`)
	if (draft.interactionTime) lines.push(`Time: ${draft.interactionTime}`)
	return lines.join('\n\n') || 'Life Sciences CRM interaction logged.'
}

const ChipListEditor = ({ label, icon: Icon, value, tempValue, onTempValueChange, onAdd, onRemove, addLabel, placeholder }) => (
	<div className="space-y-2">
		{label ? (
			<div className="flex items-center gap-2 text-sm font-medium tracking-tight text-slate-700">
				<Icon className="h-4 w-4 text-slate-500" />
				<span>{label}</span>
			</div>
		) : null}
		<div className="flex gap-2">
			<input
				value={tempValue}
				onChange={(e) => onTempValueChange(e.target.value)}
				placeholder={placeholder}
				className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
			/>
			<button
				type="button"
				onClick={onAdd}
				className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-100"
			>
				<Plus className="h-4 w-4" />
				{addLabel}
			</button>
		</div>
		{value.length > 0 && (
			<div className="flex flex-wrap gap-2 pt-1">
				{value.map((item, index) => (
					<span key={`${item}-${index}`} className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 shadow-sm">
						{item}
						<button type="button" onClick={() => onRemove(index)} className="rounded-full p-0.5 text-slate-400 transition hover:bg-slate-200 hover:text-slate-700">
							<X className="h-3.5 w-3.5" />
						</button>
					</span>
				))}
			</div>
		)}
	</div>
)

const ManualForm = () => {
	const dispatch = useDispatch()
	const { loading, messages, currentSessionId, interactions } = useSelector((state) => state.interactions)
	const formDraft = useSelector(selectFormDraft)
	const aiHighlightedFields = useSelector(selectAiHighlightedFields)
	const [chatInput, setChatInput] = useState('')
	const [chatLoading, setChatLoading] = useState(false)
	const [chatError, setChatError] = useState('')
	const [formError, setFormError] = useState('')
	const [formSuccess, setFormSuccess] = useState(false)
	const [attendeeDraft, setAttendeeDraft] = useState('')
	const [materialDraft, setMaterialDraft] = useState('')
	const [sampleDraft, setSampleDraft] = useState('')
	const [splitRatio, setSplitRatio] = useState(55)
	const [isDesktop, setIsDesktop] = useState(() => (typeof window !== 'undefined' ? window.innerWidth >= 1024 : true))
	const messagesEndRef = useRef(null)
	const highlightTimeoutsRef = useRef({})
	const splitContainerRef = useRef(null)
	const isDraggingRef = useRef(false)

	const hcpOptions = useMemo(() => {
		const names = new Set()
		interactions.forEach((interaction) => {
			if (interaction?.hcp_name) names.add(interaction.hcp_name)
		})
		return Array.from(names)
	}, [interactions])

	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
	}, [messages])

	useEffect(() => {
		const handleResize = () => setIsDesktop(window.innerWidth >= 1024)
		handleResize()
		window.addEventListener('resize', handleResize)
		return () => window.removeEventListener('resize', handleResize)
	}, [])

	useEffect(() => {
		if (!isDesktop) return

		const handleMouseMove = (event) => {
			if (!isDraggingRef.current || !splitContainerRef.current) return
			const bounds = splitContainerRef.current.getBoundingClientRect()
			const next = ((event.clientX - bounds.left) / bounds.width) * 100
			setSplitRatio(Math.max(30, Math.min(70, next)))
		}

		const handleMouseUp = () => {
			isDraggingRef.current = false
			document.body.style.cursor = ''
			document.body.style.userSelect = ''
		}

		window.addEventListener('mousemove', handleMouseMove)
		window.addEventListener('mouseup', handleMouseUp)

		return () => {
			window.removeEventListener('mousemove', handleMouseMove)
			window.removeEventListener('mouseup', handleMouseUp)
		}
	}, [isDesktop])

	useEffect(() => {
		Object.keys(aiHighlightedFields).forEach((field) => {
			if (highlightTimeoutsRef.current[field]) return
			highlightTimeoutsRef.current[field] = setTimeout(() => {
				dispatch(clearAiFieldHighlight(field))
				delete highlightTimeoutsRef.current[field]
			}, 2000)
		})

		return () => {
			Object.values(highlightTimeoutsRef.current).forEach((timerId) => clearTimeout(timerId))
			highlightTimeoutsRef.current = {}
		}
	}, [aiHighlightedFields, dispatch])

	const fieldClass = (field, baseClass) => {
		if (!aiHighlightedFields[field]) return baseClass
		return `${baseClass} border-blue-400 ring-2 ring-blue-200 transition-all duration-500`
	}

	const startResizing = () => {
		if (!isDesktop) return
		isDraggingRef.current = true
		document.body.style.cursor = 'col-resize'
		document.body.style.userSelect = 'none'
	}

	const handleChatSend = async () => {
		if (!chatInput.trim()) return
		setChatError('')
		setChatLoading(true)
		try {
			await dispatch(
				postChatMessage({
					sessionId: currentSessionId,
					message: chatInput.trim(),
				}),
			).unwrap()
			setChatInput('')
		} catch (error) {
			setChatError(error || 'Unable to send message right now.')
		} finally {
			setChatLoading(false)
		}
	}

	const handleChatKeyPress = (e) => {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault()
			handleChatSend()
		}
	}

	const addAttendee = () => {
		dispatch(addFormListItem({ field: 'attendees', value: attendeeDraft }))
		setAttendeeDraft('')
	}

	const addMaterial = () => {
		dispatch(addFormListItem({ field: 'materialsShared', value: materialDraft }))
		setMaterialDraft('')
	}

	const addSample = () => {
		dispatch(addFormListItem({ field: 'samplesDistributed', value: sampleDraft }))
		setSampleDraft('')
	}

	const handleSubmit = async (e) => {
		e.preventDefault()
		setFormError('')
		setFormSuccess(false)

		if (!formDraft.hcpName.trim()) {
			setFormError('HCP Name is required.')
			return
		}

		if (!formDraft.interactionDate) {
			setFormError('Date is required.')
			return
		}

		try {
			await dispatch(
				addInteraction({
					hcp_name: formDraft.hcpName.trim(),
					interaction_date: formDraft.interactionDate,
					interaction_type: formDraft.interactionType,
					summary: buildSummary(formDraft),
					time: formDraft.interactionTime,
					attendees: formDraft.attendees,
					topics: formDraft.topicsDiscussed,
					materials: formDraft.materialsShared,
					samples: formDraft.samplesDistributed,
					sentiment: formDraft.hcpSentiment,
					outcomes: formDraft.outcomes,
					follow_up: formDraft.followUpActions,
				}),
			).unwrap()

			dispatch(clearFormDraft())
			setAttendeeDraft('')
			setMaterialDraft('')
			setSampleDraft('')
			setFormSuccess(true)
			setTimeout(() => setFormSuccess(false), 2500)
		} catch (error) {
			setFormError(error || 'Failed to save interaction. Please try again.')
		}
	}

	return (
		<div className="h-dvh w-full overflow-hidden bg-slate-50 text-slate-900">
			<div ref={splitContainerRef} className={`flex h-full min-h-0 overflow-hidden ${isDesktop ? 'flex-row' : 'flex-col'}`}>
				<div
					className={`flex h-full min-h-0 flex-col bg-white ${isDesktop ? 'border-r border-slate-200' : 'flex-1 border-b border-slate-200'}`}
					style={isDesktop ? { width: `${splitRatio}%` } : undefined}
				>
					<div className="border-b border-slate-200 bg-linear-to-r from-slate-50 to-blue-50 px-6 py-5">
						<h2 className="text-xl font-semibold tracking-tight text-slate-900">AI Assistant Chat</h2>
						<p className="text-sm text-slate-600">Chat with your healthcare AI to log interactions</p>
					</div>

					<div className="flex-1 overflow-y-auto px-6 py-5">
						{messages.length === 0 ? (
							<div className="flex h-full items-center justify-center text-center text-slate-500">
								<div>
									<div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-2xl shadow-sm">💬</div>
									<p className="font-medium tracking-tight text-slate-700">Start a conversation</p>
									<p className="mt-2 text-sm text-slate-500">Ask the AI to summarise or structure your interaction note.</p>
								</div>
							</div>
						) : (
							<div className="space-y-4">
								{messages.map((message, index) => (
									<div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
										<div className={`max-w-xl rounded-2xl border px-4 py-3 text-sm leading-relaxed shadow-sm ${message.role === 'user' ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-200 bg-slate-50 text-slate-800'}`}>
											{message.content}
										</div>
									</div>
								))}
								{chatLoading && (
									<div className="flex justify-start">
										<div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 shadow-sm">
											<div className="flex items-center gap-2">
												<Loader className="h-4 w-4 animate-spin" />
												<span>Thinking...</span>
											</div>
										</div>
									</div>
								)}
								<div ref={messagesEndRef} />
							</div>
						)}
					</div>

					<div className="border-t border-slate-200 bg-white px-6 py-5">
						{chatError && <p className="mb-3 text-sm text-red-600">{chatError}</p>}
						<div className="flex items-end gap-3">
							<textarea
								value={chatInput}
								onChange={(e) => setChatInput(e.target.value)}
								onKeyDown={handleChatKeyPress}
								placeholder="Type your message... (Shift+Enter for new line)"
								rows={3}
								className="min-h-22 flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:ring-2 focus:ring-blue-100"
							/>
							<button
								type="button"
								onClick={handleChatSend}
								disabled={chatLoading || !chatInput.trim()}
								className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
							>
								<Send className="h-5 w-5" />
							</button>
						</div>
					</div>
				</div>

				{/* Draggable Divider */}
				{isDesktop && (
					<div
						role="separator"
						aria-orientation="vertical"
						onMouseDown={startResizing}
						className="w-2 cursor-col-resize bg-slate-200/70 transition hover:bg-blue-200"
					/>
				)}

				<div
					className={`flex h-full min-h-0 flex-col bg-slate-50 ${!isDesktop ? 'flex-1' : ''}`}
					style={isDesktop ? { width: `${100 - splitRatio}%` } : undefined}
				>
					<div className="border-b border-slate-200 bg-linear-to-r from-slate-50 to-indigo-50 px-6 py-5">
						<h2 className="text-xl font-semibold tracking-tight text-slate-900">Log Interaction</h2>
						<p className="text-sm text-slate-600">Record structured Life Sciences CRM interaction details</p>
					</div>

					<form onSubmit={handleSubmit} className="flex h-full min-h-0 flex-col">
						<div className="flex-1 overflow-y-auto px-6 py-5">
							<div className="space-y-5">
						<div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
							<div className="mb-5 flex items-center gap-2 text-sm font-semibold tracking-tight text-slate-900">
								<User className="h-4 w-4 text-slate-500" />
								<span>Interaction Details</span>
							</div>

							<div className="grid gap-4">
								<div className="space-y-2">
									<label className="text-sm font-medium tracking-tight text-slate-700">HCP Name</label>
									<input
										list="hcp-name-options"
										value={formDraft.hcpName}
										onChange={(e) => dispatch(setFormField({ field: 'hcpName', value: e.target.value }))}
										placeholder="Search or select an HCP"
										className={fieldClass('hcpName', 'w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
									/>
									<datalist id="hcp-name-options">
										{hcpOptions.map((name) => (
											<option key={name} value={name} />
										))}
									</datalist>
								</div>

								<div className="grid gap-4 md:grid-cols-2">
									<div className="space-y-2">
										<label className="text-sm font-medium tracking-tight text-slate-700">Interaction Type</label>
										<select
											value={formDraft.interactionType}
											onChange={(e) => dispatch(setFormField({ field: 'interactionType', value: e.target.value }))}
											className={fieldClass('interactionType', 'w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
										>
											{interactionTypes.map((type) => (
												<option key={type} value={type}>{type}</option>
											))}
										</select>
									</div>

									<div className="space-y-2">
										<label className="text-sm font-medium tracking-tight text-slate-700">Date &amp; Time</label>
										<div className="grid grid-cols-2 gap-3">
											<div className="relative">
												<Calendar className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
												<input
													type="date"
													value={formDraft.interactionDate}
													onChange={(e) => dispatch(setFormField({ field: 'interactionDate', value: e.target.value }))}
													className={fieldClass('interactionDate', 'w-full rounded-2xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm shadow-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
												/>
											</div>
											<div className="relative">
												<Clock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
												<input
													type="time"
													value={formDraft.interactionTime}
													onChange={(e) => dispatch(setFormField({ field: 'interactionTime', value: e.target.value }))}
													className={fieldClass('interactionTime', 'w-full rounded-2xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm shadow-sm outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
												/>
											</div>
										</div>
									</div>
								</div>

								<div className="space-y-2">
									<label className="text-sm font-medium tracking-tight text-slate-700">Topics Discussed</label>
									<textarea
										value={formDraft.topicsDiscussed}
										onChange={(e) => dispatch(setFormField({ field: 'topicsDiscussed', value: e.target.value }))}
										placeholder="Summarize the discussion points in a clear professional note..."
										rows={5}
										className={fieldClass('topicsDiscussed', 'w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
									/>
									<button type="button" className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-100">
										<Mic className="h-4 w-4" />
										Summarize from Voice Note
									</button>
								</div>

								<div className={aiHighlightedFields.attendees ? 'space-y-2 rounded-2xl border border-blue-400 p-2 ring-2 ring-blue-200 transition-all duration-500' : 'space-y-2'}>
									<label className="text-sm font-medium tracking-tight text-slate-700">Attendees</label>
									<ChipListEditor
										label=""
										icon={User}
										value={formDraft.attendees}
										tempValue={attendeeDraft}
										onTempValueChange={setAttendeeDraft}
										onAdd={addAttendee}
										onRemove={(index) => dispatch(removeFormListItem({ field: 'attendees', index }))}
										addLabel="Add"
										placeholder="Type attendee name and add"
									/>
								</div>
							</div>
						</div>

						<div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
							<div className="mb-5 flex items-center gap-2 text-sm font-semibold tracking-tight text-slate-900">
								<Search className="h-4 w-4 text-slate-500" />
								<span>Materials &amp; Samples</span>
							</div>

							<div className="grid gap-5">
								<div className={aiHighlightedFields.materialsShared ? 'rounded-2xl border border-blue-400 p-2 ring-2 ring-blue-200 transition-all duration-500' : ''}>
								<ChipListEditor
									label="Materials Shared"
									icon={Search}
									value={formDraft.materialsShared}
									tempValue={materialDraft}
									onTempValueChange={setMaterialDraft}
									onAdd={addMaterial}
									onRemove={(index) => dispatch(removeFormListItem({ field: 'materialsShared', index }))}
									addLabel="Search/Add"
									placeholder="Search a material or add a custom item"
								/>
								</div>

								<div className={aiHighlightedFields.samplesDistributed ? 'rounded-2xl border border-blue-400 p-2 ring-2 ring-blue-200 transition-all duration-500' : ''}>
								<ChipListEditor
									label="Samples Distributed"
									icon={Package2}
									value={formDraft.samplesDistributed}
									tempValue={sampleDraft}
									onTempValueChange={setSampleDraft}
									onAdd={addSample}
									onRemove={(index) => dispatch(removeFormListItem({ field: 'samplesDistributed', index }))}
									addLabel="Add Sample"
									placeholder="Sample name or code"
								/>
								</div>
							</div>
						</div>

						<div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
							<div className="mb-5 flex items-center gap-2 text-sm font-semibold tracking-tight text-slate-900">
								<Sparkles className="h-4 w-4 text-slate-500" />
								<span>Sentiment &amp; Follow-up</span>
							</div>

							<div className="space-y-5">
								<div className={aiHighlightedFields.hcpSentiment ? 'rounded-2xl border border-blue-400 p-2 ring-2 ring-blue-200 transition-all duration-500' : ''}>
									<p className="mb-3 text-sm font-medium tracking-tight text-slate-700">HCP Sentiment</p>
									<div className="grid gap-3 md:grid-cols-3">
										{sentimentOptions.map(({ value, label, icon: Icon, emoji }) => {
											const selected = formDraft.hcpSentiment === value
											return (
												<label key={value} className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 text-sm shadow-sm transition ${selected ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-100' : 'border-slate-200 bg-white hover:bg-slate-50'}`}>
													<input
														type="radio"
														name="hcpSentiment"
														value={value}
														checked={selected}
														onChange={(e) => dispatch(setFormField({ field: 'hcpSentiment', value: e.target.value }))}
														className="sr-only"
													/>
													<Icon className={`h-5 w-5 ${selected ? 'text-blue-600' : 'text-slate-500'}`} />
													<span className="text-lg">{emoji}</span>
													<span className="font-medium text-slate-700">{label}</span>
												</label>
										)
										})}
									</div>
								</div>

								<div className="space-y-2">
									<label className="text-sm font-medium tracking-tight text-slate-700">Outcomes</label>
									<textarea
										value={formDraft.outcomes}
										onChange={(e) => dispatch(setFormField({ field: 'outcomes', value: e.target.value }))}
										rows={4}
										placeholder="Capture key agreements, commitments, and decisions..."
										className={fieldClass('outcomes', 'w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
									/>
								</div>

								<div className="space-y-2">
									<label className="text-sm font-medium tracking-tight text-slate-700">Follow-up Actions</label>
									<textarea
										value={formDraft.followUpActions}
										onChange={(e) => dispatch(setFormField({ field: 'followUpActions', value: e.target.value }))}
										rows={4}
										placeholder="List next steps, reminders, and follow-up tasks..."
										className={fieldClass('followUpActions', 'w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100')}
									/>
								</div>
							</div>
						</div>

						{formError && (
							<div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm">
								{formError}
							</div>
						)}

						{formSuccess && (
							<div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 shadow-sm">
								✓ Interaction logged successfully!
							</div>
						)}
							</div>
						</div>

						<div className="border-t border-slate-200 bg-white px-6 py-5">
							<button
								type="submit"
								disabled={loading === 'loading'}
								className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-linear-to-r from-blue-600 to-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:from-blue-700 hover:to-indigo-700 disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-300"
							>
								{loading === 'loading' ? (
									<>
										<Loader className="h-5 w-5 animate-spin" />
										<span>Saving...</span>
									</>
								) : (
									<span>Submit Interaction</span>
								)}
							</button>
						</div>
					</form>
				</div>
			</div>
		</div>
	)
}

export default ManualForm