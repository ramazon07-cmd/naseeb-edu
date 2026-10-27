import test from 'node:test';
import assert from 'node:assert/strict';
import { enterAssistantInvite } from '../src/lib/assistantInviteSession.js';

const credentials = { username: 'NewAssistant', password: 'test-only-password' };
const accepted = { username: 'newassistant', counselor_name: 'Counselor' };

test('an accepted invite replaces the counselor session before loading the assistant workspace', async () => {
  let session = 'counselor';
  let opened = null;
  const result = await enterAssistantInvite({ token: 'invite', credentials }, {
    acceptInvite: async (token, payload) => {
      assert.equal(token, 'invite');
      assert.deepEqual(payload, credentials);
      assert.equal(session, 'counselor');
      return accepted;
    },
    signIn: async (username, password) => {
      assert.equal(username, accepted.username);
      assert.equal(password, credentials.password);
      session = username;
    },
    openWorkspace: async () => { opened = session; },
  });
  assert.equal(opened, 'newassistant');
  assert.equal(result.error, null);
});

test('invalid invitations leave the existing session alone', async () => {
  const unavailable = new Error('unavailable');
  let sessionChanged = false;
  await assert.rejects(enterAssistantInvite({ token: 'expired', credentials }, {
    acceptInvite: async () => { throw unavailable; },
    signIn: async () => { sessionChanged = true; },
    openWorkspace: async () => { assert.fail('must not open an invalid invite'); },
  }), unavailable);
  assert.equal(sessionChanged, false);
});

for (const failedStep of ['signIn', 'openWorkspace']) {
  test(`retrying a ${failedStep} failure signs into the created account without accepting the single-use link again`, async () => {
    let accepts = 0;
    let attempts = 0;
    let opens = 0;
    const failure = new Error('connection interrupted');
    const actions = {
      acceptInvite: async () => { accepts += 1; return accepted; },
      signIn: async () => { attempts += 1; if (failedStep === 'signIn' && attempts === 1) throw failure; },
      openWorkspace: async () => { opens += 1; if (failedStep === 'openWorkspace' && opens === 1) throw failure; },
    };
    const first = await enterAssistantInvite({ token: 'single-use', credentials }, actions);
    assert.equal(first.error, failure);
    assert.equal(first.account, accepted);
    if (failedStep === 'signIn') assert.equal(opens, 0);
    const retry = await enterAssistantInvite({ token: 'single-use', credentials, account: first.account }, actions);
    assert.equal(accepts, 1);
    assert.equal(attempts, 2);
    assert.equal(retry.error, null);
    assert.equal(opens, failedStep === 'signIn' ? 1 : 2);
  });
}
