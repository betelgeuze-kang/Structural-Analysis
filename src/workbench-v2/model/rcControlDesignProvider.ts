import { openRcReviewWorker } from './rcReviewWorker'
import type { JobAuthorizationProvider } from './jobTransport'
import type { RcDesignReview } from './rcControlDesignSchema'

export interface RcDesignSession extends RcDesignReview {
  download(candidate: string, role: string): Promise<Blob>
  onFailure(listener: () => void): () => void
  dispose(): void
}
export async function loadRcControlDesign(url: string, signal: AbortSignal, authorize?: JobAuthorizationProvider): Promise<RcDesignSession> {
  const connection = await openRcReviewWorker(new URL('./rcControlDesign.worker.ts', import.meta.url), url, signal, authorize)
  try {
    const review = await connection.initialize<RcDesignReview>()
    return { ...review, dispose: connection.dispose, onFailure: connection.onFailure, download: (candidate, role) => connection.call('download', { candidate, role }) }
  } catch (error) { connection.dispose(); throw error }
}
