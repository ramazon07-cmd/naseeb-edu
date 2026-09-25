import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  MAX_UPLOAD_BYTES,
  UPLOAD_ACCEPT,
  UPLOAD_EXTENSIONS,
  canPreviewInBrowser,
  fileExtension,
  fileKind,
  sendWithProgress,
  titleFromFileName,
  toFormData,
  uploadPercent,
  uploadProblem,
} from '../src/lib/fileUpload.js';

const backendSource = (path) => readFileSync(new URL(`../../backend/${path}`, import.meta.url), 'utf8');

test('client rules stay within the backend upload policy', () => {
  const settings = backendSource('core/settings.py');
  const allowed = settings.match(/'DOCUMENT_ALLOWED_EXTENSIONS',\s*default='([^']+)'/)[1].split(',');
  for (const extension of UPLOAD_EXTENSIONS) assert.ok(allowed.includes(extension), extension);
  const [, megabytes] = settings.match(/'DOCUMENT_MAX_UPLOAD_SIZE', default=(\d+) \* 1024 \* 1024/);
  assert.equal(MAX_UPLOAD_BYTES, Number(megabytes) * 1024 * 1024);

  const serializers = backendSource('apps/admissions/serializers/common.py');
  const inline = serializers.match(/INLINE_FILE_EXTENSIONS = frozenset\(\{([^}]+)\}\)/)[1].match(/'\.[a-z]+'/g).map((item) => item.slice(1, -1));
  for (const extension of UPLOAD_EXTENSIONS) {
    assert.equal(canPreviewInBrowser(`file${extension}`), inline.includes(extension), extension);
  }
});

test('the picker accepts every allowed extension and offers photos on phones', () => {
  const accept = UPLOAD_ACCEPT.split(',');
  for (const extension of UPLOAD_EXTENSIONS) assert.ok(accept.includes(extension));
  assert.ok(accept.includes('image/jpeg'));
  assert.ok(accept.includes('application/pdf'));
});

test('uploadProblem refuses wrong types, empty and oversized files', () => {
  const file = (name, size) => ({ name, size });
  assert.equal(uploadProblem(file('Transcript.PDF', 1000)), null);
  assert.equal(uploadProblem(file('essay.docx', 1000)), null);
  assert.equal(uploadProblem(file('IMG_0001.HEIC', 1000)), null);
  assert.deepEqual(uploadProblem(file('setup.exe', 1000)), { code: 'type' });
  assert.deepEqual(uploadProblem(file('sheet.xlsx', 1000)), { code: 'type' });
  assert.deepEqual(uploadProblem(file('no-extension', 1000)), { code: 'type' });
  assert.deepEqual(uploadProblem(file('empty.pdf', 0)), { code: 'empty' });
  assert.deepEqual(uploadProblem(file('big.pdf', MAX_UPLOAD_BYTES + 1)), { code: 'size' });
  assert.equal(uploadProblem(file('edge.pdf', MAX_UPLOAD_BYTES)), null);
  assert.equal(uploadProblem(null), null);
});

test('file kinds pick icons and preview notes', () => {
  assert.equal(fileExtension('a.b.PDF'), '.pdf');
  assert.equal(fileExtension('.hidden'), '.hidden');
  assert.equal(fileExtension('folder.d/name'), '');
  assert.equal(fileKind('cv.pdf'), 'pdf');
  assert.equal(fileKind('cv.doc'), 'word');
  assert.equal(fileKind('upload', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'), 'word');
  assert.equal(fileKind('photo.heic'), 'image');
  assert.equal(fileKind('notes.txt'), 'file');
  assert.equal(canPreviewInBrowser('scan.webp'), true);
  assert.equal(canPreviewInBrowser('photo.heic'), false);
  assert.equal(canPreviewInBrowser('essay.docx'), false);
});

test('titles are suggested from file names', () => {
  assert.equal(titleFromFileName('IELTS_score  report.pdf'), 'IELTS score report');
  assert.equal(titleFromFileName('C:\\scans\\passport.jpg'), 'passport');
  assert.equal(titleFromFileName('README'), 'README');
});

test('uploadPercent is clamped and safe without a total', () => {
  assert.equal(uploadPercent(50, 200), 25);
  assert.equal(uploadPercent(500, 200), 100);
  assert.equal(uploadPercent(10, 0), 0);
});

test('toFormData clears with an empty value and keeps file names', async () => {
  const file = new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' });
  const payload = toFormData({ title: 'Transcript', file, date: null, verified: false, skipped: undefined, student: 4 });
  assert.equal(payload.get('title'), 'Transcript');
  assert.equal(payload.get('date'), '');
  assert.equal(payload.get('verified'), 'false');
  assert.equal(payload.get('student'), '4');
  assert.equal(payload.has('skipped'), false);
  assert.equal(payload.get('file').name, 'transcript.pdf');
  assert.equal(await payload.get('file').text(), '%PDF');
});

class FakeRequest {
  constructor() {
    this.listeners = {};
    this.uploadListeners = {};
    this.headers = {};
    this.upload = { addEventListener: (name, fn) => {this.uploadListeners[name] = fn;} };
  }
  addEventListener(name, fn) {this.listeners[name] = fn;}
  open(method, url) {this.method = method;this.url = url;}
  setRequestHeader(name, value) {this.headers[name] = value;}
  getResponseHeader(name) {return name === 'Content-Type' ? 'application/json' : null;}
  send(body) {this.body = body;}
  abort() {this.aborted = true;this.listeners.abort?.();}
  progress(loaded, total) {this.uploadListeners.progress?.({ lengthComputable: true, loaded, total });}
  finish(status, text) {this.status = status;this.responseText = text;this.listeners.load?.();}
}

test('sendWithProgress reports progress and resolves any HTTP answer', async () => {
  const xhr = new FakeRequest();
  const seen = [];
  const promise = sendWithProgress({
    createRequest: () => xhr, method: 'POST', url: '/api/documents/', headers: { Authorization: 'Bearer x' },
    body: 'payload', onProgress: (value) => seen.push(value), timeoutMs: 1000,
  });
  xhr.progress(25, 100);
  xhr.progress(100, 100);
  xhr.finish(400, '{"file":["Unsupported file type."]}');
  const response = await promise;
  assert.deepEqual(seen, [25, 100]);
  assert.equal(xhr.method, 'POST');
  assert.equal(xhr.headers.Authorization, 'Bearer x');
  assert.equal(xhr.timeout, 1000);
  assert.equal(xhr.body, 'payload');
  assert.deepEqual(response, { status: 400, text: '{"file":["Unsupported file type."]}', contentType: 'application/json' });
});

test('sendWithProgress aborts through the signal and on network failure', async () => {
  const controller = new AbortController();
  const xhr = new FakeRequest();
  const aborted = sendWithProgress({ createRequest: () => xhr, method: 'PATCH', url: '/x', body: '', signal: controller.signal });
  controller.abort();
  await assert.rejects(aborted, { name: 'AbortError' });
  assert.equal(xhr.aborted, true);

  const early = new AbortController();
  early.abort();
  const unsent = new FakeRequest();
  await assert.rejects(sendWithProgress({ createRequest: () => unsent, method: 'POST', url: '/x', body: '', signal: early.signal }), { name: 'AbortError' });
  assert.equal(unsent.method, undefined);

  const broken = new FakeRequest();
  const failed = sendWithProgress({ createRequest: () => broken, method: 'POST', url: '/x', body: '' });
  broken.listeners.error();
  await assert.rejects(failed, { name: 'NetworkError' });
});
