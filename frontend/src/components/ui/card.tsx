import * as React from "react"
import { cn } from "@/lib/utils"

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-2xl border border-slate-200/80 bg-white shadow-[0_12px_35px_-24px_rgba(17,43,61,0.36)]", className)} {...props} />
  ),
)
Card.displayName = "Card"
