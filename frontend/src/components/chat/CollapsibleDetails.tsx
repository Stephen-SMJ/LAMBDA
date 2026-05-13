import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface CollapsibleDetailsProps {
  title: string
  children: React.ReactNode
}

export default function CollapsibleDetails({ title, children }: CollapsibleDetailsProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="mt-4 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-2 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
        type="button"
      >
        <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          🔧 {title}
        </span>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-neutral-500" />
        ) : (
          <ChevronRight className="w-4 h-4 text-neutral-500" />
        )}
      </button>
      {isExpanded && (
        <div className="p-4 bg-neutral-50 dark:bg-neutral-900/50">
          {children}
        </div>
      )}
    </div>
  )
}
