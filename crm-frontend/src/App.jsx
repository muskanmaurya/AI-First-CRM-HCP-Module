import { useEffect, useRef } from 'react'
import { Provider, useDispatch, useSelector } from 'react-redux'
import { applyAiFormUpdates } from './store/interactionSlice'
import { store } from './store/store'
import ManualForm from './components/ManualForm'

const AppStatePatchBridge = () => {
  const dispatch = useDispatch()
  const messages = useSelector((state) => state.interactions.messages)
  const lastAppliedRef = useRef('')

  useEffect(() => {
    if (!messages?.length) return
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
    if (!lastAssistant?.structured_response?.form_updates) return

    const updates = lastAssistant.structured_response.form_updates
    const signature = JSON.stringify(updates)
    if (!signature || signature === '{}' || signature === lastAppliedRef.current) return

    dispatch(applyAiFormUpdates(updates))
    lastAppliedRef.current = signature
  }, [dispatch, messages])

  return null
}

const App = () => {
  return (
    <Provider store={store}>
      <div className="h-dvh w-screen overflow-hidden bg-gray-50">
        <AppStatePatchBridge />
        <ManualForm />
      </div>
    </Provider>
  )
}

export default App