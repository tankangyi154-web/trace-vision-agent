import policy from '../../data/media-limits.json'

export const mediaLimits = policy
export const mediaWaitMs = (policy.worker_timeout_seconds * policy.max_inflight + 30) * 1000

export function validateMediaFile(file: { name: string; size: number }): string {
  const extension = file.name.split('.').pop()?.toLowerCase()
  const image = ['jpg', 'jpeg', 'png', 'webp'].includes(extension || '')
  const video = ['mp4', 'mov', 'webm'].includes(extension || '')
  if (!image && !video) return '请选JPG、PNG、WebP图片，或MP4、MOV、WebM短视频。'
  if (!Number.isFinite(file.size) || file.size <= 0 || file.size > (image ? policy.image_max_mb : policy.video_max_mb) * 1024 * 1024) {
    return image ? `图片请不超过${policy.image_max_mb}MB。` : `视频请不超过${policy.video_max_mb}MB，时长不超过${policy.video_max_seconds / 60}分钟。`
  }
  return ''
}
