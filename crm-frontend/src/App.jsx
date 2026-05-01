import { useEffect, useRef } from 'react'
import { Provider, useDispatch, useSelector } from 'react-redux'
import { applyAiFormUpdates, normalizeIncomingAiUpdates } from './store/interactionSlice'
import { store } from './store/store'
import ManualForm from './components/ManualForm'

const AppStatePatchBridge = () => {
  const dispatch = useDispatch();
  const messages = useSelector((state) => state.interactions.messages);
  const lastAppliedRef = useRef('');

  useEffect(() => {
    if (!messages?.length) return;
    // Look for the most recent assistant message that contains form updates
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === 'assistant' && m.structured_response && m.structured_response.form_updates && Object.keys(m.structured_response.form_updates).length > 0);

    if (!lastAssistant) return;

    const rawUpdates = lastAssistant.structured_response.form_updates || {};
    const signature = JSON.stringify(rawUpdates);

    // Prevent infinite loops: only dispatch if the data is NEW and non-empty
    if (signature === '{}' || signature === lastAppliedRef.current) return;

    // Normalize snake_case -> camelCase at bridge-level for clarity
    const normalized = normalizeIncomingAiUpdates(rawUpdates);

    dispatch(applyAiFormUpdates(normalized));
    lastAppliedRef.current = signature;
  }, [messages, dispatch]);

  return null;
};

const App = () => {
  return (
    <Provider store={store}>
      <div className="fixed inset-0 overflow-hidden bg-gray-50">
        <AppStatePatchBridge />
        <ManualForm />
      </div>
    </Provider>
  )
}

export default App