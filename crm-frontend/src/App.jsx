import { Provider } from 'react-redux'
import { store } from './store/store'
import LogInteractionScreen from './pages/LogInteractionScreen'

const App = () => {
  return (
    <Provider store={store}>
      <div className="h-screen w-screen bg-gray-50 overflow-hidden">
        <LogInteractionScreen />
      </div>
    </Provider>
  )
}

export default App