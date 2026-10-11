// "Reviewed today" on the Review page: the server's list (GET /review/today/,
// newest first; the server owns the day boundary, midnight in Tashkent) plus
// decisions made on this page that no server reply has covered yet.
// Translation-free; the page words it.
//
// No clock matching: every local row carries the sequence number current when
// it was added, and a reply to a request started after that (the decision had
// already been saved, so its timeline row is in the reply if one was written)
// replaces it. An approve that wrote nothing (already approved) therefore
// disappears with the next reply instead of lingering.

export function createReviewedTodayState() {
  let seq = 0;
  return {
    // A queue item just decided here, shaped like a server row.
    local(item, decision, now = new Date()) {
      seq += 1;
      return {
        id: `local-${item.id}-${seq}`,
        seq,
        kind: item.kind,
        decision,
        record_id: item.recordId,
        title: item.title,
        student_id: item.studentId,
        student_name: item.studentName,
        at: now.toISOString(),
        pending: true,
      };
    },
    // Call when a request starts; pass the result to settleLocal with its reply.
    mark: () => seq,
  };
}

// Local rows a reply to a request started at `mark` does not cover yet.
export const settleLocal = (localRows = [], mark = 0) => localRows.filter((row) => row.seq > mark);

// Local rows (the newest decisions) first, then the server's rows in its order.
export const mergeReviewedToday = (serverRows = [], localRows = []) => [
  ...[...localRows].sort((a, b) => b.seq - a.seq),
  ...serverRows,
];

// The list in a /review/today/ reply, whether or not the client unwrapped it.
export const reviewedTodayRows = (data) => (Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : []);
