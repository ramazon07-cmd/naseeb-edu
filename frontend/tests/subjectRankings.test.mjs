import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const lib = await import('../src/lib/subjectRankings.js');
const { FALLBACK_SUBJECT, canLoadMore, SUBJECT_PAGE_SIZES, appendRows, isTopRank, presetSubject, publishedRank, scoreText, subjectLimit, subjectRankingsPath, subjectRankingsQuery, weightText } = lib;

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const query = (options) => Object.fromEntries(new URLSearchParams(subjectRankingsQuery(options)));

test('a subject page asks for 10, 25 or 50 rows of one subject and nothing else by default', () => {
  assert.deepEqual(SUBJECT_PAGE_SIZES, [10, 25, 50]);
  assert.equal(subjectRankingsQuery({ subject: 'COM02' }), 'subject=COM02&limit=10');
  assert.equal(subjectRankingsPath(subjectRankingsQuery({ subject: 'COM02', limit: 25 }), 25), 'subject=COM02&limit=25&offset=25');
});

test('only the filters that are set are sent, and the page size is clamped to the offered ones', () => {
  assert.deepEqual(query({ subject: 'LAW01', query: '  oxford ', country: 'United Kingdom', qsFilters: { region: 'Europe', size: '', research: 'VH', status: 'Public' }, limit: 50 }), {
    subject: 'LAW01', search: 'oxford', country: 'United Kingdom', region: 'Europe', research: 'VH', limit: '50',
  });
  assert.equal(query({ subject: 'LAW01', limit: 7 }).limit, '10');
  assert.equal(query({ subject: 'LAW01', limit: 100 }).limit, '10');
  // The shared "Show" control also offers 100: a subject page tops out at 50.
  assert.deepEqual([10, 25, 50, 100].map(subjectLimit), [10, 25, 50, 50]);
});

test('the rank reads as QS published it: a number, a tie, a range', () => {
  assert.equal(publishedRank(1), '#1');
  assert.equal(publishedRank(4, '=4'), '=4');
  assert.equal(publishedRank(201, '201-250'), '201–250');
  assert.equal(publishedRank(1401, '1401+'), '1401+');
});

test('a rank is gold only when it is a real top-10 position, never a range', () => {
  assert.ok(isTopRank(1) && isTopRank(10, '=10'));
  assert.ok(!isTopRank(11) && !isTopRank(1, '1-5'));
});

test('scores show one decimal and a missing one a dash; weights read as percentages', () => {
  assert.equal(scoreText(94.7), '94.7');
  assert.equal(scoreText(100), '100.0');
  assert.equal(scoreText(null), '—');
  assert.equal(weightText(0.4), '40%');
  assert.equal(weightText(0.125), '12.5%');
  assert.equal(weightText(0.05), '5%');
});

test('"Show more" appends the next page after the rows shown and never repeats a row', () => {
  const page = (from, to) => Array.from({ length: to - from }, (_, index) => ({ id: from + index }));
  const first = page(0, 25);
  const second = appendRows(first, page(25, 50));
  assert.deepEqual(second.map((row) => row.id), Array.from({ length: 50 }, (_, index) => index));
  assert.equal(appendRows(second, page(40, 60)).length, 60);
});

const AREAS = [{ code: 'AREA_ENG', subjects: [['COM02', 'x']] }, { code: 'AREA_SOC', subjects: [['LAW01', 'x'], ['MED01', 'x'], ['ECO01', 'x']] }];

test('the view starts at the subject of the major, else a fixed fallback, and ignores a subject we do not list', () => {
  assert.equal(presetSubject({ subjects: ['LAW01', 'ECO01'] }, AREAS), 'LAW01');
  assert.equal(presetSubject({ subjects: ['AREA_ENG'] }, AREAS), 'AREA_ENG');
  assert.equal(presetSubject({ subjects: ['NOPE', 'MED01'] }, AREAS), 'MED01');
  assert.equal(presetSubject({ subjects: [] }, AREAS), FALLBACK_SUBJECT);
  assert.equal(presetSubject(null, AREAS), FALLBACK_SUBJECT);
});

test('College Search loads the view lazily and the first search never waits for the student\'s subject', () => {
  const page = read('../src/pages/CollegeSearchPage.jsx');
  const loader = read('../src/components/SubjectRankingsLoader.jsx');
  assert.ok(!/^import[^;]*from\s*['"]\.\.?\/components\/SubjectRankings['"]/m.test(page), 'the view must not be imported statically');
  assert.ok(!/^import[^;]*from\s*['"]\.\/SubjectRankings['"]/m.test(loader), 'the loader must not import the view statically');
  assert.match(loader, /lazy\(load\)/);
  assert.match(loader, /import\('\.\/SubjectRankings'\)/);
  assert.match(page, /import \{ SubjectRankingsView \} from '\.\.\/components\/SubjectRankingsLoader'/);
  assert.ok(!/^import[^;]*from\s*['"]\.\.\/hooks\/useSubjectRankings['"]/m.test(page), 'the data hook belongs to the lazy chunk');
  // The first request is built without waiting for research, and none is made while the view is open.
  assert.match(page, /useCollegeSearch\(inSubjects \? null : collegeSearchQuery\(/);
  assert.ok(!page.includes('subjectReady'), 'the first page must not wait for the research response');
  assert.match(page, /const subject = subjectPick \?\? ''/);
});

test('the view keeps no ranking data in browser storage and aborts a request when the subject or a filter changes', () => {
  const hook = read('../src/hooks/useSubjectRankings.js');
  const view = read('../src/components/SubjectRankings.jsx');
  for (const source of [hook, view, read('../src/lib/subjectRankings.js')]) assert.ok(!/localStorage|sessionStorage|indexedDB/i.test(source));
  assert.match(hook, /new AbortController\(\)/);
  assert.match(hook, /controller\.current\?\.abort\(\)/);
  assert.match(hook, /fetchPage\(subjectRankingsPath\(query\), own\.signal\)/);
});

// After `npm run build`: the view is its own chunk, and the start-up chunks do not hold it.
const assets = new URL('../dist/assets/', import.meta.url);
test('the build has a separate Subject rankings chunk that no start-up chunk contains', { skip: !existsSync(assets) && 'run npm run build first' }, () => {
  const files = readdirSync(assets);
  const chunk = files.filter((name) => /^SubjectRankings-.*\.js$/.test(name));
  assert.equal(chunk.length, 1, files.join(', '));
  assert.ok(files.some((name) => /^SubjectRankings-.*\.css$/.test(name)), 'its styles ship with it');
  const chunkText = readFileSync(new URL(chunk[0], assets), 'utf8');
  assert.ok(chunkText.includes('subject-rankings'));
  for (const name of files.filter((file) => /^(index|react-vendor|icons)-.*\.js$/.test(file))) {
    assert.ok(!readFileSync(new URL(name, assets), 'utf8').includes('subject-rankings'), `${name} must not carry the Subject rankings request`);
  }
});

test('"Show more" only pages the query that produced the rows on screen', () => {
  const loaded = { query: 'subject=LAW01&limit=10', nextOffset: 10, loading: false, loadingMore: false };
  assert.ok(canLoadMore(loaded, 'subject=LAW01&limit=10'));
  // A filter changed and its first page failed: the old rows and offset must not page the new query.
  assert.ok(!canLoadMore(loaded, 'subject=LAW01&country=France&limit=10'));
  assert.ok(!canLoadMore({ ...loaded, nextOffset: null }, loaded.query));
  assert.ok(!canLoadMore({ ...loaded, loading: true }, loaded.query));
  assert.ok(!canLoadMore({ ...loaded, loadingMore: true }, loaded.query));
  const hook = read('../src/hooks/useSubjectRankings.js');
  assert.match(hook, /canLoadMore\(state, query\)/);
  assert.match(hook, /previous\.query === query \? previous : \{ \.\.\.previous, rows: \[\], count: 0, nextOffset: null \}/);
});

test('Retry after a failed chunk load remounts the child so it renders the new lazy view', () => {
  const loader = read('../src/components/SubjectRankingsLoader.jsx');
  assert.match(loader, /attempt: state\.attempt \+ 1/);
  assert.match(loader, /<Fragment key=\{this\.state\.attempt\}>/);
  assert.match(loader, /View = lazy\(load\)/);
  // The child reads the module-level lazy type at render time instead of holding the rejected one in its element.
  assert.match(loader, /function CurrentView\(props\) \{\s*return <View \{\.\.\.props\} \/>/);
  assert.match(loader, /<CurrentView \{\.\.\.props\} \/>/);
  assert.ok(!/<View \{\.\.\.props\} \/><\/Suspense>/.test(loader));
});

test('the request that carries the facets is not cancelled when the Subject rankings view opens', () => {
  const hook = read('../src/hooks/useCollegeSearch.js');
  assert.match(hook, /const signal = withFacets \? undefined : controller\.current\?\.signal/);
  assert.match(hook, /facets: payload\.facets \}\)\)/);
  // No extra request: the facets still ride on the first page request.
  assert.equal((hook.match(/api\.collegeSearch\(/g) || []).length, 1);
});

test('facets from a request for an older profile version are cached but never published', () => {
  const hook = read('../src/hooks/useCollegeSearch.js');
  assert.match(hook, /const currentVersion = useRef\(version\)/);
  assert.match(hook, /currentVersion\.current = version/);
  assert.match(hook, /facets\.current\.set\(version, payload\.facets\)/);
  assert.match(hook, /if \(version === currentVersion\.current\) setState\(\(previous\) => \(\{ \.\.\.previous, facets: payload\.facets \}\)\)/);
  assert.equal((hook.match(/api\.collegeSearch\(/g) || []).length, 1);
});
