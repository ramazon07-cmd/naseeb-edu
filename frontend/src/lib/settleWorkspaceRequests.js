// Publish each independent resource as it arrives. A slow sidebar request
// must not keep an already available dashboard behind its loading skeleton.
// The returned results retain request order for batch retry/error handling.
export function settleWorkspaceRequests(requests, onSettled) {
  return Promise.all(requests.map(async ([key, request]) => {
    let result;
    try {
      result = { status: 'fulfilled', value: await request() };
    } catch (reason) {
      result = { status: 'rejected', reason };
    }
    onSettled(key, result);
    return result;
  }));
}
