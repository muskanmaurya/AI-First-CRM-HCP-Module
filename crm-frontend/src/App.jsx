import { useEffect, useRef } from 'react'
import { Provider, useDispatch, useSelector } from 'react-redux'
import { applyAiFormUpdates } from './store/interactionSlice'
import { store } from './store/store'
import ManualForm from './components/ManualForm'

const AppStatePatchBridge = () => {
  const dispatch = useDispatch();
  const messages = useSelector((state) => state.interactions.messages);
  const lastAppliedRef = useRef('');

  useEffect(() => {
    if (!messages?.length) return;

    // Look for the most recent message from the assistant
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
    
    if (!lastAssistant?.structured_response?.form_updates) return;

    const updates = lastAssistant.structured_response.form_updates;
    const signature = JSON.stringify(updates);

    // Prevent infinite loops: only dispatch if the data is NEW
    if (signature === '{}' || signature === lastAppliedRef.current) return;

    console.log("🚀 Senior Dev: Auto-filling form with:", updates);
    dispatch(applyAiFormUpdates(updates));
    lastAppliedRef.current = signature;
  }, [messages, dispatch]);

  return null;
};

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