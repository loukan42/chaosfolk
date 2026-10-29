/* Bounded local evidence loading. Classic scripts also work from file://. */
(() => {
  'use strict';
  window.createEvidenceStore = function(manifest) {
    const cache = new Map(), pending = new Map(), queue = [];
    const chunks = Array.isArray(manifest?.chunks) ? manifest.chunks : [];
    const maxBytes = 1024 * 1024, maxChunks = 4;
    let retainedBytes = 0, active = 0, loads = 0;
    const descriptors = new Map();
    const valid = descriptor => descriptor && /^[a-f0-9]{64}$/.test(descriptor.id) &&
      descriptor.file === `assets/journal/${descriptor.id}.js` && Number.isSafeInteger(descriptor.bytes) && descriptor.bytes >= 0;
    for (const descriptor of [...chunks, ...Object.values(manifest?.proofs || {})]) {
      if (valid(descriptor)) descriptors.set(descriptor.id, descriptor);
    }
    function remember(id, payload, bytes) {
      if (bytes > maxBytes) return; // One oversized event/proof is usable, but never retained in the cache.
      if (cache.has(id)) {retainedBytes -= cache.get(id).bytes; cache.delete(id);}
      while (cache.size && (cache.size >= maxChunks || retainedBytes + bytes > maxBytes)) {
        const key = cache.keys().next().value;
        retainedBytes -= cache.get(key).bytes; cache.delete(key);
      }
      cache.set(id, {payload, bytes}); retainedBytes += bytes;
    }
    function cached(id) {
      const entry = cache.get(id);
      if (entry) {cache.delete(id); cache.set(id, entry);}
      return entry?.payload;
    }
    function relevant(task) {return task.checks.some(check => !check || check());}
    function prune() {
      for (let index = queue.length - 1; index >= 0; index--) {
        const task = queue[index];
        if (!relevant(task)) {
          queue.splice(index, 1); pending.delete(task.descriptor.id);
          task.reject(new Error('superseded'));
        }
      }
    }
    function pump() {
      prune();
      while (active < 2 && queue.length) {
        const task = queue.shift(), descriptor = task.descriptor;
        active++; loads++;
        const script = document.createElement('script');
        task.script = script;
        script.src = descriptor.file; script.async = true;
        const finish = error => {
          if (task.finished) return;
          task.finished = true;
          clearTimeout(task.timeout); script.remove();
          pending.delete(descriptor.id); active--;
          if (!error && !task.received) error = new Error('invalid-evidence');
          if (error) task.reject(error);
          else {remember(descriptor.id, task.payload, descriptor.bytes); task.resolve(task.payload);}
          task.payload = null;
          pump();
        };
        task.timeout = setTimeout(() => finish(new Error('missing-evidence')), 15000);
        script.onload = () => finish();
        script.onerror = () => finish(new Error('missing-evidence'));
        document.head.append(script);
      }
    }
    window.__chaosfolkReceiveDetails = function(id, payload) {
      const task = pending.get(id);
      if (!task || task.script !== document.currentScript || task.finished || !payload || typeof payload !== 'object') return;
      const descriptor = task.descriptor;
      if ('count' in descriptor && (!Array.isArray(payload.events) || payload.events.length !== descriptor.count ||
          payload.events.some(event => !event || typeof event !== 'object' || Array.isArray(event)))) return;
      if (!('count' in descriptor) && (!payload.proof || typeof payload.proof !== 'object' || Array.isArray(payload.proof))) return;
      task.payload = payload; task.received = true;
    };
    function request(descriptor, current) {
      if (manifest?.version !== 1 || !valid(descriptor) || !descriptors.has(descriptor.id)) return Promise.reject(new Error('invalid-evidence'));
      if (current && !current()) return Promise.reject(new Error('superseded'));
      const hit = cached(descriptor.id);
      if (hit) return Promise.resolve(hit);
      const existing = pending.get(descriptor.id);
      if (existing) {existing.checks.push(current); return existing.promise;}
      const task = {descriptor, checks:[current]};
      task.promise = new Promise((resolve,reject) => {task.resolve=resolve; task.reject=reject;});
      pending.set(descriptor.id, task); queue.push(task); pump();
      return task.promise;
    }
    function eventChunk(index) {
      if (!Number.isSafeInteger(index) || index < 0 || index >= manifest?.total_events) return null;
      let low = 0, high = chunks.length;
      while (low < high) {
        const middle = Math.floor((low + high) / 2), chunk = chunks[middle];
        if (chunk.start + chunk.count <= index) low = middle + 1; else high = middle;
      }
      const chunk = chunks[low];
      return chunk && Number.isSafeInteger(chunk.start) && Number.isSafeInteger(chunk.count) &&
        chunk.count > 0 && chunk.start <= index && index < chunk.start + chunk.count ? chunk : null;
    }
    return {
      event(event, current) {
        if (manifest?.version !== 1 || !Number.isSafeInteger(event?._detail)) return Promise.resolve(event);
        const chunk = eventChunk(event._detail);
        return request(chunk, current).then(payload => payload.events[event._detail - chunk.start]);
      },
      peek(event) {
        if (manifest?.version !== 1 || !Number.isSafeInteger(event?._detail)) return event;
        const chunk = eventChunk(event._detail), hit = chunk && cached(chunk.id);
        return hit?.events[event._detail - chunk.start];
      },
      proof(proof, current) {
        if (manifest?.version !== 1 || !proof?._proof_detail) return Promise.resolve(proof);
        return request(descriptors.get(proof._proof_detail), current).then(payload => payload.proof);
      },
      stats() {return {chunks:cache.size, bytes:retainedBytes, pending:pending.size, active, loads};}
    };
  };
})();
