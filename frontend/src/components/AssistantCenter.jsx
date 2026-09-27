import { useMemo, useState, useRef, useEffect } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { Trash2, X, ShieldCheck, WifiOff, ChevronRight, Square, Send, Info } from 'lucide-react';
import { initials, fullName } from '../lib/labels';
import { assistantSource } from '../lib/assistantSource';

export function AssistantCenter({ user, onOpenScreenTime }) {
  const welcome = useMemo(() => ({
    id: `welcome-${user.id}`,
    role: 'assistant',
    local: true,
    content: user.role === 'counselor' ?
    'Let’s plan your work with students.' :
    'What would you like help with?'
  }), [user.id, user.role]);
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState('ready');
  const [error, setError] = useState('');
  const abortRef = useRef(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const busy = status === 'submitted' || status === 'streaming';

  useEffect(() => setMessages([welcome]), [welcome]);
  // Stop a streaming answer when the assistant unmounts (sign-out, role change).
  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    if (!open) return undefined;
    function closeOnEscape(event) {if (event.key === 'Escape') setOpen(false);}
    document.addEventListener('keydown', closeOnEscape);
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => {window.clearTimeout(focusTimer);document.removeEventListener('keydown', closeOnEscape);};
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: status === 'streaming' || reduced ? 'auto' : 'smooth' });
  }, [messages, open, status]);

  function clearConversation() {
    abortRef.current?.abort();
    setMessages([welcome]);
    setInput('');
    setError('');
    setStatus('ready');
  }

  async function sendMessage(value = input) {
    const content = value.trim();
    if (!content || busy) return;
    const stamp = Date.now();
    const userMessage = { id: `user-${stamp}`, role: 'user', content };
    const assistantId = `assistant-${stamp}`;
    const outbound = [...messages.filter((message) => !message.local && message.content), userMessage].
    slice(-12).
    map(({ role, content: text }) => ({ role, content: text }));
    setMessages((current) => [...current, userMessage, { id: assistantId, role: 'assistant', content: '' }]);
    setInput('');
    setError('');
    setStatus('submitted');
    const controller = new AbortController();
    abortRef.current = controller;
    let received = '';
    try {
      const response = await api.streamAssistant(outbound, controller.signal);
      if (!response.body) throw new Error('Streaming is not supported by this browser.');
      const source = assistantSource(response.headers?.get('X-Assistant-Source'));
      if (source) setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, source } : message));
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value: chunk } = await reader.read();
        if (done) break;
        received += decoder.decode(chunk, { stream: true });
        setStatus('streaming');
        setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: received } : message));
      }
      received += decoder.decode();
      if (!received.trim()) throw new Error('The assistant returned an empty response.');
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: received } : message));
      setStatus('ready');
    } catch (requestError) {
      if (requestError?.name === 'AbortError') {
        if (!received) setMessages((current) => current.filter((message) => message.id !== assistantId));
        setStatus('ready');
      } else {
        setMessages((current) => current.filter((message) => message.id !== assistantId));
        setError(requestError?.status === 429 ? t("You have reached the assistant limit. Please try again later.") : t("The assistant could not respond. Check your connection and try again."));
        setStatus('error');
      }
    } finally {
      abortRef.current = null;
    }
  }

  const suggestions = user.role === 'counselor' ?
  ['Plan student check-ins', 'Review overdue tasks', 'Plan a meeting'] :
  ['Plan today’s tasks', 'Break down my next mission', 'Plan my essay'];

  return <div className={`assistant-center ${open ? 'open' : ''}`}>
    {open && <section className="assistant-drawer" role="dialog" aria-label={t("Naseeb AI assistant")}>
      <header><div className="assistant-title"><span className="assistant-mark"><span className="assistant-title-mark" aria-hidden="true" /></span><div><h2>{t("Naseeb AI")}</h2></div></div><div className="assistant-header-actions"><button type="button" className="icon-button" onClick={clearConversation} aria-label={t("Clear conversation")} title={t("Clear conversation")}><Trash2 size={16} /></button><button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label={t("Close assistant")}><X size={18} /></button></div></header>
      <div className="assistant-safety"><ShieldCheck size={15} /><span>{t("Keep personal data private.")}</span></div>
      <div ref={listRef} className="assistant-messages" aria-live="polite" aria-busy={busy}>
        {messages.map((message) => <article className={`assistant-message ${message.role}`} key={message.id}><span>{message.role === 'assistant' ? <span className="assistant-avatar-mark" aria-hidden="true" /> : initials(fullName(user))}</span><div><b>{message.role !== 'assistant' ? t("You") : message.source && !message.source.ai ? t("Naseeb guide") : t("Naseeb AI")}</b><p>{(message.local ? t(message.content) : message.content) || <span className="assistant-typing" aria-label={t("Assistant is thinking")}><i /><i /><i /></span>}</p>{message.source?.note && <small className="assistant-source-note"><Info size={12} aria-hidden="true" />{t(message.source.note)}</small>}</div></article>)}
        {status === 'submitted' && <span className="sr-only">{t("Assistant is preparing a response.")}</span>}
        {error && <div className="assistant-error" role="alert"><WifiOff size={15} /><span>{error}</span></div>}
      </div>
      {messages.length === 1 && <div className="assistant-suggestions" aria-label={t("Suggested questions")}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => sendMessage(t(suggestion))}>{t(suggestion)}<ChevronRight size={14} /></button>)}</div>}
      <form className="assistant-compose" onSubmit={(event) => {event.preventDefault();sendMessage();}}>
        <textarea ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {if (event.key === 'Enter' && !event.shiftKey) {event.preventDefault();sendMessage();}}} maxLength="2000" rows="2" placeholder={t("Ask a question…")} disabled={busy} aria-label={t("Message Naseeb AI")} />
        <button type={busy ? "button" : "submit"} className="assistant-send" onClick={busy ? () => abortRef.current?.abort() : undefined} disabled={!busy && !input.trim()} aria-label={busy ? t("Stop response") : t("Send message")}>{busy ? <Square size={16} fill="currentColor" /> : <Send size={17} />}</button>
        <details className="assistant-info"><summary>{t("AI can make mistakes.")}</summary><p>{t("Role-scoped context only. Do not share contact, passport, password, or payment details.")}</p><p>{t("AI can make mistakes. Verify important deadlines with your counselor. History is kept only while this page is open.")}</p></details>
      </form>
    </section>}
    <div className="assistant-launchers"><button type="button" className="assistant-launcher" onClick={() => setOpen((current) => !current)} aria-label={t("Open Naseeb AI assistant")} aria-expanded={open}><span className="assistant-launcher-mark" aria-hidden="true" /></button></div>
  </div>;
}
