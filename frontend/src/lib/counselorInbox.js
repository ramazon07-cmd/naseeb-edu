// The student's earlier counselor messages (the /student-messages/ thread that
// predates chats). Framework-free so it is unit tested.

// The active chat id that shows this thread instead of a channel.
export const COUNSELOR_INBOX = 'counselor';

// Messages addressed to `userId` that are still unread.
export const unreadFor = (messages, userId) => messages.filter((message) => message.recipient === userId && !message.is_read).length;

// Who "Continue in chat" should open: the other side of the newest message.
export function counselorOf(messages, userId) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const { sender, recipient } = messages[index];
    const other = sender === userId ? recipient : sender;
    if (other && other !== userId) return other;
  }
  return null;
}

// Everything addressed to `userId` marked read, the rest unchanged.
export const markReadFor = (messages, userId) => messages.map((message) => (
  message.recipient === userId && !message.is_read ? { ...message, is_read: true } : message
));
