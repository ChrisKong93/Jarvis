/**
 * 语音交互工具函数
 * 提供语音识别 (STT) 和语音合成 (TTS) 功能
 * 优先使用浏览器原生 API，支持后端 API 作为增强
 */

// ---- 语音识别 (Speech-to-Text) ----

let recognition = null
let isRecording = false

/**
 * 检测浏览器是否支持语音识别
 */
export function isSpeechSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition)
}

/**
 * 开始语音识别
 * @param {Object} options
 * @param {Function} options.onResult - 识别结果回调 (text, isFinal)
 * @param {Function} options.onError - 错误回调 (errorMsg)
 * @param {Function} options.onEnd - 识别结束回调
 * @param {string} options.lang - 语言，默认 'zh-CN'
 * @returns {boolean} 是否成功启动
 */
export function startSpeechRecognition({ onResult, onError, onEnd, lang = 'zh-CN' } = {}) {
  if (isRecording) {
    console.warn('[Voice] 正在录音中')
    return false
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) {
    onError?.('当前浏览器不支持语音识别，请使用 Chrome 或 Edge')
    return false
  }

  try {
    recognition = new SpeechRecognition()
    recognition.lang = lang
    recognition.continuous = false
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onstart = () => {
      isRecording = true
    }

    recognition.onresult = (event) => {
      let finalText = ''
      let interimText = ''

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          finalText += transcript
        } else {
          interimText += transcript
        }
      }

      if (finalText) {
        onResult?.(finalText, true)
      } else if (interimText) {
        onResult?.(interimText, false)
      }
    }

    recognition.onerror = (event) => {
      console.error('[Voice] 语音识别错误:', event.error)
      isRecording = false
      const errorMap = {
        'no-speech': '未检测到语音，请重试',
        'aborted': '录音已取消',
        'audio-capture': '无法访问麦克风，请检查权限',
        'network': '网络错误',
        'not-allowed': '麦克风权限被拒绝',
        'service-not-allowed': '语音识别服务不可用',
      }
      onError?.(errorMap[event.error] || `语音识别错误: ${event.error}`)
    }

    recognition.onend = () => {
      isRecording = false
      onEnd?.()
    }

    recognition.start()
    return true
  } catch (e) {
    console.error('[Voice] 启动语音识别失败:', e)
    isRecording = false
    onError?.('启动语音识别失败: ' + e.message)
    return false
  }
}

/**
 * 停止语音识别
 */
export function stopSpeechRecognition() {
  if (recognition && isRecording) {
    try {
      recognition.stop()
    } catch (e) {
      // ignore
    }
  }
  isRecording = false
  recognition = null
}

/**
 * 是否正在录音
 */
export function isRecognizing() {
  return isRecording
}

// ---- 语音合成 (Text-to-Speech) ----

let currentUtterance = null
let isSpeaking = false

/**
 * 检测浏览器是否支持语音合成
 */
export function isTTSSupported() {
  return !!window.speechSynthesis
}

/**
 * 获取可用的语音列表
 * @returns {Promise<SpeechSynthesisVoice[]>}
 */
export function getVoices() {
  return new Promise((resolve) => {
    const voices = window.speechSynthesis?.getVoices()
    if (voices?.length) {
      resolve(voices)
    } else {
      // 部分浏览器需要等待 voiceschanged 事件
      window.speechSynthesis?.addEventListener('voiceschanged', () => {
        resolve(window.speechSynthesis?.getVoices() || [])
      }, { once: true })
      // 超时后备
      setTimeout(() => {
        resolve(window.speechSynthesis?.getVoices() || [])
      }, 1000)
    }
  })
}

/**
 * 获取中文语音列表
 */
export async function getChineseVoices() {
  const voices = await getVoices()
  return voices.filter(v =>
    v.lang.startsWith('zh') ||
    v.lang.startsWith('cmn') ||
    v.lang.startsWith('yue')
  )
}

/**
 * 播放语音
 * @param {string} text - 要播放的文本
 * @param {Object} options
 * @param {string} options.lang - 语言，默认 'zh-CN'
 * @param {number} options.rate - 语速，0.1~10，默认 1.0
 * @param {number} options.pitch - 音高，0~2，默认 1.0
 * @param {number} options.volume - 音量，0~1，默认 1.0
 * @param {string} options.voiceName - 指定语音名称
 * @param {Function} options.onStart - 开始播放回调
 * @param {Function} options.onEnd - 播放结束回调
 * @param {Function} options.onError - 错误回调
 * @returns {boolean} 是否成功启动
 */
export function speakText(text, options = {}) {
  if (!text || !window.speechSynthesis) {
    options.onError?.('当前浏览器不支持语音合成')
    return false
  }

  // 取消当前播放
  stopSpeaking()

  try {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = options.lang || 'zh-CN'
    utterance.rate = options.rate ?? 1.0
    utterance.pitch = options.pitch ?? 1.0
    utterance.volume = options.volume ?? 1.0

    // 如果指定了语音名称，匹配并使用
    if (options.voiceName) {
      const voices = window.speechSynthesis.getVoices()
      const matched = voices.find(v => v.name === options.voiceName)
      if (matched) utterance.voice = matched
    }

    currentUtterance = utterance

    utterance.onstart = () => {
      isSpeaking = true
      options.onStart?.()
    }

    utterance.onend = () => {
      isSpeaking = false
      currentUtterance = null
      options.onEnd?.()
    }

    utterance.onerror = (event) => {
      console.error('[Voice] 语音合成错误:', event.error)
      isSpeaking = false
      currentUtterance = null
      options.onError?.(event.error)
    }

    window.speechSynthesis.speak(utterance)
    return true
  } catch (e) {
    console.error('[Voice] 启动语音合成失败:', e)
    isSpeaking = false
    options.onError?.(e.message)
    return false
  }
}

/**
 * 停止语音播放
 */
export function stopSpeaking() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
  isSpeaking = false
  currentUtterance = null
}

/**
 * 是否正在播放语音
 */
export function isSpeakingNow() {
  return isSpeaking
}

// ---- 后端语音 API（可选增强） ----

/**
 * 使用后端 API 进行语音识别（需要 backend/routes/voice.py 支持）
 * @param {Blob} audioBlob - 录音音频 blob
 * @param {string} provider - STT 引擎 ('whisper_api')
 * @returns {Promise<string>} 识别结果文本
 */
export async function backendSTT(audioBlob, provider = 'whisper_api') {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'recording.webm')
  formData.append('provider', provider)

  const token = localStorage.getItem('jarvis-token') || ''

  const response = await fetch('/api/voice/stt', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
    body: formData,
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: '未知错误' }))
    throw new Error(err.error || `STT 请求失败: ${response.status}`)
  }

  const data = await response.json()
  return data.text
}

/**
 * 使用后端 API 进行语音合成
 * @param {string} text - 要合成的文本
 * @param {Object} options
 * @param {string} options.voice - 语音角色
 * @param {number} options.speed - 语速
 * @returns {Promise<string>} 音频 URL (blob URL)
 */
export async function backendTTS(text, options = {}) {
  const token = localStorage.getItem('jarvis-token') || ''

  const response = await fetch('/api/voice/tts', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      text,
      voice: options.voice || 'zh-CN-XiaoxiaoNeural',
      speed: options.speed ?? 1.0,
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: '未知错误' }))
    throw new Error(err.error || `TTS 请求失败: ${response.status}`)
  }

  const audioBlob = await response.blob()
  return URL.createObjectURL(audioBlob)
}
