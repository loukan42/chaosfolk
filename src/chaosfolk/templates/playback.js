/* Index an immutable journal once; seeks read counters and per-user positions. */
(() => {
  'use strict';
  function bound(values, value, inclusive = true) {
    let low = 0, high = values.length;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (values[mid] < value || (inclusive && values[mid] === value)) low = mid + 1;
      else high = mid;
    }
    return low;
  }

  window.buildPlaybackIndex = function(events, {timed, start, findings, validCapture, blocking}) {
    const at = i => timed ? Math.max(0, events[i].t - start) : i * 1000;
    const order = Array.from(events.keys());
    if (!order.every((i) => !i || at(i - 1) <= at(i))) order.sort((a, b) => at(a) - at(b) || a - b);
    const times = new Float64Array(events.length);
    const actions = new Uint32Array(events.length + 1), flags = new Uint32Array(events.length + 1);
    const groups = new Map(), completions = new Map(), findingRefs = new Map();
    const foundAt = new Float64Array(findings.length).fill(Infinity);
    for (const [index, finding] of findings.entries()) {
      for (const ref of Array.isArray(finding.evenements) ? finding.evenements : []) {
        if (!ref || typeof ref !== 'object') continue;
        const key = `${ref.h}/${ref.n}`;
        if (!findingRefs.has(key)) findingRefs.set(key, []);
        findingRefs.get(key).push(index);
      }
    }
    const ignored = new Set(['look', 'think', 'flag', 'giveup', 'done']);
    for (const [position, original] of order.entries()) {
      const event = events[original], time = at(original);
      times[position] = time;
      actions[position + 1] = actions[position] + !ignored.has(event.action);
      flags[position + 1] = flags[position] + (event.action === 'flag');
      if (!groups.has(event.h)) groups.set(event.h, []);
      groups.get(event.h).push(original);
      if (event.action === 'done' && !completions.has(event.h)) completions.set(event.h, time);
      for (const finding of findingRefs.get(`${event.h}/${event.n}`) || []) foundAt[finding] = Math.min(foundAt[finding], time);
    }
    const people = new Map();
    for (const [id, indices] of groups) {
      const userTimes = new Float64Array(indices.length), last = new Uint32Array(indices.length);
      const shots = new Int32Array(indices.length);
      let newest = -1, shot = -1, firstBlocker = Infinity;
      for (const [position, original] of indices.entries()) {
        const event = events[original];
        userTimes[position] = at(original);
        newest = Math.max(newest, original);
        if (validCapture(event.capture)) shot = Math.max(shot, original);
        if (event.action === 'flag' && blocking(event.gravite)) firstBlocker = Math.min(firstBlocker, at(original));
        last[position] = newest;
        shots[position] = shot;
      }
      people.set(id, {times: userTimes, last, shots, firstBlocker});
    }
    const doneAt = Float64Array.from(completions.values()).sort();
    foundAt.sort();
    return {
      at,
      end: times.length ? times[times.length - 1] : 0,
      count: time => bound(times, time),
      // Neighbor semantics match the controls' one-millisecond tolerance.
      next: time => times[bound(times, time + 1)],
      previous: time => times[bound(times, time - 1, false) - 1],
      snapshot(time) {
        const count = bound(times, time), users = new Map();
        for (const [id, user] of people) {
          const count = bound(user.times, time), position = count - 1;
          users.set(id, {count, last: count ? events[user.last[position]] : undefined,
            shot: count && user.shots[position] >= 0 ? events[user.shots[position]] : undefined,
            blocking: user.firstBlocker <= time});
        }
        return {count, actions: actions[count], flags: flags[count],
          finished: bound(doneAt, time), found: bound(foundAt, time), users};
      }
    };
  };
})();
