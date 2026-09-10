import type { JobAuthorizationProvider } from './jobTransport'
import type { RcDesignSession } from './rcControlDesignProvider'
import { openRcReviewWorker } from './rcReviewWorker'
import type { RcSearchReview } from './rcControlSearchSchema'

export interface RcSearchSession extends RcSearchReview {
  designSession(arm: string): RcDesignSession
  download(role: 'result' | 'plan' | 'policy' | 'historical-training'): Promise<Blob>
  onFailure(listener: () => void): () => void
  dispose(): void
}
export async function loadRcControlSearch(url: string, signal: AbortSignal, authorize?: JobAuthorizationProvider): Promise<RcSearchSession> {
  const connection = await openRcReviewWorker(new URL('./rcControlSearch.worker.ts', import.meta.url), url, signal, authorize)
  try {
    const review = await connection.initialize<RcSearchReview>()
    return { ...review, dispose: connection.dispose, onFailure: connection.onFailure,
      download: role => connection.call('metadata', { role }),
      designSession(arm) {
        if (!Object.prototype.hasOwnProperty.call(review.designs, arm)) throw new Error('rc_search_arm_unavailable')
        return { ...review.designs[arm], dispose() { /* Search session owns its shared worker. */ }, onFailure: connection.onFailure,
          download: (candidate, role) => connection.call('download', { arm, candidate, role }) }
      },
    }
  } catch (error) { connection.dispose(); throw error }
}
