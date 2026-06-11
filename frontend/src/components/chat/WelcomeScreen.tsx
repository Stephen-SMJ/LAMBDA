import { AnimatePresence, motion } from 'framer-motion'
import { 
  CarTaxiFront,
  HeartPulse,
  Upload,
  ChevronDown,
  Compass,
  X,
  FileText,
  Send
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ChatInput from './ChatInput'
import { useI18n } from '../../i18n'

interface WelcomeScreenProps {
  onSendMessage: (message: string, files?: File[], analysisMode?: string) => void | boolean | Promise<void | boolean>
  models?: Array<{ id: string; name: string; multimodal?: boolean }>
  selectedModel: string
  onModelChange: (model: string) => void
}

const exampleDatasets = [
  {
    icon: CarTaxiFront,
    title: 'NYC Taxi Trips',
    description: 'Autonomously explore fares, tips, trip distances, payment behavior, and borough-level taxi patterns',
    filename: 'taxis.csv',
    displayName: 'NYC Taxi Trips Dataset',
  },
  {
    icon: HeartPulse,
    title: 'Health Expenditure',
    description: 'Autonomously analyze health spending and life expectancy trends across countries from 1970 to 2020',
    filename: 'healthexp.csv',
    displayName: 'Health Expenditure Dataset',
  },
]

const MAX_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024
const BLOCKED_UPLOAD_EXTENSIONS = new Set([
  '.app', '.apk', '.bat', '.bin', '.bash', '.cmd', '.com', '.cpl', '.dll',
  '.dmg', '.elf', '.exe', '.gadget', '.hta', '.jar', '.js', '.jse', '.lnk',
  '.msi', '.msp', '.pif', '.ps1', '.py', '.rb', '.reg', '.run', '.scr',
  '.sh', '.so', '.sys', '.vb', '.vbe', '.vbs', '.ws', '.wsf', '.zsh',
])

const getFileExtension = (filename: string) => {
  const dotIndex = filename.lastIndexOf('.')
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : ''
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const getModelSpeedHint = (model: { id: string; name: string }) => {
  const text = `${model.id} ${model.name}`.toLowerCase()
  if (text.includes('claude-sonnet-4-6') || text.includes('claude sonnet 4.6') || text.includes('gpt-5.3-codex') || text.includes('gpt 5.3 codex') || text.includes('codex')) {
    return 'Max · 10+ min'
  }
  if (text.includes('pro')) return 'Max · 10+ min'
  if (text.includes('deepseek') || text.includes('mimo') || text.includes('minimax')) return 'Medium · 5-10 min'
  return 'Medium · 5-10 min'
}

const formatModelName = (model: { name: string; multimodal?: boolean }) => (
  model.multimodal ? `${model.name} (Multi-modal)` : model.name
)

export default function WelcomeScreen({
  onSendMessage,
  models = [],
  selectedModel,
  onModelChange,
}: WelcomeScreenProps) {
  const [isAutonomousOpen, setIsAutonomousOpen] = useState(false)
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false)
  const [autonomousFiles, setAutonomousFiles] = useState<File[]>([])
  const [exampleError, setExampleError] = useState('')
  const [loadingExample, setLoadingExample] = useState<string | null>(null)
  const autonomousFileInputRef = useRef<HTMLInputElement>(null)
  const modelMenuRef = useRef<HTMLDivElement>(null)
  const selectedModelInfo = models.find((model) => model.id === selectedModel)
  const { t } = useI18n()

  const getDatasetCopy = (dataset: typeof exampleDatasets[0]) => {
    if (dataset.filename === 'taxis.csv') {
      return { title: t('taxiTrips'), description: t('taxiTripsDescription') }
    }
    return { title: t('healthExpenditure'), description: t('healthExpenditureDescription') }
  }

  useEffect(() => {
    if (!isModelMenuOpen) return

    const handleClickOutside = (event: MouseEvent) => {
      if (!modelMenuRef.current?.contains(event.target as Node)) {
        setIsModelMenuOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isModelMenuOpen])

  const handleExampleClick = async (dataset: typeof exampleDatasets[0]) => {
    if (loadingExample) return

    setExampleError('')
    setLoadingExample(dataset.filename)
    try {
      // Fetch the CSV file from public folder
      const response = await fetch(`/examples/${dataset.filename}`, { cache: 'no-store' })
      if (!response.ok) {
        throw new Error('Failed to load dataset')
      }
      
      const blob = await response.blob()
      if (blob.size === 0) {
        throw new Error('Example dataset is empty')
      }
      const file = new File([blob], dataset.filename, { type: 'text/csv' })
      
      // Example cards start the autonomous exploration flow directly.
      await onSendMessage('', [file], 'autonomous_exploration')
    } catch (error) {
      console.error('Failed to load example dataset:', error)
      setExampleError(`Failed to load ${dataset.filename}. Please refresh the page or upload the dataset manually.`)
    } finally {
      setLoadingExample(null)
    }
  }

  const addAutonomousFiles = (incomingFiles: File[]) => {
    const validFiles = incomingFiles.filter((file) => {
      const ext = getFileExtension(file.name)
      return file.size <= MAX_UPLOAD_SIZE_BYTES && !BLOCKED_UPLOAD_EXTENSIONS.has(ext)
    })
    if (validFiles.length > 0) {
      setAutonomousFiles((prev) => [...prev, ...validFiles])
    }
  }

  const submitAutonomousExploration = () => {
    if (autonomousFiles.length === 0) return
    onSendMessage('', autonomousFiles, 'autonomous_exploration')
    setAutonomousFiles([])
    setIsAutonomousOpen(false)
    if (autonomousFileInputRef.current) autonomousFileInputRef.current.value = ''
  }

  return (
    <div className="h-full overflow-y-auto bg-white dark:bg-neutral-900">
      <div className="relative min-h-full flex flex-col items-center justify-center px-6 py-10">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-20 h-72 w-72 -translate-x-1/2 rounded-full bg-neutral-100 blur-3xl dark:bg-neutral-800/50" />
        <div className="absolute bottom-20 right-20 h-56 w-56 rounded-full bg-blue-50 blur-3xl dark:bg-blue-950/20" />
      </div>
      {/* Logo & Hero Input */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-4xl text-center"
      >
        <div className="inline-flex items-center justify-center w-[72px] h-[72px] mb-7">
          <img 
            src="/LAMBDA_logo.gif" 
            alt="LAMBDA" 
            className="w-[72px] h-[72px] object-contain rounded-2xl"
          />
        </div>
        <h1 className="text-6xl sm:text-7xl font-black tracking-tight text-neutral-950 dark:text-white mb-10">
          LAMBDA
        </h1>

        <ChatInput
          onSendMessage={(message, files) => onSendMessage(message, files)}
          placeholder={t('askPlaceholder')}
          variant="hero"
          className="rounded-[28px]"
          heroControls={
            <>
              <button
                type="button"
                onClick={() => setIsAutonomousOpen(true)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-neutral-200 bg-white/90 px-2.5 py-2 text-xs font-medium text-neutral-700 shadow-sm transition-all hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:border-neutral-600 sm:px-3 sm:text-sm"
              >
                <Compass className="h-4 w-4 text-neutral-500" />
                <span className="hidden min-[420px]:inline">{t('autoExploration')}</span>
                <span className="min-[420px]:hidden">{t('autoShort')}</span>
              </button>

              <div ref={modelMenuRef} className="relative ml-auto min-w-0 shrink">
                <button
                  type="button"
                  onClick={() => setIsModelMenuOpen((open) => !open)}
                  className="inline-flex max-w-[132px] items-center gap-1.5 rounded-xl px-2 py-2 text-xs font-medium text-neutral-700 transition-colors hover:bg-neutral-100 hover:text-neutral-950 dark:text-neutral-200 dark:hover:bg-neutral-700 dark:hover:text-white sm:max-w-[190px] sm:text-sm"
                  title={t('selectModel')}
                >
                  <span className="truncate">{selectedModelInfo?.name || t('model')}</span>
                  <ChevronDown className={`h-4 w-4 shrink-0 text-neutral-400 transition-transform ${isModelMenuOpen ? 'rotate-180' : ''}`} />
                </button>

                <AnimatePresence>
                  {isModelMenuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.98 }}
                      className="absolute bottom-full right-0 z-30 mb-2 w-72 overflow-hidden rounded-2xl border border-neutral-200 bg-white p-1.5 text-left shadow-xl shadow-neutral-200/70 dark:border-neutral-700 dark:bg-neutral-800 dark:shadow-black/30"
                    >
                      {models.map((model) => {
                        const isSelected = model.id === selectedModel
                        return (
                          <button
                            key={model.id}
                            type="button"
                            onClick={() => {
                              onModelChange(model.id)
                              setIsModelMenuOpen(false)
                            }}
                            className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                              isSelected
                                ? 'bg-neutral-100 text-neutral-950 dark:bg-neutral-700 dark:text-white'
                                : 'text-neutral-700 hover:bg-neutral-50 hover:text-neutral-950 dark:text-neutral-200 dark:hover:bg-neutral-700/70 dark:hover:text-white'
                            }`}
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-semibold">{formatModelName(model)}</span>
                              <span className="mt-0.5 block text-xs text-neutral-400">{getModelSpeedHint(model)}</span>
                            </span>
                            {isSelected && <span className="h-2 w-2 shrink-0 rounded-full bg-neutral-900 dark:bg-white" />}
                          </button>
                        )
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </>
          }
        />
      </motion.div>

      <AnimatePresence>
        {isAutonomousOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4 backdrop-blur-sm"
            onClick={() => setIsAutonomousOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              className="w-full max-w-lg rounded-[28px] border border-neutral-200 bg-white p-5 text-left shadow-2xl dark:border-neutral-700 dark:bg-neutral-900"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <div className="inline-flex rounded-2xl bg-neutral-100 p-2 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200">
                    <Compass className="h-5 w-5" />
                  </div>
                  <h2 className="mt-3 text-xl font-bold text-neutral-950 dark:text-white">{t('autoExploration')}</h2>
                  <p className="mt-2 text-sm leading-6 text-neutral-500 dark:text-neutral-400">
                    {t('autoDescription')}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsAutonomousOpen(false)}
                  className="rounded-full p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <input
                ref={autonomousFileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(event) => {
                  addAutonomousFiles(Array.from(event.target.files || []))
                  if (autonomousFileInputRef.current) autonomousFileInputRef.current.value = ''
                }}
              />
              <button
                type="button"
                onClick={() => autonomousFileInputRef.current?.click()}
                className="flex min-h-[132px] w-full flex-col items-center justify-center rounded-3xl border border-dashed border-neutral-300 bg-neutral-50 px-4 text-center transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-800/60 dark:hover:bg-neutral-800"
              >
                <Upload className="h-6 w-6 text-neutral-400" />
                <span className="mt-3 text-sm font-semibold text-neutral-800 dark:text-neutral-100">{t('uploadData')}</span>
                <span className="mt-1 text-xs text-neutral-400">{t('uploadMultiple')}</span>
              </button>

              {autonomousFiles.length > 0 && (
                <div className="mt-4 space-y-2">
                  {autonomousFiles.map((file, index) => (
                    <div key={`${file.name}-${file.size}-${file.lastModified}`} className="flex items-center gap-2 rounded-2xl bg-neutral-50 px-3 py-2 text-sm dark:bg-neutral-800">
                      <FileText className="h-4 w-4 shrink-0 text-neutral-400" />
                      <span className="min-w-0 flex-1 truncate text-neutral-700 dark:text-neutral-200">{file.name}</span>
                      <span className="text-xs text-neutral-400">{formatFileSize(file.size)}</span>
                      <button
                        type="button"
                        onClick={() => setAutonomousFiles((prev) => prev.filter((_, fileIndex) => fileIndex !== index))}
                        className="rounded-full p-1 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={submitAutonomousExploration}
                disabled={autonomousFiles.length === 0}
                className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-neutral-950 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 disabled:bg-neutral-200 disabled:text-neutral-400 dark:bg-white dark:text-neutral-950 dark:hover:bg-neutral-200 dark:disabled:bg-neutral-800 dark:disabled:text-neutral-500"
              >
                <Send className="h-4 w-4" />
                {t('submit')}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Example Datasets */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15 }}
        className="relative mt-14 w-full max-w-4xl"
      >
        <div className="flex items-center justify-between gap-2 mb-4 px-1">
          <div className="flex items-center gap-2">
          <Upload className="w-4 h-4 text-neutral-400" />
            <span className="text-sm text-neutral-500 dark:text-neutral-400 font-medium">{t('tryExamples')}</span>
          </div>
          <span className="text-xs text-neutral-400">{t('csvExamples')}</span>
        </div>
        {exampleError && (
          <div className="mb-3 rounded-2xl border border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200">
            {exampleError}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {exampleDatasets.map((dataset, index) => {
            const datasetCopy = getDatasetCopy(dataset)
            const isLoading = loadingExample === dataset.filename
            return (
            <motion.button
              key={dataset.filename}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + index * 0.1 }}
              onClick={() => handleExampleClick(dataset)}
              disabled={!!loadingExample}
              aria-busy={isLoading}
              className="group text-left p-4 bg-white/90 dark:bg-neutral-800/90 border border-neutral-200/80 dark:border-neutral-700 rounded-3xl hover:border-neutral-300 dark:hover:border-neutral-600 hover:shadow-lg hover:shadow-neutral-200/70 dark:hover:shadow-black/20 transition-all duration-300 backdrop-blur disabled:cursor-wait disabled:opacity-70"
            >
              <div className="flex items-start gap-3">
                <div className="p-2.5 bg-neutral-100 dark:bg-neutral-700 rounded-xl group-hover:bg-neutral-200 dark:group-hover:bg-neutral-600 transition-colors">
                  <dataset.icon className="w-5 h-5 text-neutral-700 dark:text-neutral-200" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-semibold text-neutral-900 dark:text-white">
                    {datasetCopy.title}
                  </h3>
                  <p className="mt-1 line-clamp-2 text-xs text-neutral-500 dark:text-neutral-400">
                    {datasetCopy.description}
                  </p>
                  <div className="mt-2 flex items-center gap-2 text-xs text-neutral-900 dark:text-white font-medium">
                    {isLoading && (
                      <span className="h-3 w-3 rounded-full border-2 border-neutral-300 border-t-neutral-900 animate-spin dark:border-neutral-600 dark:border-t-white" />
                    )}
                    <span>{isLoading ? t('loadingExample') : t('analyzeExample')}</span>
                  </div>
                </div>
              </div>
            </motion.button>
          )})}
        </div>
      </motion.div>
      </div>
    </div>
  )
}
