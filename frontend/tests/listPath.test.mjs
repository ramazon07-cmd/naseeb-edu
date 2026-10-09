import test from 'node:test';
import assert from 'node:assert/strict';
import { LIST_PAGE_SIZE, PAGE_SIZES, firstListPath } from '../src/lib/listPath.js';

test('the first page asks for the large page size', () => {
  assert.equal(firstListPath('tasks'), `/tasks/?page_size=${LIST_PAGE_SIZE}`);
  assert.equal(firstListPath('users/accounts'), `/users/accounts/?page_size=${LIST_PAGE_SIZE}`);
});

test('existing filters are kept', () => {
  assert.equal(firstListPath('challenge-attempts', '?student=12'), `/challenge-attempts/?student=12&page_size=${LIST_PAGE_SIZE}`);
  assert.equal(firstListPath('challenge-attempts', '?student=a%26b'), `/challenge-attempts/?student=a%26b&page_size=${LIST_PAGE_SIZE}`);
});

test('the page size stays within the API maximum', () => {
  assert.ok(LIST_PAGE_SIZE > 25 && LIST_PAGE_SIZE <= 100);
});

test('the university catalogue reads its slim rows in pages of at most 500 (backend CatalogPagination)', () => {
  assert.equal(firstListPath('universities'), `/universities/?page_size=${PAGE_SIZES.universities}`);
  assert.ok(PAGE_SIZES.universities > LIST_PAGE_SIZE && PAGE_SIZES.universities <= 500);
});
