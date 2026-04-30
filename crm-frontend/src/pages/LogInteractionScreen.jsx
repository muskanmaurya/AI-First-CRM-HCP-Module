import { useState, useRef, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { Send, User, Calendar, FileText, Loader } from 'lucide-react'
import axios from 'axios'
import { addInteraction } from '../store/interactionSlice'

const LogInteractionScreen = () => {
  const dispatch = useDispatch()
  const { loading } = useSelector((state) => state.interactions)

  // Chat state
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const messagesEndRef = useRef(null)

  // Form state
  const [formData, setFormData] = useState({
    hcpName: '',
    interactionDate: new Date().toISOString().split('T')[0],
    meetingNotes: '',
  })
  const [formError, setFormError] = useState('')
  const [formSuccess, setFormSuccess] = useState(false)

  // Auto-scroll to newest message
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [chatMessages])

  // Handle chat message send
  const handleSendMessage = async () => {
    if (!chatInput.trim()) return

    const userMessage = { role: 'user', content: chatInput }
    setChatMessages((prev) => [...prev, userMessage])
    setChatInput('')
    setChatLoading(true)

    try {
      const response = await axios.post('https://ai-first-crm-hcp-module-hw8f.onrender.com/chat', {
        message: chatInput,
        session_id: 'default_session',
      })

      const botMessage = {
        role: 'assistant',
        content: response.data.response || 'No response received',
      }
      setChatMessages((prev) => [...prev, botMessage])
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: `Error: ${error.response?.data?.detail || error.message}`,
      }
      setChatMessages((prev) => [...prev, errorMessage])
    } finally {
      setChatLoading(false)
    }
  }

  // Handle form input change
  const handleFormChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
    setFormError('')
  }

  // Handle form submission
  const handleFormSubmit = async (e) => {
    e.preventDefault()
    setFormError('')
    setFormSuccess(false)

    if (!formData.hcpName.trim()) {
      setFormError('HCP Name is required')
      return
    }
    if (!formData.interactionDate) {
      setFormError('Date is required')
      return
    }
    if (!formData.meetingNotes.trim()) {
      setFormError('Meeting Notes are required')
      return
    }

    try {
      await dispatch(
        addInteraction({
          hcp_name: formData.hcpName,
          interaction_date: formData.interactionDate,
          interaction_type: 'Form',
          summary: formData.meetingNotes,
        }),
      ).unwrap()

      setFormSuccess(true)
      setFormData({
        hcpName: '',
        interactionDate: new Date().toISOString().split('T')[0],
        meetingNotes: '',
      })
      setTimeout(() => setFormSuccess(false), 3000)
    } catch (error) {
      setFormError(
        error || 'Failed to save interaction. Please try again.',
      )
    }
  }

  // Handle keyboard send in chat
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  return (
    <div className="h-screen w-full bg-gray-50 overflow-hidden">
      {/* Main container */}
      <div className="h-full flex flex-col lg:flex-row">
        {/* Left Panel - Chat Interface (60% on desktop) */}
        <div className="flex-1 lg:w-3/5 flex flex-col bg-white border-r border-gray-200 lg:border-r lg:border-gray-200">
          {/* Header */}
          <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-indigo-50">
            <h2 className="text-lg font-semibold text-gray-900">
              AI Assistant Chat
            </h2>
            <p className="text-sm text-gray-600">
              Chat with your healthcare AI to log interactions
            </p>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-white">
            {chatMessages.length === 0 ? (
              <div className="flex items-center justify-center h-full text-center">
                <div>
                  <div className="text-4xl mb-4 opacity-20">💬</div>
                  <p className="text-gray-500 font-medium">
                    Start a conversation
                  </p>
                  <p className="text-sm text-gray-400 mt-2">
                    Ask the AI to help you log or search interactions
                  </p>
                </div>
              </div>
            ) : (
              <>
                {chatMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${
                      msg.role === 'user' ? 'justify-end' : 'justify-start'
                    }`}
                  >
                    <div
                      className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                        msg.role === 'user'
                          ? 'bg-blue-600 text-white rounded-br-none'
                          : 'bg-gray-100 text-gray-900 rounded-bl-none border border-gray-200'
                      }`}
                    >
                      <p className="text-sm leading-relaxed">{msg.content}</p>
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 text-gray-900 px-4 py-3 rounded-lg border border-gray-200 rounded-bl-none">
                      <div className="flex items-center space-x-2">
                        <Loader className="w-4 h-4 animate-spin text-gray-600" />
                        <span className="text-sm text-gray-600">
                          Thinking...
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input Area */}
          <div className="px-6 py-4 border-t border-gray-200 bg-white">
            <div className="flex items-end space-x-3">
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your message... (Shift+Enter for new line)"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                rows="3"
              />
              <button
                onClick={handleSendMessage}
                disabled={chatLoading || !chatInput.trim()}
                className="px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>

        {/* Right Panel - Form (40% on desktop) */}
        <div className="flex-1 lg:w-2/5 flex flex-col bg-gray-50 border-t lg:border-t-0 lg:border-l border-gray-200 lg:overflow-y-auto">
          {/* Form Header */}
          <div className="px-6 py-4 bg-gradient-to-r from-indigo-50 to-blue-50 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">
              Log Interaction
            </h2>
            <p className="text-sm text-gray-600">
              Record details about your healthcare professional interaction
            </p>
          </div>

          {/* Form Content */}
          <form onSubmit={handleFormSubmit} className="flex-1 p-6 space-y-5">
            {/* HCP Name Field */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <div className="flex items-center space-x-2">
                  <User className="w-4 h-4 text-blue-600" />
                  <span>HCP Name</span>
                </div>
              </label>
              <input
                type="text"
                name="hcpName"
                value={formData.hcpName}
                onChange={handleFormChange}
                placeholder="e.g., Dr. Sarah Johnson"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Date Field */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <div className="flex items-center space-x-2">
                  <Calendar className="w-4 h-4 text-blue-600" />
                  <span>Interaction Date</span>
                </div>
              </label>
              <input
                type="date"
                name="interactionDate"
                value={formData.interactionDate}
                onChange={handleFormChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Meeting Notes Field */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-blue-600" />
                  <span>Meeting Notes</span>
                </div>
              </label>
              <textarea
                name="meetingNotes"
                value={formData.meetingNotes}
                onChange={handleFormChange}
                placeholder="Summarize the key points from your interaction..."
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                rows="5"
              />
            </div>

            {/* Error Message */}
            {formError && (
              <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{formError}</p>
              </div>
            )}

            {/* Success Message */}
            {formSuccess && (
              <div className="px-4 py-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-sm text-green-700">
                  ✓ Interaction logged successfully!
                </p>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading === 'loading'}
              className="w-full px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-medium rounded-lg hover:from-blue-700 hover:to-indigo-700 disabled:from-gray-400 disabled:to-gray-400 disabled:cursor-not-allowed transition-all flex items-center justify-center space-x-2"
            >
              {loading === 'loading' ? (
                <>
                  <Loader className="w-5 h-5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Submit Interaction</span>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

export default LogInteractionScreen
