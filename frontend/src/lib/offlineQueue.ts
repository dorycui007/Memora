import type { CaptureCreate } from "./types";
import { capturesApi } from "./api";

const QUEUE_KEY = "memora_offline_captures";

interface QueuedCapture {
  id: string;
  data: CaptureCreate;
  queuedAt: string;
}

function getQueue(): QueuedCapture[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveQueue(queue: QueuedCapture[]) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export function queueCapture(data: CaptureCreate): string {
  const id = crypto.randomUUID();
  const queue = getQueue();
  queue.push({ id, data, queuedAt: new Date().toISOString() });
  saveQueue(queue);
  return id;
}

export function getQueuedCaptures(): QueuedCapture[] {
  return getQueue();
}

export async function flushQueue(): Promise<number> {
  const queue = getQueue();
  if (queue.length === 0) return 0;

  let flushed = 0;
  const remaining: QueuedCapture[] = [];

  for (const item of queue) {
    try {
      await capturesApi.create(item.data);
      flushed++;
    } catch {
      remaining.push(item);
    }
  }

  saveQueue(remaining);
  return flushed;
}

export function clearQueue() {
  localStorage.removeItem(QUEUE_KEY);
}
