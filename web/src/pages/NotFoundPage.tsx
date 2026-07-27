import { CircleSlash } from 'lucide-react'
import { Card, EmptyState } from '../components/ui'
import { Link } from '../lib/router'

export function NotFoundPage() {
  return (
    <Card>
      <EmptyState
        icon={<CircleSlash size={20} />}
        title="Nothing here"
        description="That page does not exist in LM-Gambit."
        action={
          <Link to="/" className="btn btn-primary">
            Back to the run dashboard
          </Link>
        }
      />
    </Card>
  )
}
