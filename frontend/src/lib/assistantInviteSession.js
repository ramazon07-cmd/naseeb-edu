// Accepting an invite commits a new account before sign-in. Keep that result
// if sign-in or workspace loading fails so a retry never spends the token again.
export async function enterAssistantInvite({ token, credentials, account = null }, { acceptInvite, signIn, openWorkspace }) {
  const accepted = account || await acceptInvite(token, credentials);
  try {
    // Use the server's normalized username, never an existing browser session.
    await signIn(accepted.username, credentials.password);
    await openWorkspace();
    return { account: accepted, error: null };
  } catch (error) {
    return { account: accepted, error };
  }
}
