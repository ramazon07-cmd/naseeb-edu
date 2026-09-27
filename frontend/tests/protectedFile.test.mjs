import test from 'node:test';
import assert from 'node:assert/strict';
import { FILE_LINK_CONTENT_TYPE, protectedFileUrl, readProtectedFile, responseFileName } from '../src/lib/protectedFile.js';

function response({ status = 200, headers = {}, body = '' } = {}) {
  const map = new Headers(headers);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: map,
    blob: async () => new Blob([body], { type: map.get('Content-Type') || '' }),
    json: async () => JSON.parse(body),
  };
}

test('file requests ask for a link and keep the download flag', () => {
  assert.equal(protectedFileUrl('https://api.test/api', '/documents/4/file/'), 'https://api.test/api/documents/4/file/?mode=url');
  assert.equal(protectedFileUrl('https://api.test/api', '/documents/4/file/', true), 'https://api.test/api/documents/4/file/?mode=url&download=1');
});

test('a streamed file (local disk) is read directly and never re-fetched', async () => {
  const fetched = [];
  const result = await readProtectedFile(
    response({ headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': "inline; filename*=UTF-8''Transcript%20%C3%B6.pdf" }, body: '%PDF' }),
    { fetchFile: async (url) => { fetched.push(url); }, fileError: () => new Error('no') },
  );
  assert.deepEqual(fetched, []);
  assert.equal(result.contentType, 'application/pdf');
  assert.equal(result.fileName, 'Transcript ö.pdf');
  assert.equal(await result.blob.text(), '%PDF');
});

test('a presigned link is followed with the credential-free fetcher', async () => {
  const fetched = [];
  const link = { url: 'https://bucket.test/private/a.pdf?X-Amz-Signature=x', expires_at: '2026-01-01T00:00:00Z', file_name: 'a.pdf', content_type: 'application/pdf' };
  const result = await readProtectedFile(
    response({ headers: { 'Content-Type': FILE_LINK_CONTENT_TYPE }, body: JSON.stringify(link) }),
    {
      fetchFile: async (url) => { fetched.push(url); return response({ headers: { 'Content-Type': 'binary/octet-stream' }, body: 'bytes' }); },
      fileError: () => new Error('no'),
    },
  );
  assert.deepEqual(fetched, [link.url]);
  assert.equal(result.contentType, 'application/pdf');
  assert.equal(result.fileName, 'a.pdf');
  assert.equal(await result.blob.text(), 'bytes');
});

test('an expired or refused bucket link surfaces the caller error', async () => {
  const link = { url: 'https://bucket.test/x', file_name: 'x.pdf', content_type: 'application/pdf' };
  await assert.rejects(
    readProtectedFile(
      response({ headers: { 'Content-Type': FILE_LINK_CONTENT_TYPE }, body: JSON.stringify(link) }),
      { fetchFile: async () => response({ status: 403 }), fileError: (status) => new Error(`bucket ${status}`) },
    ),
    /bucket 403/,
  );
});

test('file names fall back safely', () => {
  assert.equal(responseFileName(response()), 'document');
  assert.equal(responseFileName(response({ headers: { 'Content-Disposition': 'attachment; filename="plain.txt"' } })), 'plain.txt');
  assert.equal(responseFileName(response({ headers: { 'Content-Disposition': "attachment; filename*=UTF-8''%E0%A4%A" } })), 'document');
});
