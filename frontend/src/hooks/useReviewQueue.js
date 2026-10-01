import { useMemo } from 'react';
import { usePagedList } from './usePagedList';
import { REVIEW_SOURCES, mergeReviewQueue } from '../lib/reviewQueue';

// "Needs your review": staff never bulk-load tasks/documents/roadmap
// missions/achievements (see workspaceResources.js — those grow with the
// school), so each source is its own small, server-filtered page, the same way
// the rest of the staff UI reads them (usePagedList). One call per
// REVIEW_SOURCES entry (kept explicit — hooks can't be called in a loop).
// Shared by Home's queue and the Review page; exact totals are in the stats.
const PAGE_SIZE = 25;

export function useReviewQueue() {
  const filters = Object.fromEntries(REVIEW_SOURCES.map((source) => [source.listKey, source.filters]));
  const tasks = usePagedList('tasks', { filters: filters.tasks, pageSize: PAGE_SIZE });
  const documents = usePagedList('documents', { filters: filters.documents, pageSize: PAGE_SIZE });
  const roadmapMissions = usePagedList('roadmap-missions', { filters: filters.roadmapMissions, pageSize: PAGE_SIZE });
  const achievements = usePagedList('achievements', { filters: filters.achievements, pageSize: PAGE_SIZE });
  const lists = { tasks, documents, roadmapMissions, achievements };
  const loaded = Object.values(lists).every((list) => list.loaded);
  const items = useMemo(
    () => mergeReviewQueue({ tasks: tasks.items, documents: documents.items, roadmapMissions: roadmapMissions.items, achievements: achievements.items }),
    [tasks.items, documents.items, roadmapMissions.items, achievements.items],
  );
  return { items, loaded, lists, reload: () => Object.values(lists).forEach((list) => list.reload()) };
}
