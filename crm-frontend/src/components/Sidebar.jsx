import React, { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { fetchSessions, fetchSessionMessages, postChatMessage, setCurrentSession, clearCurrentSession, createSession } from '../store/interactionSlice'

function Sidebar() {
    const dispatch = useDispatch()
    const sessions = useSelector((s) => s.interactions.sessions || [])
    const current = useSelector((s) => s.interactions.currentSessionId)

    useEffect(() => {
        dispatch(fetchSessions())
    }, [dispatch])

    const [openMobile, setOpenMobile] = useState(false)

    const handleNewChat = async () => {
        // generate a uuid and create session on backend
        const id = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)
        await dispatch(createSession({ sessionId: id, title: 'New Chat' }))
        // ensure UI cleared
        dispatch(setCurrentSession(id))
        dispatch(clearCurrentSession())
        setOpenMobile(false)
    }

    const openSession = (id) => {
        dispatch(setCurrentSession(id))
        dispatch(fetchSessionMessages(id))
    }

    const deleteSession = (id) => {
        // For now, we simply remove from UI; backend delete endpoint can be added later
        // optimistic update
        // TODO: implement backend delete
        console.warn('Delete session not implemented on backend yet', id)
    }

    return (
        <>
            {/* Mobile toggle button */}
            <div className="md:hidden p-2">
                <button onClick={() => setOpenMobile((v) => !v)} className="px-3 py-2 bg-blue-600 text-white rounded">{openMobile ? 'Close' : 'Menu'}</button>
            </div>

            <aside className={`fixed top-0 left-0 h-full z-40 bg-white border-r w-72 transform transition-transform duration-200 ease-in-out md:translate-x-0 ${openMobile ? 'translate-x-0' : '-translate-x-full'} md:relative md:translate-x-0 font-inter`}>
                <div className="px-4 py-3 flex items-center justify-between border-b">
                    <h2 className="text-lg font-semibold">Past Conversations</h2>
                    <button onClick={handleNewChat} className="text-sm text-blue-600 hover:underline">New Chat</button>
                </div>

                <div className="overflow-auto h-[calc(100%-56px)]">
                    {sessions.length === 0 && (
                        <div className="p-4 text-sm text-gray-500">No conversations yet</div>
                    )}
                    <ul>
                        {sessions.map((s) => (
                            <li key={s.id} className={`px-3 py-2 flex items-center justify-between cursor-pointer ${current === s.id ? 'bg-blue-50' : 'hover:bg-gray-50'}`}>
                                <div onClick={() => { openSession(s.id); setOpenMobile(false) }} className="flex-1">
                                    <div className="text-sm font-medium">{s.title}</div>
                                    <div className="text-xs text-gray-400">{new Date(s.created_at).toLocaleString()}</div>
                                </div>
                                <div className="pl-2">
                                    <button onClick={() => deleteSession(s.id)} className="text-red-500 hover:text-red-700">✕</button>
                                </div>
                            </li>
                        ))}
                    </ul>
                </div>
            </aside>
        </>
    )
}

export default Sidebar
